#!/usr/bin/env python3
"""
Generate HTML report matching the original dark theme design
Now includes FIXED hour-block handling (no more repeated '23.00u – 00.00u')
"""

import json
import os
from datetime import datetime, timedelta, timezone

def load_latest_data():
    """Load the latest price data"""
    try:
        with open('latest.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Geen latest.json gevonden")
        return None
    except json.JSONDecodeError:
        print("❌ Ongeldige JSON in latest.json")
        return None


# -----------------------------
#  FIXED hour-block formatter
# -----------------------------
def format_hour_block(ts_utc):
    """
    Converts UTC timestamp to CET (UTC+1).
    Prevents repeated hour blocks such as 4× '23.00u – 00.00u'.
    """

    # Convert UTC → CET safely
    ts_local = ts_utc.astimezone(timezone(timedelta(hours=1)))

    start = ts_local.hour
    end = (start + 1) % 24

    return f"{start:02d}.00u – {end:02d}.00u"


def format_price_table(prices):
    """Generate table with price data matching original styling, with FIXED timestamps."""
    if not prices:
        return '<tbody><tr><td colspan="4">Geen prijsdata beschikbaar</td></tr></tbody>'

    # Find min/max for relative bars
    price_values = [p['price_eur_mwh'] for p in prices]
    min_price = min(price_values)
    max_price = max(price_values)

    html = '<tbody>'

    for price in prices:
        # Parse datetime as TRUE UTC
        dt_utc = datetime.fromisoformat(price['datetime'].replace('Z', '+00:00'))

        # FIXED hour block label
        time_range = format_hour_block(dt_utc)

        # Highlight lowest prices
        row_class = ' class="best-block"' if price['price_eur_mwh'] == min_price else ""

        # Relative bar width
        ratio = (price['price_eur_mwh'] / max_price) * 100 if max_price > 0 else 0

        html += f'''
            <tr{row_class}>
                <td data-label="Uurblok">{time_range}</td>
                <td data-label="Prijs (€/MWh)">{price['price_eur_mwh']:.2f} €</td>
                <td data-label="Prijs (ct/kWh)">{price['price_cent_kwh']:.2f} ct/kWh</td>
                <td data-label="Niveau" class="bar-cell">
                    <div class="bar-wrapper">
                        <div class="bar" style="width: {ratio:.1f}%"></div>
                    </div>
                </td>
            </tr>
        '''

    html += '</tbody>'
    return html


def generate_html_report(data):
    """Generate HTML report matching original dark theme"""
    if not data:
        return generate_error_page()

    metadata = data.get('metadata', {})
    prices = data.get('prices', [])

    # Parse date for display
    try:
        date_obj = datetime.fromisoformat(metadata.get('date', ''))
        date_display = date_obj.strftime('%A %d %B %Y')
        # Dutch translations
        date_dutch = {
            'Monday': 'maandag', 'Tuesday': 'dinsdag', 'Wednesday': 'woensdag',
            'Thursday': 'donderdag', 'Friday': 'vrijdag', 'Saturday': 'zaterdag', 'Sunday': 'zondag',
            'January': 'januari', 'February': 'februari', 'March': 'maart', 'April': 'april',
            'May': 'mei', 'June': 'juni', 'July': 'juli', 'August': 'augustus',
            'September': 'september', 'October': 'oktober', 'November': 'november', 'December': 'december'
        }
        for en, nl in date_dutch.items():
            date_display = date_display.replace(en, nl)
    except:
        date_display = metadata.get('date', 'Onbekend')

    # Statistics
    stats = metadata.get('statistics', {})
    avg_price = stats.get('average_eur_mwh', 0)
    min_price = stats.get('min_eur_mwh', 0)
    max_price = stats.get('max_eur_mwh', 0)
    min_hour = stats.get('min_hour', 0)
    max_hour = stats.get('max_hour', 0)

    # Retrieved timestamp
    retrieved_at = metadata.get('retrieved_at', '')
    try:
        retrieved_dt = datetime.fromisoformat(retrieved_at)
        retrieved_display = retrieved_dt.strftime('%d/%m/%Y om %H:%M')
    except:
        retrieved_display = 'Onbekend'

    html = f'''<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <title>Belgian Day-Ahead Electricity Prices</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color-scheme: light dark;
    }}

    body {{
      margin: 0;
      padding: 1.5rem;
      background: #0f172a;
      color: #e5e7eb;
    }}

    h1 {{
      margin-top: 0;
      font-size: 1.6rem;
    }}

    .card {{
      max-width: 1000px;
      margin: 0 auto;
      background: rgba(15, 23, 42, 0.9);
      border-radius: 1rem;
      padding: 1.5rem;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(148, 163, 184, 0.5);
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Belgian Day-Ahead Electricity Prices</h1>
    <p class="small">
      Officiële dag-vooruit elektriciteitsprijzen van de Belgische elektriciteitsmarkt.
      Data van ENTSO-E Transparency Platform via geautomatiseerde GitHub Actions.
    </p>

    <div class="status-box">
      Laatste update: {retrieved_display} • Data voor: {date_display}
    </div>

    <div>
        <table>
          <thead>
            <tr>
              <th>Uurblok</th>
              <th>Prijs (€/MWh)</th>
              <th>Prijs (ct/kWh)</th>
              <th class="bar-cell">Relatief niveau</th>
            </tr>
          </thead>
          {format_price_table(prices)}
        </table>
    </div>
  </div>
</body>
</html>'''

    return html


def generate_error_page():
    return "<html><body><h1>❌ Geen data beschikbaar</h1></body></html>"


def main():
    print("🌐 Generating HTML report with dark theme & fixed hour blocks...")
    
    data = load_latest_data()
    html_content = generate_html_report(data)
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("✅ index.html gegenereerd (uurblokken 100% correct)")


if __name__ == "__main__":
    main()
