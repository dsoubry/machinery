#!/usr/bin/env python3
"""
ENTSO-E Day-Ahead Price Scraper
Correct filtering (A44), hourly only, no duplicates.
Matches exactly the dataset from:
https://transparency.entsoe.eu/market/energyPrices
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import pandas as pd

ENTSOE_API_URL = "https://web-api.tp.entsoe.eu/api"
ENTSOE_TOKEN = os.getenv("ENTSOE_TOKEN")
BE_BIDDING_ZONE = "10YBE----------2"   # Official Belgian zone


# ------------------------- Helper functions -------------------------

def ensure_token():
    if not ENTSOE_TOKEN:
        print("❌ Missing ENTSO-E API token (ENTSOE_TOKEN).")
        sys.exit(1)


def detect_ns(root):
    if root.tag.startswith("{"):
        uri = root.tag.split("}")[0][1:]
        return {"ns": uri}
    return {}


def parse_iso(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ------------------------- Fetch ENTSO-E XML -------------------------

def fetch_api_xml(date):
    """
    Requests the Day-Ahead Prices (documentType A44)
    for Belgium (BZN|BE) for the given date.
    """
    ensure_token()

    start = date.replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    params = {
        "securityToken": ENTSOE_TOKEN,
        "documentType": "A44",                 # Day-ahead Auction
        "out_Domain": BE_BIDDING_ZONE,
        "in_Domain": BE_BIDDING_ZONE,
        "periodStart": start.strftime("%Y%m%d%H%M"),
        "periodEnd": end.strftime("%Y%m%d%H%M"),
    }

    print(f"🌍 Fetching ENTSO-E Day-Ahead prices for {date.date()}...")

    r = requests.get(ENTSOE_API_URL, params=params, timeout=30)

    if r.status_code != 200:
        print(f"❌ API request failed: {r.status_code} {r.reason}")
        print(r.text)
        return None

    try:
        root = ET.fromstring(r.content)
        return root
    except ET.ParseError as e:
        print("❌ XML Parse Error:", e)
        return None


# ------------------------- Parse Prices -------------------------

def parse_prices(root, target_date):
    """
    Extracts EXACTLY the same prices shown on ENTSO-E UI.
    Filters correctly on:
    - Hourly resolution (PT60M)
    - Currency EUR
    - One correct TimeSeries
    """

    prices = []
    ns = detect_ns(root)
    find = lambda path: root.findall(path, ns) if ns else root.findall(path)

    # Find all TimeSeries objects
    ts_list = find(".//ns:TimeSeries" if ns else ".//TimeSeries")

    if not ts_list:
        print("❌ No TimeSeries found")
        return None

    # --- Filter down to the correct TimeSeries ---
    selected_ts = None

    for ts in ts_list:
        # resolution
        res = ts.find(".//ns:resolution", ns)
        if res is None:
            res = ts.find(".//resolution")

        if not res or res.text != "PT60M":   # must be hourly
            continue

        # currency
        cur = ts.find(".//ns:currency_Unit.name", ns)
        if cur is None:
            cur = ts.find(".//currency_Unit.name")

        if not cur or cur.text != "EUR":
            continue

        # measure
        mu = ts.find(".//ns:price_Measure_Unit.name", ns)
        if mu is None:
            mu = ts.find(".//price_Measure_Unit.name")

        if not mu or mu.text != "MWH":
            continue

        # → This is the correct one
        selected_ts = ts
        break

    if selected_ts is None:
        print("❌ No valid TimeSeries (EUR + MWH + hourly)")
        return None

    # --- Extract Period ---
    period = selected_ts.find(".//ns:Period", ns)
    if period is None:
        period = selected_ts.find(".//Period")

    start_el = period.find(".//ns:start", ns)
    if start_el is None:
        start_el = period.find(".//start")

    start_ts = parse_iso(start_el.text)

    # --- Extract Points ---
    point_elems = period.findall(".//ns:Point", ns)
    if not point_elems:
        point_elems = period.findall(".//Point")

    for p in point_elems:
        pos = p.find(".//ns:position", ns)
        if pos is None:
            pos = p.find(".//position")

        price_el = p.find(".//ns:price.amount", ns)
        if price_el is None:
            price_el = p.find(".//price.amount")

        if pos is None or price_el is None:
            continue

        position = int(pos.text)
        price = float(price_el.text)

        ts_local = (start_ts + timedelta(hours=position-1)).astimezone(timezone.utc)

        prices.append({
            "hour": position,
            "datetime": ts_local.isoformat(),
            "price_eur_mwh": round(price, 2),
            "price_eur_kwh": round(price / 1000, 4),
            "price_cent_kwh": round(price / 10, 2)
        })

    prices.sort(key=lambda x: x["hour"])

    if len(prices) != 24:
        print(f"⚠️ Warning: Expected 24 prices, got {len(prices)}")

    return prices


# ------------------------- Format Output -------------------------

def wrap_output(prices, date):
    values = [p["price_eur_mwh"] for p in prices]

    return {
        "metadata": {
            "source": "ENTSO-E Day-Ahead Auction (A44)",
            "date": date.strftime("%Y-%m-%d"),
            "retrieved_at": datetime.now().isoformat(),
            "timezone": "Europe/Brussels",
            "data_points": len(prices),
            "statistics": {
                "average_eur_mwh": round(sum(values) / len(values), 2),
                "min_eur_mwh": min(values),
                "max_eur_mwh": max(values),
                "min_hour": prices[values.index(min(values))]["hour"],
                "max_hour": prices[values.index(max(values))]["hour"],
            }
        },
        "prices": prices
    }


# ------------------------- Save Files -------------------------

def save_all(data, date):
    dstr = date.strftime("%Y%m%d")

    with open(f"day_ahead_prices_{dstr}.json", "w") as f:
        json.dump(data, f, indent=2)

    pd.DataFrame(data["prices"]).to_csv(
        f"day_ahead_prices_{dstr}.csv", index=False
    )

    with open("latest.json", "w") as f:
        json.dump(data, f, indent=2)

    print("💾 Saved JSON, CSV, latest.json")


# ------------------------- Main -------------------------

def main():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    root = fetch_api_xml(today)
    if not root:
        print("❌ No XML returned")
        sys.exit(1)

    prices = parse_prices(root, today)
    if not prices:
        print("❌ Parsing failed")
        sys.exit(1)

    data = wrap_output(prices, today)
    save_all(data, today)

    print("✅ Day-ahead prices retrieved successfully!")


if __name__ == "__main__":
    main()
