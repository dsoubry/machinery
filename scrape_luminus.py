import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timezone

URL = "https://my.luminusbusiness.be/market-info/nl/dynamic-prices/"

def fetch_page():
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    resp = requests.get(URL, timeout=20, headers=headers)
    resp.raise_for_status()
    return resp.text

def parse_luminus(html):
    soup = BeautifulSoup(html, "html.parser")

    # Zoek de hoofd-tabel met uurprijzen
    tables = soup.find_all("table")
    if not tables:
        print("Geen tabellen gevonden op de pagina.")
        return None

    # We nemen de eerste tabel -> bevat uurprijzen
    table = tables[0]

    rows = []
    trs = table.find_all("tr")

    for tr in trs:
        cells = tr.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        hour = cells[0].get_text(strip=True)
        today = cells[1].get_text(strip=True)
        tomorrow = cells[2].get_text(strip=True)

        # Filter alleen echte uren (bv "00:00 - 01:00")
        if ":" not in hour:
            continue

        # Converteer prijzen
        def clean_price(p):
            p = p.replace("€", "").replace(",", ".").strip()
            try:
                return float(p)
            except:
                return None

        t1 = clean_price(today)
        t2 = clean_price(tomorrow)

        if t1 is not None and t2 is not None:
            rows.append({
                "range": hour.replace(" ", ""),
                "today": t1,
                "tomorrow": t2
            })

    # Verzamel datums boven de tabel
    date_texts = soup.find_all(string=lambda t: "Belpex" in t)
    date_today = None
    date_tomorrow = None
    if date_texts:
        import re
        matches = re.findall(r"\d{2}/\d{2}/\d{2}", str(date_texts))
        if len(matches) >= 2:
            date_today, date_tomorrow = matches[0], matches[1]

    print(f"Gevonden uurblokken: {len(rows)}")

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

    if not data or not data["rows"]:
        print("Geen geldige gegevens gevonden.")
        return

    with open("luminus-prices.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("luminus-prices.json gevuld met", len(data["rows"]), "uurblokken.")

if __name__ == "__main__":
    main()
