#!/usr/bin/env python3
"""
Belgian Day-Ahead Price Scraper - fixed for single-day data

Key fixes:
- Treat ENTSO-E timestamps as UTC (spec zegt: alle tijden in UTC)
- Converteer naar Europe/Brussels voor "hour" en filtering
- Filter ALLEEN punten waarvan de lokale datum = gevraagde datum
  => geen 4× "23:00 – 00:00" blokken meer voor verschillende dagen
"""

import os
import sys
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

# ENTSO-E API Configuration
ENTSOE_TOKEN = os.getenv("ENTSOE_TOKEN", "")
ENTSOE_API_URL = "https://web-api.tp.entsoe.eu/api"
BELGIUM_DOMAIN = "10YBE----------2"

LOCAL_TZ = ZoneInfo("Europe/Brussels")


def get_entsoe_token():
    """Get ENTSO-E API token from environment or exit with instructions"""
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
    if "}" in root_tag:
        namespace_uri = root_tag.split("}")[0][1:]  # Remove { and }
        return {"ns": namespace_uri}
    return {}


def fetch_day_ahead_prices(target_date_utc):
    """
    Fetch day-ahead prices from ENTSO-E for a given UTC date.

    ENTSO-E gebruikt UTC timestamps. We vragen 00:00 → 24:00 UTC van die datum.
    """
    token = get_entsoe_token()

    start_time = datetime(
        year=target_date_utc.year,
        month=target_date_utc.month,
        day=target_date_utc.day,
        tzinfo=timezone.utc,
    )
    end_time = start_time + timedelta(days=1)

    start_str = start_time.strftime("%Y%m%d%H%M")
    end_str = end_time.strftime("%Y%m%d%H%M")

    print(f"🔌 Ophalen dag-vooruit prijzen voor {start_time.date()} (UTC)...")

    params = {
        "securityToken": token,
        "documentType": "A44",  # Day-ahead prices
        "in_Domain": BELGIUM_DOMAIN,
        "out_Domain": BELGIUM_DOMAIN,
        "periodStart": start_str,
        "periodEnd": end_str,
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

        try:
            root = ET.fromstring(response.content)
            print(f"🔍 Root element: {root.tag}")
        except ET.ParseError as e:
            print(f"❌ XML Parse Error: {e}")
            return None

        namespaces = detect_xml_namespace(root)
        print(f"🔍 Detected namespace: {namespaces}")

        prices = parse_entsoe_response(root, target_date_utc, namespaces)

        if not prices:
            print("❌ Geen prijsdata gevonden (na filtering op datum)")
            return None

        print(f"✅ {len(prices)} uurprijzen succesvol opgehaald (en gefilterd)")
        return format_price_data(prices, target_date_utc)

    except Exception as e:
        print(f"❌ Fout: {e}")
        return None


def parse_entsoe_response(root, target_date_utc, namespaces):
    """
    Parse ENTSO-E XML response with dynamic namespace.

    We:
    - interpreteren alle tijden als UTC
    - converteren naar Europe/Brussels
    - houden ALLEEN punten waarvan de lokale datum == target_date_local
    """
    prices = []

    print("🔍 Parsing XML response...")

    # Lokale kalenderdag die we willen tonen
    target_date_local = target_date_utc.astimezone(LOCAL_TZ).date()
    print(f"🎯 Doeldatum (lokale tijd): {target_date_local}")

    # Probeer met gedetecteerde namespace
    if namespaces:
        time_series_list = root.findall(".//ns:TimeSeries", namespaces)
        print(f"🔍 Found {len(time_series_list)} TimeSeries elements (with namespace)")
    else:
        time_series_list = []

    # Fallback: zoek zonder namespace
    if not time_series_list:
        for elem in root.iter():
            if elem.tag.endswith("}TimeSeries") or elem.tag == "TimeSeries":
                time_series_list.append(elem)
        print(f"🔍 Found {len(time_series_list)} TimeSeries elements (fallback)")

    for ts_idx, time_series in enumerate(time_series_list):
        print(f"🔍 Processing TimeSeries {ts_idx + 1}")

        # Period zoeken
        period = None
        if namespaces:
            period = time_series.find(".//ns:Period", namespaces)

        if period is None:
            for elem in time_series.iter():
                if elem.tag.endswith("}Period") or elem.tag == "Period":
                    period = elem
                    break

        if period is None:
            print(f"⚠️ No Period found in TimeSeries {ts_idx + 1}")
            continue

        # start-tijd element zoeken
        start_time_elem = None
        for elem in period.iter():
            if elem.tag.endswith("}start") or elem.tag == "start":
                start_time_elem = elem
                break

        if start_time_elem is None:
            print("⚠️ No start time found in Period")
            continue

        start_time_text = start_time_elem.text
        print(f"🔍 Period start time (raw): {start_time_text}")

        try:
            # ENTSO-E: alle tijden in UTC; zorg dat dit tz-aware UTC is
            start_time = datetime.fromisoformat(start_time_text.replace("Z", "+00:00"))
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            else:
                start_time = start_time.astimezone(timezone.utc)
        except ValueError as e:
            print(f"❌ Error parsing start time: {e}")
            continue

        # Points verzamelen
        points = []
        for elem in period.iter():
            if elem.tag.endswith("}Point") or elem.tag == "Point":
                points.append(elem)

        print(f"🔍 Found {len(points)} price points in this Period")

        for point in points:
            position_elem = None
            price_elem = None

            for elem in point.iter():
                if elem.tag.endswith("}position") or elem.tag == "position":
                    position_elem = elem
                elif elem.tag.endswith("}price.amount") or elem.tag == "price.amount":
                    price_elem = elem

            if position_elem is None or price_elem is None:
                continue

            try:
                position = int(position_elem.text)
                price = float(price_elem.text)
            except (ValueError, TypeError):
                continue

            # UTC tijdstip van dit punt
            hour_timestamp_utc = start_time + timedelta(hours=position - 1)
            local_time = hour_timestamp_utc.astimezone(LOCAL_TZ)

            # FILTER: alleen punten van onze lokale kalenderdag bewaren
            if local_time.date() != target_date_local:
                continue

            prices.append(
                {
                    "datetime_utc": hour_timestamp_utc,
                    "local_hour": local_time.hour,
                    "price_eur_mwh": price,
                    "price_eur_kwh": price / 1000.0,
                }
            )

    # Sorteren op UTC-tijd
    prices.sort(key=lambda x: x["datetime_utc"])
    print(f"🔍 Total parsed & kept prices: {len(prices)}")

    return prices


def format_price_data(prices, target_date_utc):
    """Format price data for JSON/CSV output"""
    if not prices:
        return None

    price_values = [p["price_eur_mwh"] for p in prices]
    avg_price = sum(price_values) / len(price_values)
    min_price = min(price_values)
    max_price = max(price_values)

    min_item = min(prices, key=lambda p: p["price_eur_mwh"])
    max_item = max(prices, key=lambda p: p["price_eur_mwh"])

    print(f"📊 Gemiddeld: €{avg_price:.2f}/MWh")
    print(
        f"📉 Minimum: €{min_price:.2f}/MWh om {min_item['local_hour']:02d}:00 (lokale tijd)"
    )
    print(
        f"📈 Maximum: €{max_price:.2f}/MWh om {max_item['local_hour']:02d}:00 (lokale tijd)"
    )

    # Datum in metadata: gebruik lokale datum van de prijzen
    if prices:
        local_date = prices[0]["datetime_utc"].astimezone(LOCAL_TZ).date()
    else:
        local_date = target_date_utc.astimezone(LOCAL_TZ).date()

    result = {
        "metadata": {
            "source": "ENTSO-E Transparency Platform",
            "date": local_date.isoformat(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "timezone": "Europe/Brussels",
            "data_points": len(prices),
            "statistics": {
                "average_eur_mwh": round(avg_price, 2),
                "min_eur_mwh": round(min_price, 2),
                "max_eur_mwh": round(max_price, 2),
                "min_hour": int(min_item["local_hour"]),
                "max_hour": int(max_item["local_hour"]),
            },
        },
        "prices": [],
    }

    for p in prices:
        result["prices"].append(
            {
                "hour": int(p["local_hour"]),
                "datetime": p["datetime_utc"].isoformat(),
                "price_eur_mwh": round(p["price_eur_mwh"], 2),
                "price_eur_kwh": round(p["price_eur_kwh"], 4),
                "price_cent_kwh": round(p["price_eur_kwh"] * 100, 2),
            }
        )

    return result


def save_data(data, target_date_utc):
    """Save data to JSON/CSV + latest.json"""
    if not data:
        return False

    # Bestandsnaam: lokale datum (handiger voor mensen)
    local_date = datetime.fromisoformat(data["metadata"]["date"]).date()
    date_str = local_date.strftime("%Y%m%d")

    json_filename = f"day_ahead_prices_{date_str}.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 JSON saved: {json_filename}")

    # CSV
    df_rows = []
    for price in data["prices"]:
        df_rows.append(
            {
                "datetime_utc": price["datetime"],
                "hour_local": price["hour"],
                "price_eur_mwh": price["price_eur_mwh"],
                "price_eur_kwh": price["price_eur_kwh"],
                "price_cent_kwh": price["price_cent_kwh"],
            }
        )

    if df_rows:
        df = pd.DataFrame(df_rows)
        csv_filename = f"day_ahead_prices_{date_str}.csv"
        df.to_csv(csv_filename, index=False)
        print(f"💾 CSV saved: {csv_filename}")

    # latest.json
    with open("latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("💾 Latest data saved: latest.json")

    return True


def main():
    """
    Main entrypoint.

    Strategie:
    - Eerst "vandaag" in lokale tijd (Europe/Brussels) → naar UTC
    - Als er nog geen dag-vooruit prijzen zijn, proberen we max. 3 dagen terug,
      zodat de site toch iets toont.
    """
    print("🇧🇪 Belgian Day-Ahead Price Scraper (ENTSO-E)")
    print("=" * 50)

    now_local = datetime.now(LOCAL_TZ)
    base_local_date = now_local.date()

    # Probeer vandaag en een paar vorige dagen
    for days_back in range(0, 4):
        local_date = base_local_date - timedelta(days=days_back)
        target_date_utc = datetime(
            year=local_date.year,
            month=local_date.month,
            day=local_date.day,
            tzinfo=LOCAL_TZ,
        ).astimezone(timezone.utc)

        print(f"\n🎯 Proberen lokale dag: {local_date} (=> UTC: {target_date_utc.date_
