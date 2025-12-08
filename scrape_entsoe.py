#!/usr/bin/env python3
"""
Belgian Day-Ahead Price Scraper - FIXED ENTSO-E VERSION
Correct API parameters and endpoint for ENTSO-E Transparency Platform
"""

import os
import sys
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# ENTSO-E API Configuration - CORRECTED
ENTSOE_TOKEN = os.getenv('ENTSOE_TOKEN', '')
# Correct ENTSO-E REST API endpoint
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
        print("5. Zie README.md voor details")
        sys.exit(1)
    
    return ENTSOE_TOKEN

def fetch_day_ahead_prices(target_date=None):
    """
    Fetch day-ahead prices from ENTSO-E with CORRECTED API parameters
    """
    token = get_entsoe_token()
    
    # Default to today's prices (more likely to be available)
    if target_date is None:
        target_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # ENTSO-E uses UTC timestamps in YYYYMMDDHHMM format
    start_time = target_date.replace(tzinfo=timezone.utc)
    end_time = start_time + timedelta(days=1)
    
    # Format for ENTSO-E API (YYYYMMDDHHmm)
    start_str = start_time.strftime('%Y%m%d%H%M')
    end_str = end_time.strftime('%Y%m%d%H%M')
    
    print(f"🔌 Ophalen dag-vooruit prijzen voor {target_date.strftime('%d/%m/%Y')}...")
    print(f"🕐 UTC periode: {start_str} tot {end_str}")
    
    # CORRECTED API parameters according to ENTSO-E documentation
    params = {
        'securityToken': token,
        'documentType': 'A44',  # Day-ahead prices
        'in_Domain': BELGIUM_DOMAIN,  # Belgium bidding zone
        'out_Domain': BELGIUM_DOMAIN,  # Belgium bidding zone  
        'periodStart': start_str,
        'periodEnd': end_str
    }
    
    print(f"🌐 API URL: {ENTSOE_API_URL}")
    print(f"🔑 Token (laatste 4 chars): ...{token[-4:]}")
    print(f"📋 Parameters: {dict((k, v if k != 'securityToken' else f'***{v[-4:]}') for k, v in params.items())}")
    
    try:
        response = requests.get(ENTSOE_API_URL, params=params, timeout=30)
        
        print(f"📡 HTTP Status: {response.status_code}")
        print(f"📄 Content-Type: {response.headers.get('content-type', 'unknown')}")
        print(f"📏 Response length: {len(response.content)} bytes")
        
        # Handle specific HTTP errors
        if response.status_code == 401:
            print("❌ 401 Unauthorized")
            print("🔑 Token probleem - controleer of:")
            print("   - Token correct is gekopieerd (geen extra spaties)")
            print("   - Token actief is op transparency.entsoe.eu")
            print("   - Account geactiveerd is")
            return None
        elif response.status_code == 400:
            print("❌ 400 Bad Request")
            print("📄 Response body:", response.text[:500])
            print("💡 Mogelijk zijn parameters incorrect of geen data beschikbaar")
            return None
        elif response.status_code == 429:
            print("❌ 429 Rate Limited - te veel requests")
            print("💡 Wacht even en probeer opnieuw")
            return None
        elif response.status_code != 200:
            print(f"❌ HTTP {response.status_code}: {response.reason}")
            print(f"📄 Response preview: {response.text[:300]}")
            return None
        
        # Check content type
        content_type = response.headers.get('content-type', '').lower()
        if 'xml' not in content_type and 'text' not in content_type:
            print(f"⚠️ Unexpected content type: {content_type}")
        
        # Get response text
        response_text = response.text.strip()
        print(f"📜 Response preview (first 200 chars):")
        print(response_text[:200] + "..." if len(response_text) > 200 else response_text)
        
        # Check for HTML response (indicates API error)
        if response_text.startswith('<!DOCTYPE html') or response_text.startswith('<html'):
            print("❌ Received HTML response instead of XML")
            print("💡 This usually means:")
            print("   - API endpoint is wrong")
            print("   - Parameters are incorrect")
            print("   - Authentication failed silently")
            return None
        
        # Check for ENTSO-E error messages
        if 'No matching data found' in response_text:
            print("📭 No matching data found voor deze datum")
            print("💡 Probeer een andere datum of controleer parameters")
            return None
        
        if not response_text.startswith('<?xml'):
            print("⚠️ Response does not start with XML declaration")
            print(f"⚠️ Starts with: {response_text[:50]}")
        
        # Try to parse XML
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            print(f"❌ XML Parse Error: {e}")
            print("📄 Raw response:")
            print(response_text)
            return None
        
        # Parse the XML response
        prices = parse_entsoe_response(root, target_date)
        
        if not prices:
            print("❌ Geen prijsdata gevonden in XML response")
            # Debug XML structure
            print(f"🔍 Root element: {root.tag}")
            
            # Look for error elements
            for elem in root.iter():
                if 'error' in elem.tag.lower() or 'reason' in elem.tag.lower():
                    print(f"🔍 Error element: {elem.tag} = {elem.text}")
            
            return None
        
        print(f"✅ {len(prices)} uurprijzen succesvol opgehaald")
        return format_price_data(prices, target_date)
        
    except requests.exceptions.Timeout:
        print("❌ API timeout na 30 seconden")
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
    """Parse ENTSO-E XML response"""
    prices = []
    
    # ENTSO-E XML namespace
    ns = {'ns': 'urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0'}
    
    print("🔍 Parsing XML response...")
    print(f"🔍 Root element: {root.tag}")
    
    # Find TimeSeries elements
    time_series_list = root.findall('.//ns:TimeSeries', ns)
    print(f"🔍 Found {len(time_series_list)} TimeSeries elements")
    
    for ts_idx, time_series in enumerate(time_series_list):
        print(f"🔍 Processing TimeSeries {ts_idx + 1}")
        
        # Find Period element
        period = time_series.find('.//ns:Period', ns)
        if period is None:
            print(f"⚠️ No Period found in TimeSeries {ts_idx + 1}")
            continue
        
        # Get time interval
        time_interval = period.find('ns:timeInterval', ns)
        if time_interval is None:
            print(f"⚠️ No timeInterval found in Period")
            continue
            
        start_elem = time_interval.find('ns:start', ns)
        if start_elem is None:
            print(f"⚠️ No start time found in timeInterval")
            continue
        
        start_time_text = start_elem.text
        print(f"🔍 Period start time: {start_time_text}")
        
        try:
            # Parse start time
            start_time = datetime.fromisoformat(start_time_text.replace('Z', '+00:00'))
        except ValueError as e:
            print(f"❌ Error parsing start time '{start_time_text}': {e}")
            continue
        
        # Find all Point elements
        points = period.findall('ns:Point', ns)
        print(f"🔍 Found {len(points)} price points in this period")
        
        for point in points:
            position_elem = point.find('ns:position', ns)
            price_elem = point.find('ns:price.amount', ns)
            
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
                print(f"⚠️ Error parsing point data: {e}")
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
    
    print(f"📊 Statistieken:")
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
    """Main function with multiple date attempts"""
    print("🇧🇪 Belgian Day-Ahead Price Scraper (ENTSO-E FIXED)")
    print("=" * 55)
    
    # Try different dates to find available data
    dates_to_try = []
    base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Add several days to try
    for days_offset in [0, -1, -2, 1]:  # Today, yesterday, 2 days ago, tomorrow
        dates_to_try.append(base_date + timedelta(days=days_offset))
    
    for attempt, target_date in enumerate(dates_to_try, 1):
        print(f"\n🎯 Attempt {attempt}: {target_date.strftime('%Y-%m-%d %A')}")
        
        data = fetch_day_ahead_prices(target_date)
        
        if data:
            success = save_data(data, target_date)
            if success:
                print("\n✅ Data succesvol opgehaald en opgeslagen!")
                print("🌐 Klaar voor weergave en analyse")
                return  # Exit successfully
            else:
                print("❌ Fout bij opslaan data")
        else:
            print(f"❌ Geen data voor {target_date.strftime('%Y-%m-%d')}")
    
    print("\n❌ Geen data opgehaald voor alle geprobeerde datums")
    print("💡 Controleer ENTSO-E token en probeer later opnieuw")
    sys.exit(1)

if __name__ == "__main__":
    main()
