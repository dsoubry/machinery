import requests
import json
from datetime import datetime, timezone

# De API voor dynamische prijzen
API_URL = "https://my.luminusbusiness.be/api/market-info/dynamic-prices"

def fetch_prices():
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    resp = requests.get(API_URL, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()

def convert(data):
    # De API bevat velden zoals:
    # {
    #   "labels": ["00:00", "01:00", ...],
    #   "today": [55.1, 48.2, ...],
    #   "tomorrow": [60.2, 50.1, ...]
    # }

    labels = data.get("labels", [])
    today = data.get("today", [])
    tomorrow = data.get("tomorrow", [])

    rows = []
    for i in range(len(labels) - 1):
        start = labels[i]
        end = labels[i + 1]
        range_txt = f"{start}u – {end}u"

        rows.append({
            "range": range_txt,
            "today": float(today[i]),
            "tomorrow": float(tomorrow[i])
        })

    return {
        "source": API_URL,
        "date_fetched": datetime.now(timezone.utc).isoformat(),
        "date_today": data.get("labelsDateToday"),
        "date_tomorrow": data.get("labelsDateTomorrow"),
        "rows": rows
    }

def main():
    json_data = fetch_prices()
    converted = convert(json_data)

    print("Gevonden uurblokken:", len(converted["rows"]))

    with open("luminus-prices.json", "w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=2)

    print("luminus-prices.json succesvol aangemaakt.")

if __name__ == "__main__":
    main()
