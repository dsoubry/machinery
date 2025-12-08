#!/usr/bin/env python3
"""
Belgian Day-Ahead Price Scraper (ENTSO-E)
- Haalt A44 day-ahead prijzen op voor België
- Converteert UTC -> Europe/Brussels
- Filtert op één lokale kalenderdag
- Bij dubbele prijzen voor hetzelfde uur: neemt de LAAGSTE prijs
  (sluit aan bij DSoubry/Luminus spotprijzen)
"""

import os
import sys
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

ENTSOE_API_URL = "https://web-api.tp.entsoe.eu/api"
BELGIUM_DOMAIN = "10YBE----------2"
LOCAL_TZ = ZoneInfo("Europe/Brussels")


def get_entsoe_token() -> str:
    """Retrieve ENTSO-E API token from environment."""
    token = os.getenv("ENTSOE_TOKEN", "")
    if not token:
        print("❌ ENTSO-E API token niet gevonden (ENV VAR ENTSOE_TOKEN)!")
        sys.exit(1)
    return token


def detect_xml_namespace(root) -> dict:
    """Detect XML namespace dynamically."""
    tag = root.tag
    if "}" in tag:
        ns = tag.split("}")[0][1:]
        return {"ns": ns}
    return {}


def fetch_day_ahead_prices(target_date_utc: datetime):
    """
    Fetch A44 day-ahead prices for Belgium for a given UTC date.
    We vragen 00:00–24:00 UTC van die dag op.
    """

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
        print(f"❌ HTTP fout: {e}")
        return None

    if r.status_code != 200:
        print(f"❌ ENTSO-E HTTP {r.status_code}: {r.reason}")
        return None

    try:
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"❌ XML parse error: {e}")
        return None

    ns = detect_xml_namespace(root)
    prices = parse_entsoe_response(root, ns, target_date_utc)
    if not prices:
        return None

    return format_price_data(prices)


def parse_entsoe_response(root, namespaces, target_date_utc: datetime):
    """
    Parse ENTSO-E XML into cleaned price list.

    - leest ALLE TimeSeries
    - interpreteert alle tijden als UTC
    - converteert naar Europe/Brussels
    - filtert ALLEEN punten waarvan lokale datum == target_date_local
    - als er meerdere prijzen voor hetzelfde datetime_utc zijn:
      -> bewaart enkel de LAAGSTE prijs
    """

    target_date_local = target_date_utc.astimezone(LOCAL_TZ).date()
    print(f"🎯 Doeldatum (lokale tijd): {target_date_local}")

    # Alle TimeSeries ophalen
    if namespaces:
        ts_list = root.findall(".//ns:TimeSeries", namespaces)
    else:
        ts_list = [e for e in root.iter() if e.tag.endswith("TimeSeries")]

    print(f"🔍 Aantal TimeSeries gevonden: {len(ts_list)}")

    # We bouwen een dict om per UTC-timestamp de laagste prijs te bewaren
    by_timestamp = {}

    for ts in ts_list:
        # Zoek Period
        if namespaces:
            period = ts.find(".//ns:Period", namespaces)
        else:
            period = next((e for e in ts.iter() if e.tag.endswith("Period")), None)

        if period is None:
            continue

        # Zoek start-tijd
        start_el = next(
            (
                el
                for el in period.iter()
                if el.tag.endswith("start") or el.tag == "start"
            ),
            None,
        )
        if start_el is None or not start_el.text:
            continue

        raw_start = start_el.text.strip()
        try:
            start_time_utc = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
            if start_time_utc.tzinfo is None:
                start_time_utc = start_time_utc.replace(tzinfo=timezone.utc)
            else:
                start_time_utc = start_time_utc.astimezone(timezone.utc)
        except Exception:
            continue

        # Alle points in deze Period
        points = [
            e
            for e in period.iter()
            if e.tag.endswith("Point") or e.tag == "Point"
        ]

        for p in points:
            pos_el = next(
                (
                    el
                    for el in p.iter()
                    if el.tag.endswith("position") or el.tag == "position"
                ),
                None,
            )
            price_el = next(
                (
                    el
                    for el in p.iter()
                    if el.tag.endswith("price.amount") or el.tag == "price.amount"
                ),
                None,
            )

            if pos_el is None or price_el is None:
                continue

            try:
                pos = int(pos_el.text)
                price_val = float(price_el.text)
            except Exception:
                continue

            ts_utc = start_time_utc + timedelta(hours=pos - 1)
            ts_local = ts_utc.astimezone(LOCAL_TZ)

            # Hou alleen punten van de gewenste lokale datum
            if ts_local.date() != target_date_local:
                continue

            key = ts_utc

            # als er al een prijs bestaat voor dit tijdstip: neem de LAAGSTE
            existing = by_timestamp.get(key)
            if existing is None or price_val < existing["price_eur_mwh"]:
                by_timestamp[key] = {
                    "datetime_utc": ts_utc,
                    "local_hour": ts_local.hour,
                    "price_eur_mwh": price_val,
                    "price_eur_kwh": price_val / 1000.0,
                }

    # Naar lijst + sorteren
    prices = list(by_timestamp.values())
    prices.sort(key=lambda x: x["datetime_utc"])

    print(f"🔎 Overgehouden unieke uurprijzen: {len(prices)}")
    return prices


def format_price_data(prices):
    """Turn list of price dicts into final JSON-compatible structure."""
    if not prices:
        return None

    vals = [p["price_eur_mwh"] for p in prices]
    avg_price = sum(vals) / len(vals)
    min_p = min(prices, key=lambda p: p["price_eur_mwh"])
    max_p = max(prices, key=lambda p: p["price_eur_mwh"])

    # Lokale datum van de eerste prijs
    local_date = prices[0]["datetime_utc"].astimezone(LOCAL_TZ).date()

    data = {
        "metadata": {
            "source": "ENTSO-E Transparency Platform",
            "
