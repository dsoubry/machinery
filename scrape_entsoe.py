#!/usr/bin/env python3
"""
Belgian Day-Ahead Price Scraper - FIXED VERSION
Correct handling of ENTSO-E timestamps
Prevents duplicated hour blocks such as 23.00u–00.00u
Ensures exact match with Belgian day-ahead market hours
"""

import os
import sys
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# ENTSO-E API configuration
ENTSOE_TOKEN = os.getenv('ENTSOE_TOKEN', '')
ENTSOE_API_URL = 'https://web-api.tp.entsoe.eu/api'
BELGIUM_DOMAIN = '10YBE----------2'


def get_entsoe_token():
    if not ENTSOE_TOKEN:
        print("❌ ENTSO-E API token niet gevonden!")
        sys.exit(1)
    return ENTSOE_TOKEN


def detect_xml_namespace(root):
    tag = root.tag
    if '}' in tag:
        ns = tag.split('}')[0][1:]
        return {'ns': ns}
    return {}


def fetch_day_ahead_prices(target_date=None):
    """Fetch day-ahead prices for Belgium (A44)"""

    token = get_entsoe_token()

    if target_date is None:
        target_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Belgian day-ahead = 24 hours for *next* day
    start_time = target_date.replace(tzinfo=timezone.utc)
    end_time = start_time + timedelta(days=1)

    params = {
        "securityToken": token,
        "documentType": "A44",
        "in_Domain": BELGIUM_DOMAIN,
        "out_Domain": BELGIUM_DOMAIN,
        "periodStart": start_time.strftime('%Y%m%d%H%M'),
        "periodEnd": end_time.strftime('%Y%m%d%H%M'),
    }

    print(f"🔌 Ophalen dag-vooruit prijzen voor {target_date.date()}...")

    r = requests.get(ENTSOE_API_URL, params=params, timeout=30)

    if r.status_code != 200:
        print(f"❌ ENTSO-E error {r.status_code}")
        return None

    try:
        root = ET.fromstring(r.content)
    except Exception as e:
        print("❌ XML Parse Error:", e)
        return None

    namespaces = detect_xml_namespace(root)
    return parse_entsoe_response(root, namespaces, target_date)


def parse_entsoe_response(root, namespaces, target_date):
    """Parse ENTSO-E XML for A44 day-ahead prices"""

    prices = []

    # Find TimeSeries blocks
    if namespaces:
        series_list = root.findall('.//ns:TimeSeries', namespaces)
    else:
        series_list = [el for el in root.iter() if el.tag.endswith('TimeSeries')]

    for ts in series_list:
        # Find Period node
        if namespaces:
            period = ts.find('.//ns:Period', namespaces)
        else:
            period = next((el for el in ts.iter() if el.tag.endswith("Period")), None)

        if period is None:
            continue

        # Find <start> timestamp
        start_el = next((el for el in period.iter() if el.tag.endswith("start")), None)
        if start_el is None:
            continue

        start_text = start_el.text

        # IMPORTANT:
        # ENTSO-E A44 start timestamps are ALREADY in local market time (CET or CEST).
        # So we must NOT convert or shift them.
        try:
            start_time = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
        except:
            continue

        # Process <Point> elements
        points = [el for el in period.iter() if el.tag.endswith("Point")]

        for p in points:
            pos_el = next((el for el in p.iter() if el.tag.endswith("position")), None)
            val_el = next((el for el in p.iter() if el.tag.endswith("price.amount")), None)

            if pos_el is None or val_el is None:
                continue

            try:
                pos = int(pos_el.text)
                price = float(val_el.text)
            except:
                continue

            # Compute timestamp correctly
            # Position 1 = start_time (ALREADY local time)
            ts_local = start_time + timedelta(hours=pos - 1)

            # DO NOT CONVERT TIMEZONE AGAIN !
            # ENTSO-E timestamps ARE ALREADY in Belgian market time.
            prices.append({
                "datetime": ts_local,
                "hour": ts_local.hour,
                "price_eur_mwh": price,
                "price_eur_kwh": price / 1000,
            })

    # Sort prices
    prices.sort(key=lambda x: x["datetime"])

    if len(prices) < 24:
        print("⚠️ Warning: fewer than 24 hours detected")

    return format_price_data(prices, target_date)


def format_price_data(prices, target_date):
    """Format output JSON structure"""

    if not prices:
        return None

    vals = [p["price_eur_mwh"] for p in prices]
    avg_price = sum(vals) / len(vals)
    min_price = min(vals)
    max_price = max(vals)

    min_p = next(p for p in prices if p["price_eur_mwh"] == min_price)
    max_p = next(p for p in prices if p["price_eur_mwh"] == max_price)

    return {
        "metadata": {
            "source": "ENTSO-E",
            "date": target_date.strftime('%Y-%m-%d'),
            "retrieved_at": datetime.now().isoformat(),
            "timezone": "Europe/Brussels",
            "data_points": len(prices),
            "statistics": {
                "average_eur_mwh": round(avg_price, 2),
                "min_eur_mwh": round(min_price, 2),
                "max_eur_mwh": round(max_price, 2),
                "min_hour": min_p["hour"],
                "max_hour": max_p["hour"],
            },
        },
        "prices": [
            {
                "datetime": p["datetime"].isoformat(),
                "hour": p["hour"],
                "price_eur_mwh": round(p["price_eur_mwh"], 2),
                "price_eur_kwh": round(p["price_eur_kwh"], 4),
                "price_cent_kwh": round(p["price_eur_kwh"] * 100, 2),
            }
            for p in prices
        ],
    }


def save_data(data, target_date):
    date_str = target_date.strftime('%Y%m%d')
    fn_json = f"day_ahead_prices_{date_str}.json"

    with open(fn_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    with open("latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("💾 Data opgeslagen:", fn_json)
    return True


def main():
    base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Try today only (day-ahead prices should exist before 14:00)
    target_date = base

    data = fetch_day_ahead_prices(target_date)
    if data:
        save_data(data, target_date)
        print("✅ Day-ahead data succesvol opgehaald")
    else:
        print("❌ Geen data beschikbaar")
        sys.exit(1)


if __name__ == "__main__":
    main()
