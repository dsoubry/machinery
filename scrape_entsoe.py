#!/usr/bin/env python3
"""
Belgian Day-Ahead Price Scraper - FINAL VERSION
Correct XML namespace handling for ENTSO-E API v7.3
"""

import os
import sys
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# ENTSO-E API Configuration
ENTSOE_TOKEN = os.getenv('ENTSOE_TOKEN', '')
ENTSOE_API_URL = 'https://web-api.tp.entsoe.eu/api'
BELGIUM_DOMAIN = '10YBE----------2'

def get_entsoe_token():
    """Get ENTSO-E API token from environment or exit with instructions"""
    global ENTSOE_TOKEN
    
    if not ENTSOE_TOKEN:
        print("❌ ENTSO-E API token niet gevonden!")
        print("🔧 Vereiste stappen:")
        print("1. Ga naar https://transparency.entsoe.eu/")
        print("2. Maak een gratis account aan") 
        print("3. Vraag een 'Restful API' token aan")
        print("4. Voeg ENTSOE_TOKEN toe als GitHub secret")
        sys.exit(1)
    
    return ENTSOE_TOKEN

def detect_xml_namespace(root):
    """Automatically detect the XML namespace from the root element"""
    root_tag = root.tag
    if '}' in root_tag:
        namespace_uri = root_tag.split('}')[0][1:]  # Remove { and }
        return {'ns': namespace_uri}
    return {}

def fetch_day_ahead_prices(target_date=None):
    """Fetch day-ahead prices from ENTSO-E with dynamic namespace handling"""
    token = get_entsoe_token()
    
    # Default to today's prices
    if target_date is None:
        target_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # ENTSO-E uses UTC timestamps
    start_time = target_date.replace(tzinfo=timezone.utc)
    end_time = start_time + timedelta(days=1)
    
    # Format for ENTSO-E API
    start_str = start_time.strftime('%Y%m%d%H%M')
    end_str = end_time.strftime('%Y%m%d%H%M')
    
    print(f"🔌 Ophalen dag-vooruit prijzen voor {target_date.strftime('%d/%m/%Y')}...")
    
    params = {
        'securityToken': token,
        'documentType': 'A44',  # Day-ahead prices
        'in_Domain': BELGIUM_DOMAIN,
        'out_Domain': BELGIUM_DOMAIN,
        'periodStart': start_str,
        'periodEnd': end_str
    }
    
    try:
        response = requests.get(ENTSOE_API_URL, params=params, timeout=30)
        
        print(f"📡 HTTP Status: {response.status_code}")
        
        if response.status_code == 503:
            print("⚠️ ENTSO-E service tijdelijk niet beschikbaar")
            return None
        elif response.status_code != 200:
            print(f"❌ HTTP {response.status_code}: {response.reason}")
            return None
        
        # Parse XML with dynamic namespace detection
        try:
            root = ET.fromstring(response.content)
            print(f"🔍 Root element: {root.tag}")
        except ET.ParseError as e:
            print(f"❌ XML Parse Error: {e}")
            return None
        
        # Detect namespace dynamically
        namespaces = detect_xml_namespace(root)
        print(f"🔍 Detected namespace: {namespaces}")
        
        # Parse prices
        prices = parse_entsoe_response(root, target_date, namespaces)
        
        if not prices:
            print("❌ Geen prijsdata gevonden")
            return None
        
        print(f"✅ {len(prices)} uurprijzen succesvol opgehaald")
        return format_price_data(prices, target_date)
        
    except Exception as e:
        print(f"❌ Fout: {e}")
        return None

def parse_entsoe_response(root, target_date, namespaces):
    """Parse ENTSO-E XML response with dynamic namespace"""
    prices = []
    
    print("🔍 Parsing XML response...")
    
    # Try with detected namespace first
    if namespaces:
        time_series_list = root.findall('.//ns:TimeSeries', namespaces)
        print(f"🔍 Found {len(time_series_list)} TimeSeries elements (with namespace)")
    else:
        time_series_list = []
        
    # Fallback: try without namespace
    if not time_series_list:
        # Remove namespace from search
        for elem in root.iter():
            if elem.tag.endswith('}TimeSeries'):
                time_series_list.append(elem)
        print(f"🔍 Found {len(time_series_list)} TimeSeries elements (without namespace)")
    
    for ts_idx, time_series in enumerate(time_series_list):
        print(f"🔍 Processing TimeSeries {ts_idx + 1}")
        
        # Find Period element - try both with and without namespace
        period = None
        if namespaces:
            period = time_series.find('.//ns:Period', namespaces)
        
        if period is None:
            # Try without namespace
            for elem in time_series.iter():
                if elem.tag.endswith('}Period') or elem.tag == 'Period':
                    period = elem
                    break
        
        if period is None:
            print(f"⚠️ No Period found in TimeSeries {ts_idx + 1}")
            continue
        
        # Get time interval - flexible approach
        start_time_elem = None
        
        # Try various ways to find start time
        for elem in period.iter():
            if elem.tag.endswith('}start') or elem.tag == 'start':
                start_time_elem = elem
                break
        
        if start_time_elem is None:
            print(f"⚠️ No start time found")
            continue
        
        start_time_text = start_time_elem.text
        print(f"🔍 Period start time: {start_time_text}")
        
        try:
            start_time = datetime.fromisoformat(start_time_text.replace('Z', '+00:00'))
        except ValueError as e:
            print(f"❌ Error parsing start time: {e}")
            continue
        
        # Find Point elements - flexible approach
        points = []
        for elem in period.iter():
            if elem.tag.endswith('}Point') or elem.tag == 'Point':
                points.append(elem)
        
        print(f"🔍 Found {len(points)} price points")
        
        for point in points:
            # Find position and price - flexible approach
            position_elem = None
            price_elem = None
            
            for elem in point.iter():
                if elem.tag.endswith('}position') or elem.tag == 'position':
                    position_elem = elem
                elif elem.tag.endswith('}price.amount') or elem.tag == 'price.amount':
                    price_elem = elem
            
            if position_elem is None or price_elem is None:
                continue
            
            try:
                position = int(position_elem.text)
                price = float(price_elem.text)
                
                # Calculate timestamp (position 1 = start_time)
                hour_timestamp = start_time + timedelta(hours=position-1)
                
                # Convert to Belgian local time
                local_time = hour_timestamp.astimezone()
                
                prices.append({
                    'datetime': local_time,
                    'hour': position,
                    'price_eur_mwh': price,
                    'price_eur_kwh': price / 1000
                })
                
            except (ValueError, TypeError) as e:
                continue
    
    # Sort by datetime
    prices.sort(key=lambda x: x['datetime'])
    print(f"🔍 Total parsed prices: {len(prices)}")
    
    return prices

def format_price_data(prices, target_date):
    """Format price data for output"""
    if not prices:
        return None
    
    # Calculate statistics
    price_values = [p['price_eur_mwh'] for p in prices]
    avg_price = sum(price_values) / len(price_values)
    min_price = min(price_values)
    max_price = max(price_values)
    
    min_hour_data = next(p for p in prices if p['price_eur_mwh'] == min_price)
    max_hour_data = next(p for p in prices if p['price_eur_mwh'] == max_price)
    
    print(f"📊 Gemiddeld: €{avg_price:.2f}/MWh")
    print(f"📉 Minimum: €{min_price:.2f}/MWh om {min_hour_data['datetime'].strftime('%H:%M')}")
    print(f"📈 Maximum: €{max_price:.2f}/MWh om {max_hour_data['datetime'].strftime('%H:%M')}")
    
    # Create output format
    result = {
        'metadata': {
            'source': 'ENTSO-E Transparency Platform',
            'date': target_date.strftime('%Y-%m-%d'),
            'retrieved_at': datetime.now().isoformat(),
            'timezone': 'Europe/Brussels',
            'data_points': len(prices),
            'statistics': {
                'average_eur_mwh': round(avg_price, 2),
                'min_eur_mwh': round(min_price, 2),
                'max_eur_mwh': round(max_price, 2),
                'min_hour': min_hour_data['hour'],
                'max_hour': max_hour_data['hour']
            }
        },
        'prices': []
    }
    
    # Add price data
    for p in prices:
        result['prices'].append({
            'hour': p['hour'],
            'datetime': p['datetime'].isoformat(),
            'price_eur_mwh': round(p['price_eur_mwh'], 2),
            'price_eur_kwh': round(p['price_eur_kwh'], 4),
            'price_cent_kwh': round(p['price_eur_kwh'] * 100, 2)
        })
    
    return result

def save_data(data, target_date):
    """Save data to files"""
    if not data:
        return False
    
    date_str = target_date.strftime('%Y%m%d')
    
    # Save JSON
    json_filename = f'day_ahead_prices_{date_str}.json'
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 JSON saved: {json_filename}")
    
    # Save CSV
    df_data = []
    for price in data['prices']:
        df_data.append({
            'datetime': price['datetime'],
            'hour': price['hour'],
            'price_eur_mwh': price['price_eur_mwh'],
            'price_eur_kwh': price['price_eur_kwh'],
            'price_cent_kwh': price['price_cent_kwh']
        })
    
    if df_data:
        df = pd.DataFrame(df_data)
        csv_filename = f'day_ahead_prices_{date_str}.csv'
        df.to_csv(csv_filename, index=False)
        print(f"💾 CSV saved: {csv_filename}")
    
    # Save latest data
    with open('latest.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 Latest data saved: latest.json")
    
    return True

def main():
    """Main function - try recent dates until we find data"""
    print("🇧🇪 Belgian Day-Ahead Price Scraper (ENTSO-E)")
    print("=" * 50)
    
    # Try several recent dates
    base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Try today and previous few days (more likely to have data)
    for days_back in range(0, 7):  # Try today back to 6 days ago
        target_date = base_date - timedelta(days=days_back)
        
        # Skip weekends for day-ahead markets (usually no trading)
        if target_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            continue
        
        print(f"\n🎯 Trying: {target_date.strftime('%Y-%m-%d %A')}")
        
        data = fetch_day_ahead_prices(target_date)
        
        if data:
            success = save_data(data, target_date)
            if success:
                print(f"\n✅ Success! Data voor {target_date.strftime('%d/%m/%Y')} opgehaald")
                return  # Exit successfully
        else:
            print(f"❌ Geen data voor {target_date.strftime('%Y-%m-%d')}")
    
    print("\n❌ Geen data gevonden voor recente werkdagen")
    print("💡 ENTSO-E service mogelijk tijdelijk niet beschikbaar")
    sys.exit(1)

if __name__ == "__main__":
    main()
