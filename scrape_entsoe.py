#!/usr/bin/env python3
"""
Belgian Day-Ahead Price Scraper - CORRECTED VERSION
Fixes data accuracy issues and improves ENTSO-E API handling
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

def validate_price_data(prices):
    """Validate price data for suspicious values"""
    if not prices:
        return False, "No prices found"
    
    price_values = [p['price_eur_mwh'] for p in prices]
    
    # Check for reasonable price ranges (Belgian market typically 0-300 €/MWh)
    max_price = max(price_values)
    min_price = min(price_values)
    avg_price = sum(price_values) / len(price_values)
    
    # Validation checks
    issues = []
    
    if max_price > 500:
        issues.append(f"Suspiciously high price: €{max_price:.2f}/MWh")
    
    if min_price < 0:
        issues.append(f"Negative price detected: €{min_price:.2f}/MWh")
    
    if max_price > 10 * avg_price and max_price > 100:
        issues.append(f"Price spike detected: €{max_price:.2f}/MWh (avg: €{avg_price:.2f}/MWh)")
    
    if len(set(price_values)) < 5:
        issues.append("Too few unique prices - possible data corruption")
    
    if len(prices) not in [24, 48, 96]:  # hourly, half-hourly, quarter-hourly
        issues.append(f"Unexpected number of price points: {len(prices)}")
    
    if issues:
        print("⚠️  Data validation warnings:")
        for issue in issues:
            print(f"   - {issue}")
        
        # For severe issues, reject the data
        if max_price > 1000 or min_price < -100:
            return False, "Extreme price values detected"
    
    return True, "Data validation passed"

def fetch_day_ahead_prices(target_date=None):
    """Fetch day-ahead prices from ENTSO-E with improved data validation"""
    token = get_entsoe_token()
    
    # Default to today's prices (more likely to be available and accurate)
    if target_date is None:
        target_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # ENTSO-E uses UTC timestamps
    start_time = target_date.replace(tzinfo=timezone.utc)
    end_time = start_time + timedelta(days=1)
    
    # Format for ENTSO-E API
    start_str = start_time.strftime('%Y%m%d%H%M')
    end_str = end_time.strftime('%Y%m%d%H%M')
    
    print(f"🔌 Ophalen dag-vooruit prijzen voor {target_date.strftime('%d/%m/%Y')}...")
    print(f"🕐 UTC periode: {start_str} tot {end_str}")
    
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
        print(f"📏 Response length: {len(response.content)} bytes")
        
        if response.status_code == 503:
            print("⚠️ ENTSO-E service tijdelijk niet beschikbaar")
            return None
        elif response.status_code == 400:
            print("❌ 400 Bad Request - mogelijk geen data voor deze datum")
            return None
        elif response.status_code != 200:
            print(f"❌ HTTP {response.status_code}: {response.reason}")
            return None
        
        # Parse XML
        try:
            root = ET.fromstring(response.content)
            print(f"🔍 XML parsed - root: {root.tag}")
        except ET.ParseError as e:
            print(f"❌ XML Parse Error: {e}")
            return None
        
        # Check for ENTSO-E error messages in XML
        error_text = response.text.lower()
        if 'no matching data found' in error_text:
            print("📭 ENTSO-E: No matching data found voor deze periode")
            return None
        
        # Parse the XML response
        prices = parse_entsoe_response(root, target_date)
        
        if not prices:
            print("❌ Geen prijsdata gevonden in XML")
            return None
        
        # Validate the price data
        is_valid, validation_msg = validate_price_data(prices)
        print(f"🔍 Data validatie: {validation_msg}")
        
        if not is_valid:
            print("❌ Data validatie gefaald - data wordt verworpen")
            return None
        
        print(f"✅ {len(prices)} prijspunten succesvol opgehaald en gevalideerd")
        return format_price_data(prices, target_date)
        
    except Exception as e:
        print(f"❌ Onverwachte fout: {e}")
        return None

def parse_entsoe_response(root, target_date):
    """Parse ENTSO-E XML response with improved handling and duplicate prevention"""
    prices = []
    
    # Try to detect namespace automatically
    root_tag = root.tag
    if '}' in root_tag:
        namespace_uri = root_tag.split('}')[0][1:]
        ns = {'ns': namespace_uri}
        print(f"🔍 Detected namespace: {namespace_uri}")
    else:
        ns = {}
        print("🔍 No namespace detected")
    
    # Find TimeSeries elements
    if ns:
        time_series_list = root.findall('.//ns:TimeSeries', ns)
    else:
        time_series_list = [elem for elem in root.iter() if elem.tag.endswith('TimeSeries')]
    
    print(f"🔍 Found {len(time_series_list)} TimeSeries elements")
    
    # Convert target date to compare with periods
    target_date_start = target_date.replace(tzinfo=timezone.utc)
    target_date_end = target_date_start + timedelta(days=1)
    
    collected_points = {}  # Use dict to automatically handle duplicates by timestamp
    
    for ts_idx, time_series in enumerate(time_series_list):
        print(f"🔍 Processing TimeSeries {ts_idx + 1}")
        
        # Find Period elements
        if ns:
            periods = time_series.findall('.//ns:Period', ns)
        else:
            periods = [elem for elem in time_series.iter() if elem.tag.endswith('Period')]
        
        print(f"🔍 Found {len(periods)} periods in TimeSeries {ts_idx + 1}")
        
        for period_idx, period in enumerate(periods):
            # Get start time
            start_time_elem = None
            if ns:
                start_time_elem = period.find('.//ns:start', ns)
            
            if start_time_elem is None:
                # Try without namespace
                for elem in period.iter():
                    if elem.tag.endswith('start'):
                        start_time_elem = elem
                        break
            
            if start_time_elem is None:
                print(f"⚠️ No start time found in period {period_idx + 1}")
                continue
            
            start_time_text = start_time_elem.text
            
            try:
                period_start = datetime.fromisoformat(start_time_text.replace('Z', '+00:00'))
            except ValueError:
                print(f"❌ Could not parse start time: {start_time_text}")
                continue
            
            # Check if this period is for our target date
            if not (target_date_start <= period_start < target_date_end):
                print(f"⏭️ Skipping period {period_idx + 1} - outside target date range")
                print(f"   Period start: {period_start}")
                print(f"   Target range: {target_date_start} to {target_date_end}")
                continue
            
            print(f"✅ Processing period {period_idx + 1} - start: {period_start}")
            
            # Get resolution
            resolution_elem = None
            if ns:
                resolution_elem = period.find('.//ns:resolution', ns)
            
            if resolution_elem is None:
                for elem in period.iter():
                    if elem.tag.endswith('resolution'):
                        resolution_elem = elem
                        break
            
            resolution = resolution_elem.text if resolution_elem is not None else 'PT60M'
            print(f"🔍 Resolution: {resolution}")
            
            # Calculate time delta based on resolution
            if resolution == 'PT15M':
                time_delta = timedelta(minutes=15)
            elif resolution == 'PT30M':
                time_delta = timedelta(minutes=30)
            else:  # PT60M or default
                time_delta = timedelta(hours=1)
            
            # Find Point elements
            if ns:
                points = period.findall('.//ns:Point', ns)
            else:
                points = [elem for elem in period.iter() if elem.tag.endswith('Point')]
            
            print(f"🔍 Found {len(points)} points in this period")
            
            for point in points:
                # Get position and price
                position_elem = price_elem = None
                
                for child in point:
                    if child.tag.endswith('position'):
                        position_elem = child
                    elif child.tag.endswith('price.amount'):
                        price_elem = child
                
                if position_elem is None or price_elem is None:
                    continue
                
                try:
                    position = int(position_elem.text)
                    price = float(price_elem.text)
                    
                    # Calculate exact timestamp
                    point_time = period_start + (time_delta * (position - 1))
                    
                    # Double-check this point is within our target date
                    if not (target_date_start <= point_time < target_date_end):
                        print(f"⏭️ Skipping point at {point_time} - outside target date")
                        continue
                    
                    # Convert to Belgian local time
                    local_time = point_time.astimezone()
                    
                    # Use timestamp as key to prevent duplicates
                    timestamp_key = local_time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    if timestamp_key in collected_points:
                        print(f"⚠️ Duplicate timestamp detected: {timestamp_key} - keeping first occurrence")
                        continue
                    
                    collected_points[timestamp_key] = {
                        'datetime': local_time,
                        'position': position,
                        'price_eur_mwh': price,
                        'price_eur_kwh': price / 1000,
                        'period_start': period_start,
                        'resolution': resolution
                    }
                    
                except (ValueError, TypeError) as e:
                    print(f"❌ Error parsing point: {e}")
                    continue
    
    # Convert dict to sorted list
    all_points = list(collected_points.values())
    all_points.sort(key=lambda x: x['datetime'])
    
    # Add sequential hour numbers for display
    for i, point in enumerate(all_points, 1):
        point['hour'] = i
    
    print(f"🔍 Final unique points after deduplication: {len(all_points)}")
    
    # Final validation: ensure we have exactly one day's worth of data
    if len(all_points) > 0:
        first_time = all_points[0]['datetime']
        last_time = all_points[-1]['datetime']
        time_span = last_time - first_time
        print(f"🔍 Data time span: {first_time.strftime('%H:%M')} to {last_time.strftime('%H:%M')} ({time_span})")
        
        # Check if we have more than 24 hours of data
        if time_span > timedelta(hours=25):  # Allow some tolerance
            print(f"⚠️ Warning: Data spans more than 24 hours ({time_span})")
            
            # Filter to keep only data for the target date
            target_date_local = target_date_start.astimezone()
            filtered_points = []
            
            for point in all_points:
                if point['datetime'].date() == target_date_local.date():
                    filtered_points.append(point)
            
            print(f"🔍 After date filtering: {len(filtered_points)} points")
            all_points = filtered_points
            
            # Re-assign hour numbers
            for i, point in enumerate(all_points, 1):
                point['hour'] = i
    
    return all_points

def format_price_data(prices, target_date):
    """Format price data with enhanced validation"""
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
    print(f"   Gemiddeld: €{avg_price:.2f}/MWh")
    print(f"   Minimum: €{min_price:.2f}/MWh om {min_hour_data['datetime'].strftime('%H:%M')}")
    print(f"   Maximum: €{max_price:.2f}/MWh om {max_hour_data['datetime'].strftime('%H:%M')}")
    print(f"   Spread: €{max_price - min_price:.2f}/MWh")
    
    # Create output format
    result = {
        'metadata': {
            'source': 'ENTSO-E Transparency Platform',
            'date': target_date.strftime('%Y-%m-%d'),
            'retrieved_at': datetime.now().isoformat(),
            'timezone': 'Europe/Brussels',
            'data_points': len(prices),
            'resolution': prices[0].get('resolution', 'PT60M') if prices else 'PT60M',
            'statistics': {
                'average_eur_mwh': round(avg_price, 2),
                'min_eur_mwh': round(min_price, 2),
                'max_eur_mwh': round(max_price, 2),
                'min_hour': min_hour_data['hour'],
                'max_hour': max_hour_data['hour'],
                'price_spread': round(max_price - min_price, 2)
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
    """Main function with enhanced error handling and multiple date attempts"""
    print("🇧🇪 Belgian Day-Ahead Price Scraper (CORRECTED VERSION)")
    print("=" * 60)
    
    # Try several dates to find valid data
    base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Try: today, yesterday, day before yesterday, tomorrow
    dates_to_try = [
        (base_date, "today"),
        (base_date - timedelta(days=1), "yesterday"), 
        (base_date - timedelta(days=2), "2 days ago"),
        (base_date + timedelta(days=1), "tomorrow")
    ]
    
    for target_date, date_label in dates_to_try:
        # Skip weekends for day-ahead markets (usually no trading)
        if target_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            print(f"⏭️  Skipping {date_label} ({target_date.strftime('%Y-%m-%d')}) - weekend")
            continue
        
        print(f"\n🎯 Attempting {date_label}: {target_date.strftime('%Y-%m-%d %A')}")
        
        data = fetch_day_ahead_prices(target_date)
        
        if data:
            success = save_data(data, target_date)
            if success:
                stats = data['metadata']['statistics']
                print(f"\n✅ SUCCESS! Data voor {target_date.strftime('%d/%m/%Y')} opgehaald")
                print(f"📊 {data['metadata']['data_points']} prijspunten")
                print(f"📊 €{stats['min_eur_mwh']}-{stats['max_eur_mwh']}/MWh (spread: €{stats['price_spread']}/MWh)")
                return  # Exit successfully
            else:
                print("❌ Fout bij opslaan data")
        else:
            print(f"❌ Geen geldige data voor {date_label}")
    
    print("\n❌ Geen geldige data gevonden voor alle geprobeerde datums")
    print("💡 Mogelijke oorzaken:")
    print("   - ENTSO-E service tijdelijk niet beschikbaar")
    print("   - Token problemen")
    print("   - Weekend/feestdag (geen day-ahead trading)")
    sys.exit(1)

if __name__ == "__main__":
    main()
