#!/usr/bin/env python3
"""
Belgian Day-Ahead Price Scraper for machinery repository
Uses ENTSO-E Transparency Platform instead of broken Luminus API

This script maintains compatibility with the existing GitHub Actions workflow
while using a more reliable data source.
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
ENTSOE_BASE_URL = 'https://transparency.entsoe.eu/api'
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
        print("5. Zie README.md voor details")
        sys.exit(1)
    
    return ENTSOE_TOKEN

def fetch_day_ahead_prices(target_date=None):
    """
    Fetch day-ahead prices from ENTSO-E for a specific date
    
    Args:
        target_date: datetime object for delivery date (defaults to tomorrow)
    
    Returns:
        dict: Price data in format compatible with original machinery workflow
    """
    token = get_entsoe_token()
    
    # Default to tomorrow's prices
    if target_date is None:
        target_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
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
        response = requests.get(ENTSOE_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        
        # Parse XML response
        root = ET.fromstring(response.content)
        prices = parse_entsoe_response(root, target_date)
        
        if not prices:
            print("❌ Geen prijsdata gevonden")
            return None
        
        print(f"✅ {len(prices)} uurprijzen opgehaald")
        return format_price_data(prices, target_date)
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP fout: {e}")
        if e.response.status_code == 401:
            print("🔑 Controleer je ENTSOE_TOKEN")
        return None
    except Exception as e:
        print(f"❌ Onverwachte fout: {e}")
        return None

def parse_entsoe_response(root, target_date):
    """Parse ENTSO-E XML response"""
    prices = []
    namespaces = {'ns': 'urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0'}
    
    for time_series in root.findall('.//ns:TimeSeries', namespaces):
        period = time_series.find('.//ns:Period', namespaces)
        if period is not None:
            start_time_elem = period.find('ns:timeInterval/ns:start', namespaces)
            if start_time_elem is not None:
                start_time = datetime.fromisoformat(start_time_elem.text.replace('Z', '+00:00'))
                
                for point in period.findall('ns:Point', namespaces):
                    position = int(point.find('ns:position', namespaces).text)
                    price = float(point.find('ns:price.amount', namespaces).text)
                    
                    # Calculate timestamp (position 1 = start_time)
                    hour_timestamp = start_time + timedelta(hours=position-1)
                    
                    # Convert to local Belgian time (CET/CEST)
                    local_time = hour_timestamp.astimezone()
                    
                    prices.append({
                        'datetime': local_time,
                        'hour': position,
                        'price_eur_mwh': price,
                        'price_eur_kwh': price / 1000
                    })
    
    return sorted(prices, key=lambda x: x['datetime'])

def format_price_data(prices, target_date):
    """Format price data to match original machinery output format"""
    
    # Calculate statistics
    price_values = [p['price_eur_mwh'] for p in prices]
    avg_price = sum(price_values) / len(price_values)
    min_price = min(price_values)
    max_price = max(price_values)
    
    min_hour = next(p for p in prices if p['price_eur_mwh'] == min_price)
    max_hour = next(p for p in prices if p['price_eur_mwh'] == max_price)
    
    print(f"📊 Gemiddeld: €{avg_price:.2f}/MWh")
    print(f"📉 Minimum: €{min_price:.2f}/MWh om {min_hour['datetime'].strftime('%H:%M')}")
    print(f"📈 Maximum: €{max_price:.2f}/MWh om {max_hour['datetime'].strftime('%H:%M')}")
    
    # Create output format compatible with original workflow
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
                'min_hour': min_hour['hour'],
                'max_hour': max_hour['hour']
            }
        },
        'prices': []
    }
    
    # Add hourly price data
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
    """Save data in multiple formats for compatibility"""
    if not data:
        return False
    
    date_str = target_date.strftime('%Y%m%d')
    
    # Save JSON (main format for web display)
    json_filename = f'day_ahead_prices_{date_str}.json'
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 JSON opgeslagen: {json_filename}")
    
    # Save CSV for data analysis
    df_data = []
    for price in data['prices']:
        df_data.append({
            'datetime': price['datetime'],
            'hour': price['hour'],
            'price_eur_mwh': price['price_eur_mwh'],
            'price_eur_kwh': price['price_eur_kwh'],
            'price_cent_kwh': price['price_cent_kwh']
        })
    
    df = pd.DataFrame(df_data)
    csv_filename = f'day_ahead_prices_{date_str}.csv'
    df.to_csv(csv_filename, index=False)
    print(f"💾 CSV opgeslagen: {csv_filename}")
    
    # Save as latest.json for web display
    with open('latest.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 Latest data opgeslagen: latest.json")
    
    return True

def main():
    """Main function for GitHub Actions compatibility"""
    print("🇧🇪 Belgian Day-Ahead Price Scraper (ENTSO-E)")
    print("=" * 50)
    
    try:
        # Fetch tomorrow's prices (typical use case)
        tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        data = fetch_day_ahead_prices(tomorrow)
        
        if data:
            success = save_data(data, tomorrow)
            if success:
                print("✅ Data succesvol opgehaald en opgeslagen!")
                print("🌐 Klaar voor GitHub Pages weergave")
            else:
                print("❌ Fout bij opslaan data")
                sys.exit(1)
        else:
            print("❌ Geen data opgehaald")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Kritieke fout: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
