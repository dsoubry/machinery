#!/usr/bin/env python3
"""
Generate HTML report matching the original dark theme design
Maintains the beautiful dark aesthetic with modern styling
"""

import json
import os
from datetime import datetime, timedelta

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

def format_price_table(prices):
    """Generate table with price data matching original styling"""
    if not prices:
        return '<tbody><tr><td colspan="4">Geen prijsdata beschikbaar</td></tr></tbody>'
    
    # Find min/max for relative bars
    price_values = [p['price_eur_mwh'] for p in prices]
    min_price = min(price_values)
    max_price = max(price_values)
    
    html = '<tbody>'
    
    for price in prices:
        # Parse datetime for display
        dt = datetime.fromisoformat(price['datetime'].replace('Z', '+00:00'))
        time_str = dt.strftime('%H.%Mu')
        next_hour = (dt + timedelta(hours=1)).strftime('%H.%Mu')
        time_range = f"{time_str} – {next_hour}"
        
        # Highlight lowest prices
        row_class = ""
        star = ""
        if price['price_eur_mwh'] == min_price:
            row_class = ' class="best-block"'
            star = "★"
        
        # Calculate relative bar width
        ratio = (price['price_eur_mwh'] / max_price) * 100 if max_price > 0 else 0
        
        html += f'''
            <tr{row_class}>
                <td>{time_range}</td>
                <td>{price['price_eur_mwh']:.2f} €</td>
                <td>{price['price_cent_kwh']:.2f} ct/kWh</td>
                <td class="bar-cell">
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
        # Dutch day names
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

    .results {{
      margin-top: 1.5rem;
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
      gap: 1.5rem;
    }}

    @media (max-width: 800px) {{
      .results {{
        grid-template-columns: 1fr;
      }}
    }}

    .summary {{
      border-radius: 1rem;
      padding: 1rem;
      background: radial-gradient(circle at top left, rgba(34, 197, 94, 0.3), rgba(15, 23, 42, 0.9));
      border: 1px solid rgba(34, 197, 94, 0.5);
      min-height: 110px;
    }}

    .summary h2 {{
      margin-top: 0;
      font-size: 1.1rem;
    }}

    .summary p {{
      margin: 0.15rem 0;
      font-size: 0.9rem;
    }}

    .summary strong {{
      color: #bbf7d0;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      overflow: hidden;
      border-radius: 1rem;
    }}

    thead {{
      background: #020617;
    }}

    th, td {{
      padding: 0.4rem 0.5rem;
      text-align: right;
      border-bottom: 1px solid #1f2937;
      white-space: nowrap;
    }}

    th:first-child, td:first-child {{
      text-align: left;
    }}

    tbody tr:nth-child(even) {{
      background: rgba(15, 23, 42, 0.7);
    }}

    .best-block {{
      background: rgba(34, 197, 94, 0.12) !important;
      position: relative;
    }}

    .best-block::before {{
      content: "★";
      position: absolute;
      left: 4px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 0.7rem;
      color: #22c55e;
    }}

    .bar-cell {{
      width: 35%;
    }}

    .bar-wrapper {{
      height: 8px;
      border-radius: 999px;
      background: rgba(31, 41, 55, 0.9);
      overflow: hidden;
    }}

    .bar {{
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, #22c55e, #fbbf24, #f97316, #ef4444);
      width: 0%;
      transition: width 0.3s ease;
    }}

    .note {{
      margin-top: 0.75rem;
      font-size: 0.8rem;
      color: #9ca3af;
    }}

    .small {{
      font-size: 0.75rem;
    }}

    .status-box {{
      margin-top: 0.75rem;
      font-size: 0.8rem;
      color: #9ca3af;
    }}

    .chart-container {{
      margin-top: 1rem;
      border-radius: 1rem;
      padding: 1rem;
      background: rgba(2, 6, 23, 0.5);
      border: 1px solid rgba(75, 85, 99, 0.5);
    }}

    .chart-container h3 {{
      margin-top: 0;
      font-size: 1rem;
      color: #e5e7eb;
    }}

    canvas {{
      max-width: 100%;
      height: 200px;
    }}

    .tips {{
      margin-top: 1rem;
      padding: 1rem;
      background: rgba(34, 197, 94, 0.1);
      border: 1px solid rgba(34, 197, 94, 0.3);
      border-radius: 1rem;
    }}

    .tips h3 {{
      margin-top: 0;
      font-size: 1rem;
      color: #bbf7d0;
    }}

    .tips p {{
      margin: 0.25rem 0;
      font-size: 0.85rem;
      color: #d1fae5;
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

    <div class="results">
      <div>
        <div class="summary">
          <h2>Prijsoverzicht</h2>
          <p><strong>Gemiddelde prijs:</strong> €{avg_price:.2f}/MWh</p>
          <p><strong>Laagste prijs:</strong> €{min_price:.2f}/MWh (uur {min_hour:02d})</p>
          <p><strong>Hoogste prijs:</strong> €{max_price:.2f}/MWh (uur {max_hour:02d})</p>
          <p><strong>Datapunten:</strong> {metadata.get('data_points', 0)} uurprijzen</p>
        </div>

        <div class="tips">
          <h3>💡 Energiebespaartips</h3>
          <p><strong>Gebruik apparaten tijdens groene uren</strong> (★ in tabel)</p>
          <p><strong>Vermijd hoog verbruik tijdens piekuren</strong></p>
          <p><strong>Plan wasmachine/vaatwas</strong> voor goedkoopste momenten</p>
          <p><strong>Laad elektrische auto op</strong> tijdens laagste prijzen</p>
        </div>

        <div class="chart-container">
          <h3>Prijsverloop</h3>
          <canvas id="priceChart"></canvas>
        </div>
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
        <div class="note">
          Balkjes tonen de relatieve prijs t.o.v. de duurste uurprijs van de dag.
          ★ = Laagste prijs van de dag.
        </div>
      </div>
    </div>

    <div class="note" style="text-align: center; margin-top: 2rem; border-top: 1px solid #1f2937; padding-top: 1rem;">
      Data: {metadata.get('source', 'ENTSO-E Transparency Platform')} • 
      <a href="https://github.com/dsoubry/machinery" style="color: #22c55e;">GitHub</a> • 
      <a href="https://transparency.entsoe.eu/" style="color: #22c55e;">ENTSO-E</a>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    // Chart with dark theme
    const ctx = document.getElementById('priceChart').getContext('2d');
    const chartData = {{
      labels: {json.dumps([f"{p['hour']:02d}:00" for p in prices])},
      datasets: [{{
        label: 'Prijs (€/MWh)',
        data: {json.dumps([p['price_eur_mwh'] for p in prices])},
        borderColor: '#22c55e',
        backgroundColor: 'rgba(34, 197, 94, 0.1)',
        borderWidth: 2,
        fill: true,
        tension: 0.1,
        pointBackgroundColor: '#22c55e',
        pointBorderColor: '#22c55e',
        pointRadius: 3
      }}]
    }};
    
    new Chart(ctx, {{
      type: 'line',
      data: chartData,
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          legend: {{ display: false }}
        }},
        scales: {{
          x: {{
            ticks: {{ color: '#9ca3af' }},
            grid: {{ color: 'rgba(156, 163, 175, 0.1)' }}
          }},
          y: {{
            ticks: {{ color: '#9ca3af' }},
            grid: {{ color: 'rgba(156, 163, 175, 0.1)' }},
            title: {{
              display: true,
              text: '€/MWh',
              color: '#9ca3af'
            }}
          }}
        }}
      }}
    }});
  </script>
</body>
</html>'''
    
    return html

def generate_error_page():
    """Generate error page matching the dark theme"""
    return '''<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <title>Belgian Electricity Prices - No Data</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color-scheme: light dark;
    }
    body {
      margin: 0;
      padding: 1.5rem;
      background: #0f172a;
      color: #e5e7eb;
    }
    .card {
      max-width: 600px;
      margin: 0 auto;
      background: rgba(15, 23, 42, 0.9);
      border-radius: 1rem;
      padding: 2rem;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(148, 163, 184, 0.5);
      text-align: center;
    }
    h1 {
      margin-top: 0;
      color: #ef4444;
    }
    a {
      color: #22c55e;
    }
  </style>
</head>
<body>
  <div class="card">
    <h1>⚠️ Geen prijsdata beschikbaar</h1>
    <p>De dag-vooruit elektriciteitsprijzen zijn momenteel niet beschikbaar.</p>
    <p>Probeer het later opnieuw of controleer de <a href="https://github.com/dsoubry/machinery/actions">GitHub Actions</a> voor meer informatie.</p>
  </div>
</body>
</html>'''

def main():
    """Generate HTML report matching original design"""
    print("🌐 Generating HTML report with original dark theme...")
    
    data = load_latest_data()
    html_content = generate_html_report(data)
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("✅ Dark theme index.html generated")

if __name__ == "__main__":
    main()
