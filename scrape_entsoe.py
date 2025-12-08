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
    
    # Default to today's prices (Belgian local time)
    if target_date is None:
        # Get today in Belgian timezone
        belgian_tz = timezone(timedelta(hours=1))  # CET (UTC+1)
        target_date = datetime.now(belgian_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Convert target date to UTC for ENTSO-E API
    # For Belgian date 2025-12-08 00:00 CET, we need UTC period:
    # - Start: 2025-12-07 23:00 UTC 
    # - End:   2025-12-08 23:00 UTC
    
    if target_date.tzinfo is None:
        # Assume target_date is in Belgian time if no timezone specified
        belgian_tz = timezone(timedelta(hours=1))
        target_date = target_date.replace(tzinfo=belgian_tz)
    
    # Convert Belgian date to UTC (this automatically handles the -1 hour offset)
    start_time_utc = target_date.astimezone(timezone.utc)
    end_time_utc = start_time_utc + timedelta(days=1)
    
    # Format for ENTSO-E API
    start_str = start_time_utc.strftime('%Y%m%d%H%M')
    end_str = end_time_utc.strftime('%Y%m%d%H%M')
    
    print(f"🔌 Ophalen dag-vooruit prijzen voor {target_date.strftime('%d/%m/%Y')} (Belgische tijd)")
    print(f"🕐 UTC periode: {start_str} tot {end_str}")
    print(f"🇧🇪 Belgische periode: {target_date.strftime('%Y-%m-%d 00:00')} tot {(target_date + timedelta(days=1)).strftime('%Y-%m-%d 00:00')}")
    
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
    """Parse ENTSO-E XML response with improved handling and proper resolution conversion"""
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
    
    # Convert target date for more flexible comparison
    target_date_utc = target_date.replace(tzinfo=timezone.utc)
    
    all_points = []  # Collect all valid points
    
    for ts_idx, time_series in enumerate(time_series_list):
        print(f"🔍 Processing TimeSeries {ts_idx + 1}")
        
        # Find Period elements
        if ns:
            periods = time_series.findall('.//ns:Period', ns)
        else:
            periods = [elem for elem in time_series.iter() if elem.tag.endswith('Period')]
        
        print(f"🔍 Found {len(periods)} periods in TimeSeries {ts_idx + 1}")
        
        for period_idx, period in enumerate(periods):
            # Get start and end time
            start_time_elem = end_time_elem = None
            
            if ns:
                interval = period.find('.//ns:timeInterval', ns)
                if interval is not None:
                    start_time_elem = interval.find('ns:start', ns)
                    end_time_elem = interval.find('ns:end', ns)
            
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
            
            # Get resolution first to calculate period span
            resolution_elem = None
            if ns:
                resolution_elem = period.find('.//ns:resolution', ns)
            
            if resolution_elem is None:
                for elem in period.iter():
                    if elem.tag.endswith('resolution'):
                        resolution_elem = elem
                        break
            
            resolution = resolution_elem.text if resolution_elem is not None else 'PT60M'
            
            # Calculate time delta based on resolution
            if resolution == 'PT15M':
                time_delta = timedelta(minutes=15)
            elif resolution == 'PT30M':
                time_delta = timedelta(minutes=30)
            else:  # PT60M or default
                time_delta = timedelta(hours=1)
            
            # Find Point elements to determine period span
            if ns:
                points = period.findall('.//ns:Point', ns)
            else:
                points = [elem for elem in period.iter() if elem.tag.endswith('Point')]
            
            if not points:
                print(f"⚠️ No points found in period {period_idx + 1}")
                continue
            
            # Calculate period end time
            period_end = period_start + (time_delta * len(points))
            
            # Convert to local time to check date coverage
            period_start_local = period_start.astimezone()
            period_end_local = period_end.astimezone()
            
            # Check if this period covers our target date (in local time)
            target_date_obj = target_date_utc.date()
            period_start_date = period_start_local.date()
            period_end_date = period_end_local.date()
            
            # Accept period if it covers the target date
            covers_target_date = (
                period_start_date <= target_date_obj <= period_end_date or
                target_date_obj == period_start_date or
                target_date_obj == period_end_date
            )
            
            if not covers_target_date:
                print(f"⏭️ Skipping period {period_idx + 1} - covers {period_start_date} to {period_end_date}, need {target_date_obj}")
                continue
            
            print(f"✅ Processing period {period_idx + 1}")
            print(f"   Period: {period_start_local.strftime('%Y-%m-%d %H:%M')} to {period_end_local.strftime('%Y-%m-%d %H:%M')}")
            print(f"   Resolution: {resolution} ({len(points)} points)")
            
            
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
                    
                    # Convert to Belgian local time
                    local_time = point_time.astimezone()
                    
                    # Check if this point falls on our target date (in local time)
                    local_date = local_time.date()
                    target_date_local = target_date_utc.date()
                    
                    if local_date == target_date_local:
                        all_points.append({
                            'datetime': local_time,
                            'position': position,
                            'price_eur_mwh': price,
                            'price_eur_kwh': price / 1000,
                            'period_start': period_start,
                            'resolution': resolution
                        })
                    else:
                        # Debug: show why points are being skipped
                        if len(all_points) < 5:  # Only show first few to avoid spam
                            print(f"   Skipping point {position}: {local_date} != {target_date_local}")
                    
                except (ValueError, TypeError) as e:
                    print(f"❌ Error parsing point: {e}")
                    continue
    
    print(f"🔍 Collected {len(all_points)} raw points")
    
    if not all_points:
        return []
    
    # Sort by datetime
    all_points.sort(key=lambda x: x['datetime'])
    
    # If we have high-resolution data (15min/30min), convert to hourly
    resolution = all_points[0]['resolution']
    if resolution in ['PT15M', 'PT30M']:
        print(f"🔄 Converting {resolution} data to hourly averages...")
        hourly_points = convert_to_hourly(all_points)
    else:
        print("ℹ️ Data is already hourly")
        hourly_points = all_points
    
    # Remove duplicates based on hour
    seen_hours = set()
    unique_points = []
    for point in hourly_points:
        hour_key = point['datetime'].strftime('%Y-%m-%d %H')
        if hour_key not in seen_hours:
            seen_hours.add(hour_key)
            unique_points.append(point)
        else:
            print(f"⚠️ Duplicate hour detected: {hour_key} - skipping")
    
    # Add sequential hour numbers for display
    for i, point in enumerate(unique_points, 1):
        point['hour'] = i
    
    print(f"🔍 Final unique hourly points: {len(unique_points)}")
    
    return unique_points

def convert_to_hourly(points):
    """Convert high-resolution data (15min/30min) to hourly averages"""
    if not points:
        return []
    
    hourly_data = {}
    
    for point in points:
        # Group by hour
        hour_key = point['datetime'].replace(minute=0, second=0, microsecond=0)
        
        if hour_key not in hourly_data:
            hourly_data[hour_key] = []
        
        hourly_data[hour_key].append(point['price_eur_mwh'])
    
    # Convert to hourly averages
    hourly_points = []
    for hour_time, prices in sorted(hourly_data.items()):
        avg_price = sum(prices) / len(prices)
        
        hourly_points.append({
            'datetime': hour_time,
            'price_eur_mwh': avg_price,
            'price_eur_kwh': avg_price / 1000,
            'resolution': 'PT60M',  # Now converted to hourly
            'data_points': len(prices)
        })
    
    print(f"🔄 Converted {len(points)} high-res points to {len(hourly_points)} hourly averages")
    return hourly_points

def find_cheapest_block(prices, block_hours=3):
    """Find the cheapest consecutive block of hours"""
    if len(prices) < block_hours:
        return None
    
    best_sum = float('inf')
    best_start_idx = 0
    
    # Try each possible consecutive block
    for i in range(len(prices) - block_hours + 1):
        block_sum = sum(prices[j]['price_eur_mwh'] for j in range(i, i + block_hours))
        
        if block_sum < best_sum:
            best_sum = block_sum
            best_start_idx = i
    
    # Get the block details
    block_prices = prices[best_start_idx:best_start_idx + block_hours]
    avg_price = best_sum / block_hours
    
    # Handle datetime - they might be datetime objects or ISO strings
    start_datetime = block_prices[0]['datetime']
    end_datetime = block_prices[-1]['datetime']
    
    # Convert to ISO strings if they're datetime objects
    if hasattr(start_datetime, 'isoformat'):
        start_datetime = start_datetime.isoformat()
    if hasattr(end_datetime, 'isoformat'):
        end_datetime = end_datetime.isoformat()
    
    return {
        'start_hour': block_prices[0]['hour'],
        'end_hour': block_prices[-1]['hour'],
        'start_time': start_datetime,
        'end_time': end_datetime,
        'hours': block_hours,
        'average_price': avg_price,
        'total_price': best_sum,
        'prices': [p['price_eur_mwh'] for p in block_prices]
    }

def format_price_data(prices, target_date):
    """Format price data with enhanced validation and cheapest blocks"""
    if not prices:
        return None
    
    # Calculate statistics
    price_values = [p['price_eur_mwh'] for p in prices]
    avg_price = sum(price_values) / len(price_values)
    min_price = min(price_values)
    max_price = max(price_values)
    
    min_hour_data = next(p for p in prices if p['price_eur_mwh'] == min_price)
    max_hour_data = next(p for p in prices if p['price_eur_mwh'] == max_price)
    
    # Find cheapest consecutive blocks
    cheapest_1h = find_cheapest_block(prices, 1)
    cheapest_2h = find_cheapest_block(prices, 2) 
    cheapest_3h = find_cheapest_block(prices, 3)
    cheapest_4h = find_cheapest_block(prices, 4)
    
    print(f"📊 Statistieken:")
    print(f"   Gemiddeld: €{avg_price:.2f}/MWh")
    print(f"   Minimum: €{min_price:.2f}/MWh om {min_hour_data['datetime'].strftime('%H:%M')}")
    print(f"   Maximum: €{max_price:.2f}/MWh om {max_hour_data['datetime'].strftime('%H:%M')}")
    print(f"   Spread: €{max_price - min_price:.2f}/MWh")
    
    if cheapest_3h:
        # Handle both datetime objects and ISO strings
        start_time_obj = cheapest_3h['start_time']
        end_time_obj = cheapest_3h['end_time']
        
        if hasattr(start_time_obj, 'strftime'):
            # It's already a datetime object
            start_time = start_time_obj.strftime('%H:%M')
            end_time = end_time_obj.strftime('%H:%M')
        else:
            # It's an ISO string
            start_time = datetime.fromisoformat(start_time_obj.replace('Z', '+00:00')).strftime('%H:%M')
            end_time = datetime.fromisoformat(end_time_obj.replace('Z', '+00:00')).strftime('%H:%M')
        
        print(f"💡 Goedkoopste 3-uur blok: {start_time}-{end_time} (avg: €{cheapest_3h['average_price']:.2f}/MWh)")
    
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
            },
            'cheapest_blocks': {
                '1_hour': {
                    'hour': cheapest_1h['start_hour'],
                    'time': cheapest_1h['start_time'],
                    'price': round(cheapest_1h['average_price'], 2)
                } if cheapest_1h else None,
                '2_hours': {
                    'start_hour': cheapest_2h['start_hour'],
                    'end_hour': cheapest_2h['end_hour'],
                    'start_time': cheapest_2h['start_time'],
                    'end_time': cheapest_2h['end_time'],
                    'average_price': round(cheapest_2h['average_price'], 2),
                    'hours': 2
                } if cheapest_2h else None,
                '3_hours': {
                    'start_hour': cheapest_3h['start_hour'],
                    'end_hour': cheapest_3h['end_hour'],
                    'start_time': cheapest_3h['start_time'],
                    'end_time': cheapest_3h['end_time'],
                    'average_price': round(cheapest_3h['average_price'], 2),
                    'hours': 3
                } if cheapest_3h else None,
                '4_hours': {
                    'start_hour': cheapest_4h['start_hour'],
                    'end_hour': cheapest_4h['end_hour'],
                    'start_time': cheapest_4h['start_time'],
                    'end_time': cheapest_4h['end_time'],
                    'average_price': round(cheapest_4h['average_price'], 2),
                    'hours': 4
                } if cheapest_4h else None
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

def save_combined_data(collected_data, primary_date):
    """Save combined data for multiple days"""
    if not collected_data:
        return False
    
    # Create combined JSON structure
    combined_data = {
        'metadata': {
            'source': 'ENTSO-E Transparency Platform',
            'retrieved_at': datetime.now().isoformat(),
            'timezone': 'Europe/Brussels',
            'available_days': len(collected_data),
            'primary_date': primary_date.strftime('%Y-%m-%d')
        },
        'days': {}
    }
    
    # Add each day's data
    for day_key, day_info in collected_data.items():
        combined_data['days'][day_key] = day_info['data']
    
    # Save combined latest.json
    with open('latest.json', 'w', encoding='utf-8') as f:
        json.dump(combined_data, f, ensure_ascii=False, indent=2)
    print(f"💾 Combined data saved: latest.json ({len(collected_data)} days)")
    
    # Save individual day files for backwards compatibility
    for day_key, day_info in collected_data.items():
        date_str = day_info['date'].replace('-', '')
        
        # Save individual JSON
        json_filename = f'day_ahead_prices_{date_str}.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(day_info['data'], f, ensure_ascii=False, indent=2)
        print(f"💾 Individual JSON saved: {json_filename}")
        
        # Save individual CSV
        df_data = []
        for price in day_info['data']['prices']:
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
            print(f"💾 Individual CSV saved: {csv_filename}")
    
    return True

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
    """Main function - collect data for today and tomorrow"""
    print("🇧🇪 Belgian Day-Ahead Price Scraper (CORRECTED VERSION)")
    print("=" * 60)
    
    # Get current Belgian time
    belgian_tz = timezone(timedelta(hours=1))  # CET (UTC+1)
    now_belgian = datetime.now(belgian_tz)
    today = now_belgian.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    print(f"🇧🇪 Huidige Belgische tijd: {now_belgian.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    collected_data = {}
    
    # Try to collect data for today
    print(f"\n🎯 Ophalen data voor vandaag: {today.strftime('%Y-%m-%d %A')}")
    today_data = fetch_day_ahead_prices(today)
    
    if today_data:
        print(f"✅ Data voor vandaag gevonden")
        collected_data['today'] = {
            'data': today_data,
            'date': today.strftime('%Y-%m-%d'),
            'label': 'Vandaag'
        }
    else:
        print(f"❌ Geen data voor vandaag")
    
    # Try to collect data for tomorrow
    print(f"\n🎯 Ophalen data voor morgen: {tomorrow.strftime('%Y-%m-%d %A')}")
    tomorrow_data = fetch_day_ahead_prices(tomorrow)
    
    if tomorrow_data:
        print(f"✅ Data voor morgen gevonden")
        collected_data['tomorrow'] = {
            'data': tomorrow_data,
            'date': tomorrow.strftime('%Y-%m-%d'),
            'label': 'Morgen'
        }
    else:
        print(f"❌ Geen data voor morgen")
    
    # If we have at least one dataset, save combined data
    if collected_data:
        combined_success = save_combined_data(collected_data, today)
        
        if combined_success:
            print(f"\n✅ SUCCESS! Data opgeslagen voor {len(collected_data)} dag(en)")
            
            for day_key, day_info in collected_data.items():
                stats = day_info['data']['metadata']['statistics']
                blocks = day_info['data']['metadata'].get('cheapest_blocks', {})
                best_3h = blocks.get('3_hours')
                
                print(f"📊 {day_info['label']} ({day_info['date']}): €{stats['min_eur_mwh']}-{stats['max_eur_mwh']}/MWh")
                
                if best_3h:
                    # Handle datetime formatting safely
                    start_time_obj = best_3h['start_time']
                    end_time_obj = best_3h['end_time']
                    
                    if hasattr(start_time_obj, 'strftime'):
                        start_time = start_time_obj.strftime('%H:%M')
                        end_time = end_time_obj.strftime('%H:%M')
                    else:
                        start_time = datetime.fromisoformat(start_time_obj.replace('Z', '+00:00')).strftime('%H:%M')
                        end_time = datetime.fromisoformat(end_time_obj.replace('Z', '+00:00')).strftime('%H:%M')
                    
                    print(f"💡 Beste 3u blok: {start_time}-{end_time} (€{best_3h['average_price']:.2f}/MWh)")
            
            return  # Success
        else:
            print("❌ Fout bij opslaan gecombineerde data")
    
    # Fallback: try recent days if no current data available
    print(f"\n🔄 Geen actuele data gevonden, proberen eerdere dagen...")
    
    fallback_dates = [
        (today - timedelta(days=1), "gisteren"),
        (today - timedelta(days=2), "eergisteren"),
        (today + timedelta(days=2), "overmorgen")
    ]
    
    for target_date, date_label in fallback_dates:
        if target_date.weekday() >= 5:  # Skip weekends
            print(f"⏭️ Skipping {date_label} - weekend")
            continue
        
        print(f"\n🎯 Proberen {date_label}: {target_date.strftime('%Y-%m-%d %A')}")
        
        data = fetch_day_ahead_prices(target_date)
        if data:
            # Save as single day fallback
            success = save_data(data, target_date)
            if success:
                stats = data['metadata']['statistics']
                print(f"\n✅ SUCCESS! Fallback data voor {target_date.strftime('%d/%m/%Y')} opgehaald")
                print(f"📊 {data['metadata']['data_points']} prijspunten")
                print(f"📊 €{stats['min_eur_mwh']}-{stats['max_eur_mwh']}/MWh")
                return
    
    print("\n❌ Geen geldige data gevonden voor alle geprobeerde datums")
    print("💡 Mogelijke oorzaken:")
    print("   - ENTSO-E service tijdelijk niet beschikbaar")
    print("   - Token problemen")
    print("   - Weekend/feestdag (geen day-ahead trading)")
    sys.exit(1)

if __name__ == "__main__":
    main()
