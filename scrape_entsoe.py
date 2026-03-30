#!/usr/bin/env python3
"""
Belgian Day-Ahead Price Scraper
- Primaire bron: ENTSO-E Transparency Platform API
- Fallback bron: dayaheadmarket.eu (EPEX SPOT scraper)
- Fixes: ZoneInfo voor correcte CET/CEST tijdzone (incl. zomertijd)
"""

import os
import sys
import json
import re
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

# ENTSO-E API Configuration
ENTSOE_TOKEN = os.getenv('ENTSOE_TOKEN', '')
ENTSOE_API_URL = 'https://web-api.tp.entsoe.eu/api'
BELGIUM_DOMAIN = '10YBE----------2'
BRUSSELS_TZ = ZoneInfo('Europe/Brussels')


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
    max_price = max(price_values)
    min_price = min(price_values)
    avg_price = sum(price_values) / len(price_values)

    issues = []

    if max_price > 500:
        issues.append(f"Suspiciously high price: €{max_price:.2f}/MWh")

    if min_price < -200:
        issues.append(f"Extreme negative price: €{min_price:.2f}/MWh")

    if max_price > 10 * avg_price and max_price > 100:
        issues.append(f"Price spike: €{max_price:.2f}/MWh (avg: €{avg_price:.2f}/MWh)")

    if len(set(price_values)) < 5:
        issues.append("Too few unique prices - possible data corruption")

    if len(prices) not in [23, 24, 25, 48, 96]:  # 23/25 voor zomer/wintertijd wissel
        issues.append(f"Unexpected number of price points: {len(prices)}")

    if issues:
        print("⚠️  Data validatie waarschuwingen:")
        for issue in issues:
            print(f"   - {issue}")

        if max_price > 1000 or min_price < -500:
            return False, "Extreme price values detected"

    return True, "Data validation passed"


# ─────────────────────────────────────────────────────────────
# PRIMAIRE BRON: ENTSO-E
# ─────────────────────────────────────────────────────────────

def fetch_day_ahead_prices(target_date=None):
    """Fetch day-ahead prices from ENTSO-E with fallback to dayaheadmarket.eu"""
    token = get_entsoe_token()

    if target_date is None:
        target_date = datetime.now(BRUSSELS_TZ).replace(
            hour=0, minute=0, second=0, microsecond=0)

    if target_date.tzinfo is None:
        target_date = target_date.replace(tzinfo=BRUSSELS_TZ)

    # Converteer Belgische middernacht naar UTC voor ENTSO-E
    start_time_utc = target_date.astimezone(timezone.utc)
    end_time_utc = start_time_utc + timedelta(days=1)

    start_str = start_time_utc.strftime('%Y%m%d%H%M')
    end_str = end_time_utc.strftime('%Y%m%d%H%M')

    print(f"🔌 Ophalen dag-vooruit prijzen voor {target_date.strftime('%d/%m/%Y')} (Belgische tijd)")
    print(f"🕐 UTC periode: {start_str} tot {end_str}")
    print(f"🇧🇪 Belgische periode: {target_date.strftime('%Y-%m-%d 00:00')} tot "
          f"{(target_date + timedelta(days=1)).strftime('%Y-%m-%d 00:00')}")

    params = {
        'securityToken': token,
        'documentType': 'A44',
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
            print("⚠️ ENTSO-E 503 - service tijdelijk niet beschikbaar")
            return fetch_from_dayaheadmarket(target_date)

        if response.status_code == 400:
            print("❌ 400 Bad Request - mogelijk geen data voor deze datum")
            return None

        if response.status_code != 200:
            print(f"❌ HTTP {response.status_code}: {response.reason}")
            return None

        try:
            root = ET.fromstring(response.content)
            print(f"🔍 XML parsed - root: {root.tag}")
        except ET.ParseError as e:
            print(f"❌ XML Parse Error: {e}")
            return None

        if 'no matching data found' in response.text.lower():
            print("📭 ENTSO-E: No matching data found voor deze periode")
            return None

        prices = parse_entsoe_response(root, target_date)

        if not prices:
            print("❌ Geen prijsdata gevonden in XML")
            return None

        is_valid, validation_msg = validate_price_data(prices)
        print(f"🔍 Data validatie: {validation_msg}")

        if not is_valid:
            print("❌ Data validatie gefaald - data wordt verworpen")
            return None

        print(f"✅ {len(prices)} prijspunten succesvol opgehaald via ENTSO-E")
        return format_price_data(prices, target_date, source='ENTSO-E')

    except Exception as e:
        print(f"❌ Onverwachte fout bij ENTSO-E: {e}")
        return None


def parse_entsoe_response(root, target_date):
    """Parse ENTSO-E XML response"""
    root_tag = root.tag
    if '}' in root_tag:
        namespace_uri = root_tag.split('}')[0][1:]
        ns = {'ns': namespace_uri}
        print(f"🔍 Detected namespace: {namespace_uri}")
    else:
        ns = {}
        print("🔍 No namespace detected")

    if ns:
        time_series_list = root.findall('.//ns:TimeSeries', ns)
    else:
        time_series_list = [e for e in root.iter() if e.tag.endswith('TimeSeries')]

    print(f"🔍 Found {len(time_series_list)} TimeSeries elements")

    all_points = []

    for ts_idx, time_series in enumerate(time_series_list):
        print(f"🔍 Processing TimeSeries {ts_idx + 1}")

        if ns:
            periods = time_series.findall('.//ns:Period', ns)
        else:
            periods = [e for e in time_series.iter() if e.tag.endswith('Period')]

        print(f"🔍 Found {len(periods)} periods in TimeSeries {ts_idx + 1}")

        for period_idx, period in enumerate(periods):
            start_time_elem = None

            if ns:
                interval = period.find('.//ns:timeInterval', ns)
                if interval is not None:
                    start_time_elem = interval.find('ns:start', ns)

            if start_time_elem is None:
                for elem in period.iter():
                    if elem.tag.endswith('start'):
                        start_time_elem = elem
                        break

            if start_time_elem is None:
                print(f"⚠️ No start time found in period {period_idx + 1}")
                continue

            try:
                period_start = datetime.fromisoformat(
                    start_time_elem.text.replace('Z', '+00:00'))
            except ValueError:
                print(f"❌ Could not parse start time: {start_time_elem.text}")
                continue

            resolution_elem = None
            if ns:
                resolution_elem = period.find('.//ns:resolution', ns)
            if resolution_elem is None:
                for elem in period.iter():
                    if elem.tag.endswith('resolution'):
                        resolution_elem = elem
                        break

            resolution = resolution_elem.text if resolution_elem is not None else 'PT60M'

            if resolution == 'PT15M':
                time_delta = timedelta(minutes=15)
            elif resolution == 'PT30M':
                time_delta = timedelta(minutes=30)
            else:
                time_delta = timedelta(hours=1)

            if ns:
                points = period.findall('.//ns:Point', ns)
            else:
                points = [e for e in period.iter() if e.tag.endswith('Point')]

            if not points:
                continue

            period_end = period_start + (time_delta * len(points))
            period_start_local = period_start.astimezone(BRUSSELS_TZ)
            period_end_local = period_end.astimezone(BRUSSELS_TZ)

            target_date_obj = target_date.astimezone(BRUSSELS_TZ).date()
            period_start_date = period_start_local.date()
            period_end_date = period_end_local.date()

            covers_target = (
                period_start_date <= target_date_obj <= period_end_date or
                target_date_obj == period_start_date or
                target_date_obj == period_end_date
            )

            if not covers_target:
                print(f"⏭️ Skipping period {period_idx + 1} - "
                      f"covers {period_start_date} to {period_end_date}, need {target_date_obj}")
                continue

            print(f"✅ Processing period {period_idx + 1}: "
                  f"{period_start_local.strftime('%Y-%m-%d %H:%M')} → "
                  f"{period_end_local.strftime('%Y-%m-%d %H:%M')} "
                  f"({resolution}, {len(points)} punten)")

            for point in points:
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
                    point_time = period_start + (time_delta * (position - 1))
                    local_time = point_time.astimezone(BRUSSELS_TZ)

                    if local_time.date() == target_date_obj:
                        all_points.append({
                            'datetime': local_time,
                            'position': position,
                            'price_eur_mwh': price,
                            'price_eur_kwh': price / 1000,
                            'period_start': period_start,
                            'resolution': resolution
                        })
                except (ValueError, TypeError) as e:
                    print(f"❌ Error parsing point: {e}")
                    continue

    print(f"🔍 Collected {len(all_points)} raw points")

    if not all_points:
        return []

    all_points.sort(key=lambda x: x['datetime'])

    resolution = all_points[0]['resolution']
    if resolution in ['PT15M', 'PT30M']:
        print(f"🔄 Converting {resolution} data to hourly averages...")
        hourly_points = convert_to_hourly(all_points)
    else:
        print("ℹ️ Data is already hourly")
        hourly_points = all_points

    seen_hours = set()
    unique_points = []
    for point in hourly_points:
        hour_key = point['datetime'].strftime('%Y-%m-%d %H')
        if hour_key not in seen_hours:
            seen_hours.add(hour_key)
            unique_points.append(point)
        else:
            print(f"⚠️ Duplicate hour skipped: {hour_key}")

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
        hour_key = point['datetime'].replace(minute=0, second=0, microsecond=0)
        if hour_key not in hourly_data:
            hourly_data[hour_key] = []
        hourly_data[hour_key].append(point['price_eur_mwh'])

    hourly_points = []
    for hour_time, prices in sorted(hourly_data.items()):
        avg_price = sum(prices) / len(prices)
        hourly_points.append({
            'datetime': hour_time,
            'price_eur_mwh': avg_price,
            'price_eur_kwh': avg_price / 1000,
            'resolution': 'PT60M',
            'data_points': len(prices)
        })

    print(f"🔄 Converted {len(points)} high-res points to {len(hourly_points)} hourly averages")
    return hourly_points


# ─────────────────────────────────────────────────────────────
# FALLBACK BRON: dayaheadmarket.eu
# ─────────────────────────────────────────────────────────────

def fetch_from_dayaheadmarket(target_date):
    """
    Fallback scraper voor dayaheadmarket.eu (EPEX SPOT data).
    Werkt alleen voor de huidige dag (de site toont altijd vandaag).
    """
    today = datetime.now(BRUSSELS_TZ).date()
    if target_date.astimezone(BRUSSELS_TZ).date() != today:
        print("⏭️ dayaheadmarket.eu fallback werkt alleen voor vandaag - overgeslagen")
        return None

    print("🔄 Proberen fallback via dayaheadmarket.eu (EPEX SPOT)...")

    url = 'https://www.dayaheadmarket.eu/belgium'
    try:
        response = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; energy-monitor/1.0)'
        })

        if response.status_code != 200:
            print(f"❌ dayaheadmarket.eu HTTP {response.status_code}")
            return None

        # Parse tabel met kwartuurprijzen
        # Formaat: "00:00 - 00:15" | "0.05 19" (bold split geeft spatie in tekst)
        rows = re.findall(
            r'<tr>\s*<td[^>]*>\s*([\d:]+\s*-\s*[\d:]+)\s*</td>\s*<td[^>]*>(.*?)</td>',
            response.text, re.DOTALL
        )

        if not rows:
            print("❌ Geen tabelrijen gevonden op dayaheadmarket.eu")
            return None

        quarter_prices = []
        for period_str, price_raw in rows:
            # Verwijder HTML tags en whitespace
            price_clean = re.sub(r'<[^>]+>', '', price_raw)
            price_clean = re.sub(r'\s+', '', price_clean).replace('\xa0', '')
            try:
                price_eur_kwh = float(price_clean)
                price_eur_mwh = price_eur_kwh * 1000
                period_str = period_str.strip()
                start_str = period_str.split('-')[0].strip()

                # Bouw volledige datetime
                h, m = map(int, start_str.split(':'))
                dt = target_date.astimezone(BRUSSELS_TZ).replace(
                    hour=h, minute=m, second=0, microsecond=0)

                quarter_prices.append({
                    'datetime': dt,
                    'price_eur_mwh': price_eur_mwh,
                    'price_eur_kwh': price_eur_kwh,
                    'resolution': 'PT15M'
                })
            except (ValueError, AttributeError):
                continue

        if len(quarter_prices) < 24:
            print(f"❌ Te weinig datapunten: {len(quarter_prices)}")
            return None

        print(f"✅ dayaheadmarket.eu: {len(quarter_prices)} kwartuurprijzen gevonden")

        # Converteer naar uurprijzen (gewogen gemiddelde per uur)
        hourly_data = {}
        for qp in quarter_prices:
            hour_key = qp['datetime'].replace(minute=0, second=0, microsecond=0)
            if hour_key not in hourly_data:
                hourly_data[hour_key] = []
            hourly_data[hour_key].append(qp['price_eur_mwh'])

        hourly_points = []
        for i, (hour_time, prices) in enumerate(sorted(hourly_data.items()), 1):
            avg = sum(prices) / len(prices)
            hourly_points.append({
                'hour': i,
                'datetime': hour_time,
                'price_eur_mwh': avg,
                'price_eur_kwh': avg / 1000,
                'resolution': 'PT60M'
            })

        print(f"🔄 Omgezet naar {len(hourly_points)} uurgemiddelden")

        is_valid, validation_msg = validate_price_data(hourly_points)
        print(f"🔍 Data validatie: {validation_msg}")
        if not is_valid:
            print("❌ Validatie gefaald")
            return None

        return format_price_data(hourly_points, target_date, source='EPEX/dayaheadmarket.eu')

    except Exception as e:
        print(f"❌ dayaheadmarket.eu fout: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# GEMEENSCHAPPELIJKE FUNCTIES
# ─────────────────────────────────────────────────────────────

def find_cheapest_block(prices, block_hours=3):
    """Vind het goedkoopste aaneengesloten blok van N uren"""
    if len(prices) < block_hours:
        return None

    best_sum = float('inf')
    best_start_idx = 0

    for i in range(len(prices) - block_hours + 1):
        block_sum = sum(prices[j]['price_eur_mwh'] for j in range(i, i + block_hours))
        if block_sum < best_sum:
            best_sum = block_sum
            best_start_idx = i

    block_prices = prices[best_start_idx:best_start_idx + block_hours]
    avg_price = best_sum / block_hours

    start_dt = block_prices[0]['datetime']
    end_dt = block_prices[-1]['datetime']

    if hasattr(start_dt, 'isoformat'):
        start_dt = start_dt.isoformat()
    if hasattr(end_dt, 'isoformat'):
        end_dt = end_dt.isoformat()

    return {
        'start_hour': block_prices[0]['hour'],
        'end_hour': block_prices[-1]['hour'],
        'start_time': start_dt,
        'end_time': end_dt,
        'hours': block_hours,
        'average_price': avg_price,
        'total_price': best_sum,
        'prices': [p['price_eur_mwh'] for p in block_prices]
    }


def format_price_data(prices, target_date, source='ENTSO-E'):
    """Formatteer prijsdata naar standaard outputformaat"""
    if not prices:
        return None

    price_values = [p['price_eur_mwh'] for p in prices]
    avg_price = sum(price_values) / len(price_values)
    min_price = min(price_values)
    max_price = max(price_values)

    min_hour_data = next(p for p in prices if p['price_eur_mwh'] == min_price)
    max_hour_data = next(p for p in prices if p['price_eur_mwh'] == max_price)

    cheapest_1h = find_cheapest_block(prices, 1)
    cheapest_2h = find_cheapest_block(prices, 2)
    cheapest_3h = find_cheapest_block(prices, 3)
    cheapest_4h = find_cheapest_block(prices, 4)

    print(f"📊 Statistieken ({source}):")
    print(f"   Gemiddeld: €{avg_price:.2f}/MWh")

    min_dt = min_hour_data['datetime']
    max_dt = max_hour_data['datetime']
    if hasattr(min_dt, 'strftime'):
        print(f"   Minimum: €{min_price:.2f}/MWh om {min_dt.strftime('%H:%M')}")
        print(f"   Maximum: €{max_price:.2f}/MWh om {max_dt.strftime('%H:%M')}")
    print(f"   Spread: €{max_price - min_price:.2f}/MWh")

    if cheapest_3h:
        def fmt_time(t):
            if hasattr(t, 'strftime'):
                return t.strftime('%H:%M')
            return datetime.fromisoformat(t.replace('Z', '+00:00')).strftime('%H:%M')
        print(f"💡 Goedkoopste 3u blok: "
              f"{fmt_time(cheapest_3h['start_time'])}-{fmt_time(cheapest_3h['end_time'])} "
              f"(avg: €{cheapest_3h['average_price']:.2f}/MWh)")

    def block_dict(b, single=False):
        if b is None:
            return None
        if single:
            return {
                'hour': b['start_hour'],
                'time': b['start_time'],
                'price': round(b['average_price'], 2)
            }
        return {
            'start_hour': b['start_hour'],
            'end_hour': b['end_hour'],
            'start_time': b['start_time'],
            'end_time': b['end_time'],
            'average_price': round(b['average_price'], 2),
            'hours': b['hours']
        }

    result = {
        'metadata': {
            'source': source,
            'date': target_date.astimezone(BRUSSELS_TZ).strftime('%Y-%m-%d'),
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
                '1_hour': block_dict(cheapest_1h, single=True),
                '2_hours': block_dict(cheapest_2h),
                '3_hours': block_dict(cheapest_3h),
                '4_hours': block_dict(cheapest_4h),
            }
        },
        'prices': []
    }

    for p in prices:
        dt = p['datetime']
        result['prices'].append({
            'hour': p['hour'],
            'datetime': dt.isoformat() if hasattr(dt, 'isoformat') else dt,
            'price_eur_mwh': round(p['price_eur_mwh'], 2),
            'price_eur_kwh': round(p['price_eur_kwh'], 4),
            'price_cent_kwh': round(p['price_eur_kwh'] * 100, 2)
        })

    return result


def save_combined_data(collected_data, primary_date):
    """Sla gecombineerde data op voor meerdere dagen"""
    if not collected_data:
        return False

    combined_data = {
        'metadata': {
            'source': 'ENTSO-E Transparency Platform / EPEX SPOT',
            'retrieved_at': datetime.now().isoformat(),
            'timezone': 'Europe/Brussels',
            'available_days': len(collected_data),
            'primary_date': primary_date.astimezone(BRUSSELS_TZ).strftime('%Y-%m-%d')
        },
        'days': {key: info['data'] for key, info in collected_data.items()}
    }

    with open('latest.json', 'w', encoding='utf-8') as f:
        json.dump(combined_data, f, ensure_ascii=False, indent=2)
    print(f"💾 Combined data saved: latest.json ({len(collected_data)} dagen)")

    for day_key, day_info in collected_data.items():
        date_str = day_info['date'].replace('-', '')

        json_filename = f'day_ahead_prices_{date_str}.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(day_info['data'], f, ensure_ascii=False, indent=2)
        print(f"💾 JSON saved: {json_filename}")

        df_data = [{
            'datetime': p['datetime'],
            'hour': p['hour'],
            'price_eur_mwh': p['price_eur_mwh'],
            'price_eur_kwh': p['price_eur_kwh'],
            'price_cent_kwh': p['price_cent_kwh']
        } for p in day_info['data']['prices']]

        if df_data:
            csv_filename = f'day_ahead_prices_{date_str}.csv'
            pd.DataFrame(df_data).to_csv(csv_filename, index=False)
            print(f"💾 CSV saved: {csv_filename}")

    return True


def save_data(data, target_date):
    """Sla data op voor één dag"""
    if not data:
        return False

    date_str = target_date.astimezone(BRUSSELS_TZ).strftime('%Y%m%d')

    json_filename = f'day_ahead_prices_{date_str}.json'
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 JSON saved: {json_filename}")

    df_data = [{
        'datetime': p['datetime'],
        'hour': p['hour'],
        'price_eur_mwh': p['price_eur_mwh'],
        'price_eur_kwh': p['price_eur_kwh'],
        'price_cent_kwh': p['price_cent_kwh']
    } for p in data['prices']]

    if df_data:
        csv_filename = f'day_ahead_prices_{date_str}.csv'
        pd.DataFrame(df_data).to_csv(csv_filename, index=False)
        print(f"💾 CSV saved: {csv_filename}")

    with open('latest.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 Latest data saved: latest.json")

    return True


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    print("🇧🇪 Belgian Day-Ahead Price Scraper")
    print("=" * 60)

    now_belgian = datetime.now(BRUSSELS_TZ)
    today = now_belgian.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    print(f"🇧🇪 Huidige Belgische tijd: {now_belgian.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    collected_data = {}

    # Vandaag
    print(f"\n🎯 Ophalen data voor vandaag: {today.strftime('%Y-%m-%d %A')}")
    today_data = fetch_day_ahead_prices(today)

    if today_data:
        print(f"✅ Data voor vandaag gevonden")
        collected_data['today'] = {
            'data': today_data,
            'date': today.strftime('%Y-%m-%d'),
            'label': f"Vandaag ({today.strftime('%d/%m')})"
        }
    else:
        print(f"❌ Geen data voor vandaag")

        # Gisteren als extra fallback (weekdag)
        yesterday = today - timedelta(days=1)
        if yesterday.weekday() < 5:
            print(f"🔄 Proberen gisteren als fallback: {yesterday.strftime('%Y-%m-%d %A')}")
            yesterday_data = fetch_day_ahead_prices(yesterday)
            if yesterday_data:
                print(f"✅ Fallback data voor gisteren gevonden")
                collected_data['yesterday'] = {
                    'data': yesterday_data,
                    'date': yesterday.strftime('%Y-%m-%d'),
                    'label': f"Gisteren ({yesterday.strftime('%d/%m')})"
                }

    # Morgen
    print(f"\n🎯 Ophalen data voor morgen: {tomorrow.strftime('%Y-%m-%d %A')}")
    tomorrow_data = fetch_day_ahead_prices(tomorrow)

    if tomorrow_data:
        print(f"✅ Data voor morgen gevonden")
        collected_data['tomorrow'] = {
            'data': tomorrow_data,
            'date': tomorrow.strftime('%Y-%m-%d'),
            'label': f"Morgen ({tomorrow.strftime('%d/%m')})"
        }
    else:
        print(f"❌ Geen data voor morgen (normaal vóór ~13u)")

    # Opslaan
    if collected_data:
        combined_success = save_combined_data(collected_data, today)

        if combined_success:
            print(f"\n✅ SUCCESS! Data opgeslagen voor {len(collected_data)} dag(en)")

            def fmt_time(t):
                if hasattr(t, 'strftime'):
                    return t.strftime('%H:%M')
                return datetime.fromisoformat(t.replace('Z', '+00:00')).strftime('%H:%M')

            for day_key, day_info in collected_data.items():
                stats = day_info['data']['metadata']['statistics']
                source = day_info['data']['metadata'].get('source', '?')
                blocks = day_info['data']['metadata'].get('cheapest_blocks', {})
                best_3h = blocks.get('3_hours')

                print(f"📊 {day_info['label']}: "
                      f"€{stats['min_eur_mwh']}-{stats['max_eur_mwh']}/MWh "
                      f"[{source}]")

                if best_3h:
                    print(f"💡 Beste 3u blok: "
                          f"{fmt_time(best_3h['start_time'])}-{fmt_time(best_3h['end_time'])} "
                          f"(€{best_3h['average_price']:.2f}/MWh)")
            return

        else:
            print("❌ Fout bij opslaan gecombineerde data")

    # Fallback: andere dagen proberen
    print(f"\n🔄 Geen actuele data gevonden, proberen andere dagen...")

    fallback_dates = [
        (today - timedelta(days=1), "gisteren"),
        (today - timedelta(days=2), "eergisteren"),
        (today + timedelta(days=2), "overmorgen")
    ]

    for target_date, date_label in fallback_dates:
        if target_date.weekday() >= 5:
            print(f"⏭️ Skipping {date_label} - weekend")
            continue

        print(f"\n🎯 Proberen {date_label}: {target_date.strftime('%Y-%m-%d %A')}")
        data = fetch_day_ahead_prices(target_date)

        if data:
            success = save_data(data, target_date)
            if success:
                stats = data['metadata']['statistics']
                print(f"\n✅ SUCCESS! Fallback data voor "
                      f"{target_date.strftime('%d/%m/%Y')} opgehaald")
                print(f"📊 {data['metadata']['data_points']} prijspunten")
                print(f"📊 €{stats['min_eur_mwh']}-{stats['max_eur_mwh']}/MWh")
                return

    print("\n❌ Geen geldige data gevonden voor alle geprobeerde datums")
    print("💡 Mogelijke oorzaken:")
    print("   - ENTSO-E én dayaheadmarket.eu beide niet beschikbaar")
    print("   - Token problemen")
    print("   - Weekend/feestdag (geen day-ahead trading)")
    sys.exit(1)


if __name__ == "__main__":
    main()
