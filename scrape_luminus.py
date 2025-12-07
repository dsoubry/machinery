import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, timezone

URL = "https://my.luminusbusiness.be/market-info/nl/dynamic-prices/"

def fetch_page():
    resp = requests.get(URL, timeout=20)
    resp.raise_for_status()
    return resp.text

def parse_luminus(html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Datumregel zoeken
    date_line = next((l for l in lines if "Belpex H" in l and "€/MWh" in l), None)
    date_today = None
    date_tomorrow = None
    if date_line:
        clean = date_line.replace("’", "'")
        matches = re.findall(r"\d{2}/\d{2}/\d{2}", clean)
        if len(matches) >= 2:
            date_today, date_tomorrow = matches[0], matches[1]

    hour_re = re.compile(r"^(\d{2}\.\d{2})u\s*[–-]\s*(\d{2}\.\d{2})u$")
    price_re = re.compile(r"€\s*([\d.,]+)|([\d.,]+)\s*€")

    rows = []
    i = 0
    while i < len(lines):
        m = hour_re.match(lines[i])
        if m:
            range_str = lines[i]                       # bv. "00.00u – 01.00u"
            prices = []
            j = i + 1
            while j < len(lines) and len(prices) < 2:
                pm = price_re.search(lines[j])
                if pm:
                    num = pm.group(1) or pm.group(2)
                    if num:
                        # duizendtallen weg, comma → punt
                        num = num.replace(".", "").replace(",", ".")
                        try:
                            prices.append(float(num))
                        except ValueError:
                            pass
                j += 1

            if len(prices) == 2:
                rows.append({
                    "range": range_str,
                    "today": prices[0],
                    "tomorrow": prices[1]
                })

            i = j
        else:
            i += 1

    return {
        "source": URL,
        "date_fetched": datetime.now(timezone.utc).isoformat(),
        "date_today": date_today,
        "date_tomorrow": date_tomorrow,
        "rows": rows
    }

def main():
    html = fetch_page()
    data = parse_luminus(html)

    if len(data["rows"]) != 24:
        print(f"WAARSCHUWING: {len(data['rows'])} uurblokken gevonden i.p.v. 24.")

    with open("luminus-prices.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("luminus-prices.json bijgewerkt.")

if __name__ == "__main__":
    main()
