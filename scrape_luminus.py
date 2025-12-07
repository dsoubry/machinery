import requests
import json
from datetime import datetime, timezone

# Nieuwe, correcte API endpoint
API_URL = "https://my.luminusbusiness.be/api/gas-electricity/dynamic-price"

def fetch_prices():
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    resp = requests.get(API_URL, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()

def convert(data):
    labels = data.get("labels", [])
    today_vals = data.get("valuesToday", [])
    tomorrow_vals = data.get("valuesTomorrow", [])

    rows = []

    for i in range(len(labels) - 1):
        start = labels[i]
        end = labels[i+1]
        range_txt = f"{start}u – {end}u"

        rows.append({
            "range": range_txt,
            "today": float(today_vals[i]),
            "tomorrow": float(tomorrow_vals[i])
        })

    return {
        "source": API_URL,
        "date_fetched": datetime.now(timezone.utc).isoformat(),
        "date_today": data.get("dateToday"),
        "date_tomorrow": data.get("dateTomorrow"),
        "rows": rows
    }

def main():
    print("Prijsgegevens ophalen van Luminus API...")
    json_data = fetch_prices()

    converted = convert(json_data)
    print("Uurblokken gevonden:", len(converted["rows"]))

    with open("luminus-prices.json", "w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=2)

    print("luminus-prices.json succesvol aangemaakt.")

if __name__ == "__main__":
    main()
