#!/usr/bin/env python3
"""
Generate HTML report matching the original dark theme design
Maintains the beautiful dark aesthetic with modern styling
"""

import json
import os
from datetime import datetime, timedelta

def format_cheapest_blocks_html(cheapest_blocks):
    """Format cheapest consecutive blocks for HTML display"""
    if not cheapest_blocks:
        return "<p>Geen blokgegevens beschikbaar</p>"
    
    def parse_time_safe(time_obj):
        """Safely parse datetime object or ISO string to HH:MM format"""
        if hasattr(time_obj, 'strftime'):
            return time_obj.strftime('%H:%M')
        else:
            return datetime.fromisoformat(time_obj.replace('Z', '+00:00')).strftime('%H:%M')
    
    html = ""
    
    # 1 hour block (quickest appliances)
    if cheapest_blocks.get('1_hour'):
        block_1h = cheapest_blocks['1_hour']
        time_1h = parse_time_safe(block_1h['time'])
        html += f'<p><strong>🔌 Korte toestellen (1u):</strong> {time_1h} - €{block_1h["price"]:.2f}/MWh</p>'
    
    # 2 hour block (washing machines)
    if cheapest_blocks.get('2_hours'):
        block_2h = cheapest_blocks['2_hours']
        start_2h = parse_time_safe(block_2h['start_time'])
        end_2h = parse_time_safe(block_2h['end_time'])
        html += f'<p><strong>🧺 Wasmachine (2u):</strong> {start_2h}-{end_2h} - €{block_2h["average_price"]:.2f}/MWh</p>'
    
    # 3 hour block (dishwashers, longer cycles)
    if cheapest_blocks.get('3_hours'):
        block_3h = cheapest_blocks['3_hours']
        start_3h = parse_time_safe(block_3h['start_time'])
        end_3h = parse_time_safe(block_3h['end_time'])
        html += f'<p><strong>🍽️ Vaatwas (3u):</strong> {start_3h}-{end_3h} - €{block_3h["average_price"]:.2f}/MWh</p>'
    
    # 4 hour block (dryers, long cycles)
    if cheapest_blocks.get('4_hours'):
        block_4h = cheapest_blocks['4_hours']
        start_4h = parse_time_safe(block_4h['start_time'])
        end_4h = parse_time_safe(block_4h['end_time'])
        html += f'<p><strong>👕 Droogkast (4u):</strong> {start_4h}-{end_4h} - €{block_4h["average_price"]:.2f}/MWh</p>'
    
    if html:
        html += '<p class="note">💡 Plan je apparaten om te starten aan het begin van deze tijdsblokken</p>'
    
    return html

def format_price_table(prices):
    """Generate table with price data and highlight cheapest consecutive blocks"""
    if not prices:
        return '<tbody><tr><td colspan="4">Geen prijsdata beschikbaar</td></tr></tbody>'
    
    # Find min/max for relative bars
    price_values = [p['price_eur_mwh'] for p in prices]
    min_price = min(price_values)
    max_price = max(price_values)
    
    html = '<tbody>'
    
    for i, price in enumerate(prices):
        # Parse datetime for display
        dt = datetime.fromisoformat(price['datetime'].replace('Z', '+00:00'))
        time_str = dt.strftime('%H.%Mu')
        next_hour = (dt + timedelta(hours=1)).strftime('%H.%Mu')
        time_range = f"{time_str} – {next_hour}"
        
        # Highlight different blocks
        row_class = ""
        if price['price_eur_mwh'] == min_price:
            row_class = ' class="best-single-hour"'
        
        # Calculate relative bar width
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

    .best-single-hour {{
      background: rgba(34, 197, 94, 0.12) !important;
      position: relative;
    }}

    .best-single-hour::before {{
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

    /* Mobile responsive table */
    @media (max-width: 600px) {{
      table, thead, tbody, th, td, tr {{
        display: block;
      }}
      
      thead tr {{
        position: absolute;
        top: -9999px;
        left: -9999px;
      }}
      
      tbody tr {{
        border: 1px solid #1f2937;
        border-radius: 0.5rem;
        margin-bottom: 0.75rem;
        padding: 0.75rem;
        background: rgba(15, 23, 42, 0.7);
        position: relative;
      }}
      
      tbody tr.best-single-hour {{
        background: rgba(34, 197, 94, 0.12);
        border: 1px solid rgba(34, 197, 94, 0.3);
      }}
      
      tbody tr.best-single-hour::before {{
        content: "★ LAAGSTE PRIJS";
        position: absolute;
        top: 0.5rem;
        right: 0.75rem;
        font-size: 0.7rem;
        color: #22c55e;
        font-weight: bold;
      }}
      
      td {{
        border: none;
        border-bottom: 1px solid #1f2937;
        position: relative;
        padding: 0.4rem 0 0.4rem 45%;
        text-align: left !important;
        white-space: normal;
      }}
      
      td:last-child {{
        border-bottom: none;
      }}
      
      td:before {{
        content: attr(data-label) ": ";
        position: absolute;
        left: 0;
        width: 40%;
        padding-right: 10px;
        white-space: nowrap;
        color: #9ca3af;
        font-weight: bold;
        font-size: 0.75rem;
      }}
      
      .bar-cell {{
        width: auto;
      }}
      
      .bar-wrapper {{
        margin-top: 0.25rem;
      }}
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
          <h3>🏠 Beste tijden voor huishoudtoestellen</h3>
          {format_cheapest_blocks_html(metadata.get('cheapest_blocks', {}))}
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

    return html

def generate_tabs_html(days_data):
    """Generate tabs HTML for multiple days"""
    tabs_html = '<div class="tabs">\n'
    
    day_labels = {
        'today': 'Vandaag',
        'tomorrow': 'Morgen',
        'yesterday': 'Gisteren'
    }
    
    for day_key in days_data.keys():
        label = day_labels.get(day_key, day_key.title())
        tabs_html += f'  <div class="tab" id="tab-{day_key}" onclick="showDay(\'{day_key}\')">{label}</div>\n'
    
    tabs_html += '</div>\n'
    return tabs_html

def generate_day_content_html(day_key, day_data):
    """Generate content HTML for a single day"""
    metadata = day_data.get('metadata', {})
    prices = day_data.get('prices', [])
    
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
    
    content_html = f'''
    <div class="tab-content" id="content-{day_key}">
      <div class="results">
        <div>
          <div class="summary">
            <h2>Prijsoverzicht - {date_display}</h2>
            <p><strong>Gemiddelde prijs:</strong> €{avg_price:.2f}/MWh</p>
            <p><strong>Laagste prijs:</strong> €{min_price:.2f}/MWh (uur {min_hour:02d})</p>
            <p><strong>Hoogste prijs:</strong> €{max_price:.2f}/MWh (uur {max_hour:02d})</p>
            <p><strong>Datapunten:</strong> {metadata.get('data_points', 0)} uurprijzen</p>
          </div>

          <div class="tips">
            <h3>🏠 Beste tijden voor huishoudtoestellen</h3>
            {format_cheapest_blocks_html(metadata.get('cheapest_blocks', {}))}
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
    </div>
    '''
    
    return content_html

def load_latest_data():
    """Load the latest price data (supports both single and multi-day format)"""
    try:
        with open('latest.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if it's the new multi-day format
        if 'days' in data:
            return data  # Multi-day format
        else:
            # Old single-day format - wrap it
            return {
                'metadata': {
                    'source': data.get('metadata', {}).get('source', 'ENTSO-E'),
                    'retrieved_at': data.get('metadata', {}).get('retrieved_at', ''),
                    'available_days': 1,
                    'primary_date': data.get('metadata', {}).get('date', '')
                },
                'days': {
                    'today': data
                }
            }
            
    except FileNotFoundError:
        print("❌ Geen latest.json gevonden")
        return None
    except json.JSONDecodeError:
        print("❌ Ongeldige JSON in latest.json")
        return None

def generate_html_report(data):
    """Generate HTML report with support for multiple days"""
    if not data:
        return generate_error_page()
    
    # Check if we have multi-day data
    days_data = data.get('days', {})
    if not days_data:
        return generate_error_page()
    
    # Get available days
    available_days = list(days_data.keys())
    primary_day = available_days[0] if available_days else None
    
    if not primary_day:
        return generate_error_page()
    
    # Generate tabs and content for each day
    tabs_html = generate_tabs_html(days_data)
    day_contents_html = ""
    
    for day_key, day_data in days_data.items():
        day_content = generate_day_content_html(day_key, day_data)
        day_contents_html += day_content
    
    # Get retrieved timestamp from main metadata
    main_metadata = data.get('metadata', {})
    retrieved_at = main_metadata.get('retrieved_at', '')
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
      max-width: 1200px;
      margin: 0 auto;
      background: rgba(15, 23, 42, 0.9);
      border-radius: 1rem;
      padding: 1.5rem;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(148, 163, 184, 0.5);
    }}

    .tabs {{
      display: flex;
      gap: 0.5rem;
      margin-bottom: 1.5rem;
      border-bottom: 1px solid #1f2937;
    }}

    .tab {{
      padding: 0.75rem 1.5rem;
      background: rgba(31, 41, 55, 0.5);
      border: 1px solid rgba(75, 85, 99, 0.5);
      border-bottom: none;
      border-radius: 0.5rem 0.5rem 0 0;
      cursor: pointer;
      transition: all 0.2s ease;
      color: #9ca3af;
    }}

    .tab:hover {{
      background: rgba(34, 197, 94, 0.1);
      color: #bbf7d0;
    }}

    .tab.active {{
      background: rgba(34, 197, 94, 0.2);
      border-color: rgba(34, 197, 94, 0.5);
      color: #bbf7d0;
      font-weight: bold;
    }}

    .tab-content {{
      display: none;
    }}

    .tab-content.active {{
      display: block;
    }}

    .results {{
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
      gap: 1.5rem;
    }}

    @media (max-width: 800px) {{
      .results {{
        grid-template-columns: 1fr;
      }}
      
      .tabs {{
        flex-direction: column;
      }}
      
      .tab {{
        text-align: center;
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

    .best-single-hour {{
      background: rgba(34, 197, 94, 0.12) !important;
      position: relative;
    }}

    .best-single-hour::before {{
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

    /* Mobile responsive table */
    @media (max-width: 600px) {{
      table, thead, tbody, th, td, tr {{
        display: block;
      }}
      
      thead tr {{
        position: absolute;
        top: -9999px;
        left: -9999px;
      }}
      
      tbody tr {{
        border: 1px solid #1f2937;
        border-radius: 0.5rem;
        margin-bottom: 0.75rem;
        padding: 0.75rem;
        background: rgba(15, 23, 42, 0.7);
        position: relative;
      }}
      
      tbody tr.best-single-hour {{
        background: rgba(34, 197, 94, 0.12);
        border: 1px solid rgba(34, 197, 94, 0.3);
      }}
      
      tbody tr.best-single-hour::before {{
        content: "★ LAAGSTE PRIJS";
        position: absolute;
        top: 0.5rem;
        right: 0.75rem;
        font-size: 0.7rem;
        color: #22c55e;
        font-weight: bold;
      }}
      
      td {{
        border: none;
        border-bottom: 1px solid #1f2937;
        position: relative;
        padding: 0.4rem 0 0.4rem 45%;
        text-align: left !important;
        white-space: normal;
      }}
      
      td:last-child {{
        border-bottom: none;
      }}
      
      td:before {{
        content: attr(data-label) ": ";
        position: absolute;
        left: 0;
        width: 40%;
        padding-right: 10px;
        white-space: nowrap;
        color: #9ca3af;
        font-weight: bold;
        font-size: 0.75rem;
      }}
      
      .bar-cell {{
        width: auto;
      }}
      
      .bar-wrapper {{
        margin-top: 0.25rem;
      }}
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
      Laatste update: {retrieved_display} • {len(days_data)} dag(en) beschikbaar
    </div>

    {tabs_html}
    
    {day_contents_html}

    <div class="note" style="text-align: center; margin-top: 2rem; border-top: 1px solid #1f2937; padding-top: 1rem;">
      Data: ENTSO-E Transparency Platform • 
      <a href="https://github.com/dsoubry/machinery" style="color: #22c55e;">GitHub</a> • 
      <a href="https://transparency.entsoe.eu/" style="color: #22c55e;">ENTSO-E</a>
    </div>
  </div>

  <script>
    function showDay(dayKey) {{
      // Hide all tab contents
      document.querySelectorAll('.tab-content').forEach(el => {{
        el.classList.remove('active');
      }});
      
      // Hide all tabs
      document.querySelectorAll('.tab').forEach(el => {{
        el.classList.remove('active');
      }});
      
      // Show selected tab and content
      document.getElementById('tab-' + dayKey).classList.add('active');
      document.getElementById('content-' + dayKey).classList.add('active');
    }}
    
    // Show first tab by default
    document.addEventListener('DOMContentLoaded', function() {{
      const firstTab = document.querySelector('.tab');
      if (firstTab) {{
        firstTab.click();
      }}
    }});
  </script>
</body>
</html>'''
    
    return html

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
