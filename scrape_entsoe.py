#!/usr/bin/env python3
"""
Belgian Day-Ahead Price Scraper for machinery repository (DEBUG VERSION)
Uses ENTSO-E Transparency Platform with enhanced error handling
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
    Fetch day-ahead prices from ENTSO-E with enhanced error handling
    """
    token = get_entsoe_token()
    
    # Default to tomorrow's prices, but if tomorrow is weekend, try today or next Monday
    if target_date is None:
        target_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        # If tomorrow is too far in future, try today
        if target_date > datetime.now(timezone.utc) + timedelta(days=2):
            target_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # ENTSO-E uses UTC timestamps
    start_time = target_date.replace(tzinfo=timezone.utc)
    end_time = start_time + timedelta(days=1)
    
    # Format for ENTSO-E API
    start_str = start_time.strftime('%Y%m%d%H%M')
    end_str = end_time.strftime('%Y%m%d%H%M')
    
    print(f"🔌 Ophalen dag-vooruit prijzen voor {target_date.strftime('%d/%m/%Y')}...")
    print(f"🕐 Periode: {start_str} tot {end_str}")
    
    params = {
        'securityToken': token,
        'documentType': 'A44',  # Day-ahead prices
        'in_Domain': BELGIUM_DOMAIN,
        'out_Domain': BELGIUM_DOMAIN,
        'periodStart': start_str,
        'periodEnd': end_str
    }
    
    print(f"🌐 API URL: {ENTSOE_BASE_URL}")
    print(f"🔑 Token (first 10 chars): {token[:10]}...")
    
    try:
        response = requests.get(ENTSOE_BASE_URL, params=params, timeout=30)
        
        print(f"📡 HTTP Status: {response.status_code}")
        print(f"📄 Content-Type: {response.headers.get('content-type', 'unknown')}")
        print(f"📏 Response length: {len(response.content)} bytes")
        
        if response.status_code == 401:
            print("❌ 401 Unauthorized - Controleer je ENTSO-E token")
            print("💡 Ga naar transparency.entsoe.eu → Account Settings → Web API → Request token")
            return None
        elif response.status_code == 400:
            print("❌ 400 Bad Request - Ongeldige parameters")
            print("💡 Mogelijk zijn er geen prijzen beschikbaar voor deze datum")
            return None
        elif response.status_code != 200:
            print(f"❌ HTTP {response.status_code}: {response.reason}")
            print(f"📄 Response body preview: {response.text[:500]}")
            return None
            
        response.raise_for_status()
        
        # Debug: show first part of response
        response_text = response.text
        print(f"📜 XML Response preview (first 300 chars):")
        print(response_text[:300] + "..." if len(response_text) > 300 else response_text)
        
        # Check if response looks like XML
        if not response_text.strip().startswith('<?xml'):
            print("⚠️ Response does not start with XML declaration")
            if 'html' in response_text.lower()[:100]:
                print("❌ Response appears to be HTML, not XML")
                print("💡 This might indicate an API error or authentication issue")
                return None
        
        # Try to parse XML with better error handling
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            print(f"❌ XML Parse Error: {e}")
            print("📄 Response content around error:")
            
            # Try to show context around the error
            lines = response_text.split('\n')
            if hasattr(e, 'lineno') and e.lineno:
                start_line = max(0, e.lineno - 3)
                end_line = min(len(lines), e.lineno + 3)
                for i in range(start_line, end_line):
                    marker = " >>> " if i + 1 == e.lineno else "     "
                    print(f"{marker}{i+1:3d}: {lines[i]}")
            return None
        
        # Parse the XML response
        prices = parse_entsoe_response(root, target_date)
        
        if not prices:
            print("❌ Geen prijsdata gevonden in XML response")
            # Debug: show XML structure
            print("🔍 XML root tag:", root.tag)
            print("🔍 XML namespaces:", root.nsmap if hasattr(root, 'nsmap') else 'unknown')
            
            # Look for error messages in XML
            for elem in root.iter():
                if 'error' in elem.tag.lower() or 'message' in elem.tag.lower():
                    print(f"🔍 Found potential error element: {elem.tag} = {elem.text}")
            
            return None
        
        print(f"✅ {len(prices)} uurprijzen opgehaald")
        return format_price_data(prices, target_date)
        
    except requests.exceptions.Timeout:
        print("❌ API timeout - probeer later opnieuw")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ Verbindingsfout - controleer internetverbinding")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Request fout: {e}")
        return None
    except Exception as e:
        print(f"❌ Onverwachte fout: {e}")
        import traceback
        traceback.print_exc()
        return None

def parse_entsoe_response(root, target_date):
    """Parse ENTSO-E XML response with debug info"""
    prices = []
    namespaces = {'ns': 'urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0'}
    
    print("🔍 Parsing XML response...")
    print(f"🔍 Root element: {root.tag}")
    
    # Find all TimeSeries elements
    time_series_elements = root.findall('.//ns:TimeSeries', namespaces)
    print(f"🔍 Found {len(time_series_elements)} TimeSeries elements")
    
    if not time_series_elements:
        # Try without namespace
        time_series_elements = root.findall('.//TimeSeries')
        print(f"🔍 Without namespace: found {len(time_series_elements)} TimeSeries elements")
    
    for i, time_series in enumerate(time_series_elements):
        print(f"🔍 Processing TimeSeries {i+1}")
        
        period = time_series.find('.//ns:Period', namespaces)
        if period is None:
            period = time_series.find('.//Period')
        
        if period is not None:
            start_time_elem = period.find('ns:timeInterval/ns:start', namespaces)
            if start_time_elem is None:
                start_time_elem = period.find('.//start')
            
            if start_time_elem is not None:
                start_time_text = start_time_elem.text
                print(f"🔍 Start time: {start_time_text}")
                
                try:
                    start_time = datetime.fromisoformat(start_time_text.replace('Z', '+00:00'))
                except Exception as e:
                    print(f"❌ Error parsing start time: {e}")
                    continue
                
                points = period.findall('ns:Point', namespaces)
                if not points:
                    points = period.findall('.//Point')
                
                print(f"🔍 Found {len(points)} price points")
                
                for point in points:
                    position_elem = point.find('ns:position', namespaces)
                    if position_elem is None:
                        position_elem = point.find('.//position')
                    
                    price_elem = point.find('ns:price.amount', namespaces)
                    if price_elem is None:
                        price_elem = point.find('.//price.amount')
                    
                    if position_elem is not None and price_elem is not None:
                        try:
                            position = int(position_elem.text)
                            price = float(price_elem.text)
                            
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
                        except (ValueError, TypeError) as e:
                            print(f"❌ Error parsing point data: {e}")
                            continue
    
    print(f"🔍 Total prices parsed: {len(prices)}")
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
    """Main function with fallback dates"""
    print("🇧🇪 Belgian Day-Ahead Price Scraper (ENTSO-E DEBUG)")
    print("=" * 55)
    
    try:
        # Try tomorrow first
        tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        print(f"🎯 Trying tomorrow: {tomorrow.strftime('%Y-%m-%d')}")
        
        data = fetch_day_ahead_prices(tomorrow)
        
        if not data:
            # Fallback to today
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            print(f"🎯 Fallback to today: {today.strftime('%Y-%m-%d')}")
            data = fetch_day_ahead_prices(today)
            target_date = today
        else:
            target_date = tomorrow
        
        if not data:
            # Fallback to yesterday (should always have data)
            yesterday = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            print(f"🎯 Last resort - yesterday: {yesterday.strftime('%Y-%m-%d')}")
            data = fetch_day_ahead_prices(yesterday)
            target_date = yesterday
        
        if data:
            success = save_data(data, target_date)
            if success:
                print("✅ Data succesvol opgehaald en opgeslagen!")
                print("🌐 Klaar voor GitHub Pages weergave")
            else:
                print("❌ Fout bij opslaan data")
                sys.exit(1)
        else:
            print("❌ Geen data opgehaald voor alle geprobeerde datums")
            print("💡 Controleer:")
            print("   - ENTSO-E token geldigheid")
            print("   - Internetverbinding") 
            print("   - ENTSO-E API status")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Kritieke fout: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
