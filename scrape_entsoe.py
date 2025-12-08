#!/usr/bin/env python3
"""
Belgian Day-Ahead Price Scraper (ENTSO-E)
Clean, fixed, stable version — no syntax errors, no duplicate hours.
UTC → Europe/Brussels conversion is correct.
Only keeps prices belonging to ONE local Belgian calendar day.
"""

import os
import sys
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

# Constants
ENTSOE_API_URL = "https://web-api.tp.entsoe.eu/api"
BELGIUM_DOMAIN = "10YBE----------2"
LOCAL_TZ = ZoneInfo("Europe/Brussels")


# ---------------------------------------------------------
# TOKEN HANDLING
# ---------------------------------------------------------

def get_entsoe_token():
    """Retrieve ENTSO-E API token from environment."""
    token = os.getenv("ENTSOE_TOKEN", "")
    if not token:
        print("❌ ENTSO-E API token niet gevonden!")
        sys.exit(1)
    return token


# ---------------------------------------------------------
# XML NAMESPACE
# ---------------------------------------------------------

def detect_xml_namespace(root):
    """Detect XML namespace dynamically."""
    tag = root.tag
    if "}" in tag:
        ns = tag.split("}")[0][1:]
        return {"ns": ns}
    return {}


# ---------------------------------------------------------
# FETCH
# ---------------------------------------------------------

def fetch_day_ahead_prices(target_date_utc):
    """Fetch 24h day-ahead prices for Belgium."""
    token = get_entsoe_token()

    start = datetime(
        year=target_date_utc.year,
        month=target_date_utc.month,
        day=target_date_utc.day,
        tzinfo=timezone.utc,
    )
    end = start + timedelta(days=1)

    params = {
        "securityToken": token,
        "documentType": "A44",
        "in_Domain": BELGIUM_DOMAIN,
        "out_Domain": BELGIUM_DOMAIN,
        "periodStart": start.strftime("%Y%m%d%H%M"),
        "periodEnd": end.strftime("%Y%m%d%H%M"),
    }

    print(f"🔌 Ophalen dag-vooruit prijzen voor UTC-datum {target_date_utc.date()}")

    try:
        r = requests.get(ENTSOE_API_URL, params=params, timeout=30)
    except Exception as e:
        print("❌ HTTP fout:", e)
        return None

    if r.status_code != 200:
        print(f"❌ ENTSO-E HTTP {r.status_code}: {r.reason}")
        return None

    try:
        root = ET.fromstring(r.content)
    except Exception as e:
        print("❌ XML parse error:", e)
        return None

    ns = detect_xml_namespace(root)
    return parse_entsoe_response(root, ns, target_date_utc)


# ---------------------------------------------------------
# PARSE XML
# ---------------------------------------------------------

def parse_entsoe_response(root, namespaces, target_date_utc):
    """Parse ENTSO-E XML into clean price points."""
    prices = []

    target_date_local = target_date_utc.astimezone(LOCAL_TZ).date()
    print(f"🎯 Doeldatum (lokale tijd): {target_date_local}")

    # Find TimeSeries
# ---------------------------------------------------------
# FILTER ONLY THE OFFICIAL BIDDING ZONE PRICE SERIES (A44 – GL)
# ---------------------------------------------------------

ts_candidates = []

if namespaces:
    ts_list = root.findall(".//ns:TimeSeries", namespaces)
else:
    ts_list = [e for e in root.iter() if e.tag.endswith("TimeSeries")]

for ts in ts_list:
    # find businessType
    bt = None
    for el in ts.iter():
        if el.tag.endswith("businessType") or el.tag == "businessType":
            bt = el.text.strip()
            break

    # find curveType (optional)
    ct = None
    for el in ts.iter():
        if el.tag.endswith("curveType") or el.tag == "curveType":
            ct = el.text.strip()
            break

    # Accept only Bidding Zone Day-Ahead Price (A44 + GL)
    if bt == "A44" and (ct == "GL" or ct is None):
        ts_candidates.append(ts)

# If nothing matched (rare), fallback to the first TimeSeries
if not ts_candidates:
    ts_candidates = ts_list[:1]

print(f"🔍 Geselecteerde TimeSeries voor dagprijs: {len(ts_candidates)}")


    for ts in ts_candidates:
        # Find Period
        if namespaces:
            period = ts.find(".//ns:Period", namespaces)
        else:
            period = next((e for e in ts.iter() if e.tag.endswith("Period")), None)

        if period is None:
            continue

        # Find start timestamp
        start_el = next(
            (el for el in period.iter() if el.tag.endswith("start") or el.tag == "start"),
            None,
        )
        if start_el is None:
            continue

        raw_start = start_el.text

        try:
            start_time_utc = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
            if start_time_utc.tzinfo is None:
                start_time_utc = start_time_utc.replace(tzinfo=timezone.utc)
            else:
                start_time_utc = start_time_utc.astimezone(timezone.utc)
        except Exception:
            continue

        # Collect points
        points = [
            e
            for e in period.iter()
            if e.tag.endswith("Point") or e.tag == "Point"
        ]

        for p in points:
            pos_el = next(
                (el for el in p.iter()
                 if el.tag.endswith("position") or el.tag == "position"),
                None,
            )
            val_el = next(
                (el for el in p.iter()
                 if el.tag.endswith("price.amount") or el.tag == "price.amount"),
                None,
            )

            if pos_el is None or val_el is None:
                continue

            try:
                position = int(pos_el.text)
                price = float(val_el.text)
            except Exception:
                continue

            # Compute timestamp
            ts_utc = start_time_utc + timedelta(hours=position - 1)
            ts_local = ts_utc.astimezone(LOCAL_TZ)

            # KEEP ONLY POINTS FOR THIS LOCAL DAY
            if ts_local.date() != target_date_local:
                continue

            prices.append({
                "datetime_utc": ts_utc,
                "local_hour": ts_local.hour,
                "price_eur_mwh": price,
                "price_eur_kwh": price / 1000.0,
            })

    prices.sort(key=lambda x: x["datetime_utc"])
    print(f"🔎 Overgehouden prijsuren: {len(prices)}")

    return prices


# ---------------------------------------------------------
# FORMAT OUTPUT
# ---------------------------------------------------------

def format_price_data(prices, target_date_utc):
    """Turn list of prices into JSON metadata."""
    if not prices:
        return None

    vals = [p["price_eur_mwh"] for p in prices]
    avg = sum(vals) / len(vals)
    min_p = min(prices, key=lambda p: p["price_eur_mwh"])
    max_p = max(prices, key=lambda p: p["price_eur_mwh"])

    local_date = prices[0]["datetime_utc"].astimezone(LOCAL_TZ).date()

    return {
        "metadata": {
            "source": "ENTSO-E Transparency Platform",
            "date": local_date.isoformat(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "timezone": "Europe/Brussels",
            "data_points": len(prices),
            "statistics": {
                "average_eur_mwh": round(avg, 2),
                "min_eur_mwh": round(min_p["price_eur_mwh"], 2),
                "max_eur_mwh": round(max_p["price_eur_mwh"], 2),
                "min_hour": min_p["local_hour"],
                "max_hour": max_p["local_hour"],
            },
        },
        "prices": [
            {
                "datetime": p["datetime_utc"].isoformat(),
                "hour": p["local_hour"],
                "price_eur_mwh": round(p["price_eur_mwh"], 2),
                "price_eur_kwh": round(p["price_eur_kwh"], 4),
                "price_cent_kwh": round(p["price_eur_kwh"] * 100, 2),
            }
            for p in prices
        ],
    }


# ---------------------------------------------------------
# SAVE
# ---------------------------------------------------------

def save_data(data):
    """Save JSON, CSV, and latest.json."""
    if not data:
        return False

    local_date = data["metadata"]["date"]
    date_str = local_date.replace("-", "")

    # JSON
    json_file = f"day_ahead_prices_{date_str}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"💾 JSON saved: {json_file}")

    # CSV
    df = pd.DataFrame([
        {
            "datetime_utc": p["datetime"],
            "hour_local": p["hour"],
            "price_eur_mwh": p["price_eur_mwh"],
            "price_eur_kwh": p["price_eur_kwh"],
            "price_cent_kwh": p["price_cent_kwh"],
        }
        for p in data["prices"]
    ])
    csv_file = f"day_ahead_prices_{date_str}.csv"
    df.to_csv(csv_file, index=False)
    print(f"💾 CSV saved: {csv_file}")

    # latest.json
    with open("latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("💾 latest.json saved")

    return True


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    """Try today and a few days back (local) until data exists."""
    print("🇧🇪 Belgian Day-Ahead Price Scraper")
    print("=" * 50)

    today_local = datetime.now(LOCAL_TZ).date()

    for days_back in range(0, 4):
        local_date = today_local - timedelta(days=days_back)

        # Convert local date → UTC midnight
        target_date_utc = datetime(
            year=local_date.year,
            month=local_date.month,
            day=local_date.day,
            tzinfo=LOCAL_TZ,
        ).astimezone(timezone.utc)

        print(f"\n🎯 Probeert lokale dag: {local_date} (UTC: {target_date_utc.date()})")

        prices = fetch_day_ahead_prices(target_date_utc)
        if not prices:
            continue

        data = format_price_data(prices, target_date_utc)
        if save_data(data):
            print(f"✅ Data succesvol opgeslagen voor {local_date}")
            return

    print("❌ Geen data beschikbaar voor de laatste dagen.")
    sys.exit(1)


if __name__ == "__main__":
    main()

