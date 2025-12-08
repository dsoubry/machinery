#!/usr/bin/env python3
"""
Generate HTML report for Belgian day-ahead electricity prices
Compatible with GitHub Pages deployment
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
    """Generate HTML table with price data"""
    if not prices:
        return "<p>Geen prijsdata beschikbaar</p>"
    
    html = """
    <div class="table-responsive">
        <table class="table table-striped table-hover">
            <thead class="table-dark">
                <tr>
                    <th>Uur</th>
                    <th>Tijdstip</th>
                    <th>Prijs (€/MWh)</th>
                    <th>Prijs (€/kWh)</th>
                    <th>Prijs (cent/kWh)</th>
                    <th>Indicator</th>
                </tr>
            </thead>
            <tbody>
    """
    
    # Find min/max for color coding
    price_values = [p['price_eur_mwh'] for p in prices]
    min_price = min(price_values)
    max_price = max(price_values)
    
    for price in prices:
        # Color coding
        if price['price_eur_mwh'] == min_price:
            row_class = "table-success"
            indicator = "🟢 Laagste"
        elif price['price_eur_mwh'] == max_price:
            row_class = "table-danger" 
            indicator = "🔴 Hoogste"
        elif price['price_eur_mwh'] < (min_price + max_price) / 2:
            row_class = "table-light"
            indicator = "🟡 Laag"
        else:
            row_class = ""
            indicator = "🟠 Hoog"
        
        # Parse datetime for display
        dt = datetime.fromisoformat(price['datetime'].replace('Z', '+00:00'))
        time_str = dt.strftime('%H:%M')
        
        html += f"""
                <tr class="{row_class}">
                    <td><strong>{price['hour']:02d}</strong></td>
                    <td>{time_str}</td>
                    <td>€{price['price_eur_mwh']:.2f}</td>
                    <td>€{price['price_eur_kwh']:.4f}</td>
                    <td>{price['price_cent_kwh']:.2f}</td>
                    <td>{indicator}</td>
                </tr>
        """
    
    html += """
            </tbody>
        </table>
    </div>
    """
    
    return html

def generate_statistics_cards(metadata):
    """Generate Bootstrap cards with statistics"""
    stats = metadata.get('statistics', {})
    
    return f"""
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card text-white bg-primary">
                <div class="card-header">Gemiddelde Prijs</div>
                <div class="card-body">
                    <h4 class="card-title">€{stats.get('average_eur_mwh', 0):.2f}/MWh</h4>
                    <p class="card-text">{stats.get('average_eur_mwh', 0)/10:.2f} cent/kWh</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-white bg-success">
                <div class="card-header">Laagste Prijs</div>
                <div class="card-body">
                    <h4 class="card-title">€{stats.get('min_eur_mwh', 0):.2f}/MWh</h4>
                    <p class="card-text">Uur {stats.get('min_hour', 0):02d}:00</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-white bg-danger">
                <div class="card-header">Hoogste Prijs</div>
                <div class="card-body">
                    <h4 class="card-title">€{stats.get('max_eur_mwh', 0):.2f}/MWh</h4>
                    <p class="card-text">Uur {stats.get('max_hour', 0):02d}:00</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-white bg-info">
                <div class="card-header">Data Punten</div>
                <div class="card-body">
                    <h4 class="card-title">{metadata.get('data_points', 0)}</h4>
                    <p class="card-text">Uurlijkse prijzen</p>
                </div>
            </div>
        </div>
    </div>
    """

def generate_html_report(data):
    """Generate complete HTML report"""
    if not data:
        return generate_error_page()
    
    metadata = data.get('metadata', {})
    prices = data.get('prices', [])
    
    # Parse date for display
    try:
        date_obj = datetime.fromisoformat(metadata.get('date', ''))
        date_display = date_obj.strftime('%A %d %B %Y')
        date_dutch = {
            'Monday': 'Maandag', 'Tuesday': 'Dinsdag', 'Wednesday': 'Woensdag',
            'Thursday': 'Donderdag', 'Friday': 'Vrijdag', 'Saturday': 'Zaterdag', 'Sunday': 'Zondag',
            'January': 'januari', 'February': 'februari', 'March': 'maart', 'April': 'april',
            'May': 'mei', 'June': 'juni', 'July': 'juli', 'August': 'augustus',
            'September': 'september', 'October': 'oktober', 'November': 'november', 'December': 'december'
        }
        for en, nl in date_dutch.items():
            date_display = date_display.replace(en, nl)
    except:
        date_display = metadata.get('date', 'Onbekend')
    
    retrieved_at = metadata.get('retrieved_at', '')
    try:
        retrieved_dt = datetime.fromisoformat(retrieved_at)
        retrieved_display = retrieved_dt.strftime('%d/%m/%Y om %H:%M')
    except:
        retrieved_display = 'Onbekend'
    
    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Belgische Dag-Vooruit Elektriciteitsprijzen - {date_display}</title>
    
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <style>
        body {{
            background-color: #f8f9fa;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem 0;
            margin-bottom: 2rem;
        }}
        .chart-container {{
            background: white;
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 2rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .footer {{
            margin-top: 3rem;
            padding: 2rem 0;
            background: #343a40;
            color: white;
        }}
    </style>
</head>
<body>
    <header class="header">
        <div class="container">
            <h1 class="display-4">🇧🇪 Belgische Elektriciteitsprijzen</h1>
            <p class="lead">Dag-vooruit prijzen voor {date_display}</p>
            <p class="mb-0">Gegevens van {metadata.get('source', 'ENTSO-E')} • Laatst bijgewerkt: {retrieved_display}</p>
        </div>
    </header>

    <main class="container">
        {generate_statistics_cards(metadata)}
        
        <div class="chart-container">
            <h3>Prijsverloop van de dag</h3>
            <canvas id="priceChart" height="100"></canvas>
        </div>
        
        <div class="chart-container">
            <h3>Gedetailleerde prijstabel</h3>
            {format_price_table(prices)}
        </div>
        
        <div class="alert alert-info">
            <h5>💡 Tips voor energiebesparing:</h5>
            <ul class="mb-0">
                <li><strong>Gebruik apparaten tijdens goedkope uren</strong> (groene rijen in de tabel)</li>
                <li><strong>Vermijd hoge verbruik tijdens piekuren</strong> (rode rijen in de tabel)</li>
                <li><strong>Programmeer je elektrische verwarming en boiler</strong> voor de goedkoopste momenten</li>
                <li><strong>Laad je elektrische auto op</strong> tijdens de laagste prijzen</li>
            </ul>
        </div>
    </main>

    <footer class="footer text-center">
        <div class="container">
            <p>&copy; 2024 Belgian Energy Price Monitor</p>
            <p class="small">
                Data: {metadata.get('source', 'ENTSO-E Transparency Platform')} • 
                <a href="https://github.com/dsoubry/machinery" class="text-light">GitHub</a>
            </p>
        </div>
    </footer>

    <script>
        // Chart.js configuration
        const ctx = document.getElementById('priceChart').getContext('2d');
        const priceData = {json.dumps([p['price_eur_mwh'] for p in prices])};
        const hourLabels = {json.dumps([f"{p['hour']:02d}:00" for p in prices])};
        
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: hourLabels,
                datasets: [{{
                    label: 'Prijs (€/MWh)',
                    data: priceData,
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.1
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    title: {{
                        display: true,
                        text: 'Uurlijkse Elektriciteitsprijzen'
                    }},
                    legend: {{
                        display: false
                    }}
                }},
                scales: {{
                    y: {{
                        title: {{
                            display: true,
                            text: 'Prijs (€/MWh)'
                        }},
                        beginAtZero: false
                    }},
                    x: {{
                        title: {{
                            display: true,
                            text: 'Tijdstip'
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>"""
    
    return html

def generate_error_page():
    """Generate error page when no data is available"""
    return """<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Belgische Elektriciteitsprijzen - Geen Data</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-5">
        <div class="alert alert-warning text-center">
            <h2>❌ Geen prijsdata beschikbaar</h2>
            <p>De dag-vooruit prijzen zijn momenteel niet beschikbaar.</p>
            <p>Probeer het later opnieuw of controleer de GitHub Actions voor meer informatie.</p>
        </div>
    </div>
</body>
</html>"""

def main():
    """Generate HTML report"""
    print("🌐 Genereren HTML rapport...")
    
    data = load_latest_data()
    html_content = generate_html_report(data)
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("✅ index.html gegenereerd")

if __name__ == "__main__":
    main()
