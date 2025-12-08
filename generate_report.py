#!/usr/bin/env python3
"""
Generate clean HTML report for Belgian day-ahead electricity prices
Simple layout that respects the original design
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
    """Generate simple HTML table with price data"""
    if not prices:
        return "<p>Geen prijsdata beschikbaar</p>"
    
    # Find min/max for highlighting
    price_values = [p['price_eur_mwh'] for p in prices]
    min_price = min(price_values)
    max_price = max(price_values)
    
    html = """
    <table>
        <thead>
            <tr>
                <th>Uur</th>
                <th>Tijdstip</th>
                <th>Prijs (€/MWh)</th>
                <th>Prijs (€/kWh)</th>
                <th>Prijs (cent/kWh)</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for price in prices:
        # Simple styling
        row_class = ""
        if price['price_eur_mwh'] == min_price:
            row_class = ' class="lowest"'
        elif price['price_eur_mwh'] == max_price:
            row_class = ' class="highest"'
        
        # Parse datetime for display
        dt = datetime.fromisoformat(price['datetime'].replace('Z', '+00:00'))
        time_str = dt.strftime('%H:%M')
        
        html += f"""
            <tr{row_class}>
                <td>{price['hour']:02d}</td>
                <td>{time_str}</td>
                <td>€{price['price_eur_mwh']:.2f}</td>
                <td>€{price['price_eur_kwh']:.4f}</td>
                <td>{price['price_cent_kwh']:.2f}</td>
            </tr>
        """
    
    html += """
        </tbody>
    </table>
    """
    
    return html

def generate_html_report(data):
    """Generate clean, minimal HTML report"""
    if not data:
        return generate_error_page()
    
    metadata = data.get('metadata', {})
    prices = data.get('prices', [])
    
    # Parse date for display
    try:
        date_obj = datetime.fromisoformat(metadata.get('date', ''))
        date_display = date_obj.strftime('%d/%m/%Y')
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
    
    # Price data for chart
    chart_data = {
        'labels': [f"{p['hour']:02d}:00" for p in prices],
        'prices': [p['price_eur_mwh'] for p in prices]
    }
    
    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Belgian Electricity Prices - {date_display}</title>
    
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background: #f9f9f9;
            color: #333;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #2c3e50;
            text-align: center;
            margin-bottom: 10px;
            font-size: 28px;
        }}
        
        .subtitle {{
            text-align: center;
            color: #7f8c8d;
            margin-bottom: 30px;
            font-size: 16px;
        }}
        
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-box {{
            background: #ecf0f1;
            padding: 20px;
            border-radius: 6px;
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 5px;
        }}
        
        .stat-label {{
            color: #7f8c8d;
            font-size: 14px;
        }}
        
        .chart-container {{
            margin: 30px 0;
            background: white;
            border: 1px solid #ddd;
            border-radius: 6px;
            padding: 20px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        
        th {{
            background: #34495e;
            color: white;
            font-weight: bold;
        }}
        
        tr:hover {{
            background: #f5f5f5;
        }}
        
        .lowest {{
            background: #d5f4e6 !important;
            font-weight: bold;
        }}
        
        .highest {{
            background: #fadbd8 !important;
            font-weight: bold;
        }}
        
        .footer {{
            margin-top: 30px;
            padding: 20px;
            background: #ecf0f1;
            border-radius: 6px;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }}
        
        .tips {{
            margin: 20px 0;
            padding: 20px;
            background: #e8f5e8;
            border-left: 4px solid #27ae60;
            border-radius: 0 6px 6px 0;
        }}
        
        .tips h3 {{
            margin-top: 0;
            color: #27ae60;
        }}
        
        .tips ul {{
            margin-bottom: 0;
        }}
        
        canvas {{
            max-width: 100%;
            height: 300px;
        }}
        
        @media (max-width: 768px) {{
            body {{
                margin: 10px;
            }}
            .container {{
                padding: 20px;
            }}
            .stats {{
                grid-template-columns: 1fr;
            }}
            table {{
                font-size: 14px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🇧🇪 Belgian Electricity Prices</h1>
        <p class="subtitle">Day-ahead prices for {date_display} • Data from {metadata.get('source', 'ENTSO-E')}</p>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-value">€{avg_price:.2f}</div>
                <div class="stat-label">Average (€/MWh)</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">€{min_price:.2f}</div>
                <div class="stat-label">Lowest ({min_hour:02d}:00)</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">€{max_price:.2f}</div>
                <div class="stat-label">Highest ({max_hour:02d}:00)</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{metadata.get('data_points', 0)}</div>
                <div class="stat-label">Data points</div>
            </div>
        </div>
        
        <div class="chart-container">
            <h3>Hourly Price Chart</h3>
            <canvas id="priceChart"></canvas>
        </div>
        
        <div class="tips">
            <h3>💡 Energy Saving Tips</h3>
            <ul>
                <li><strong>Use appliances during low-price hours</strong> (green rows in table below)</li>
                <li><strong>Avoid high consumption during peak hours</strong> (red rows in table below)</li>
                <li><strong>Schedule heating and water boiler</strong> for cheapest moments</li>
                <li><strong>Charge electric vehicles</strong> during lowest prices</li>
            </ul>
        </div>
        
        <h3>Detailed Price Table</h3>
        {format_price_table(prices)}
        
        <div class="footer">
            <p>Data updated: {retrieved_display} • Source: {metadata.get('source', 'ENTSO-E Transparency Platform')}</p>
            <p><a href="https://github.com/dsoubry/machinery" style="color: #3498db;">GitHub Repository</a> | 
               <a href="https://transparency.entsoe.eu/" style="color: #3498db;">ENTSO-E Platform</a></p>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        // Simple chart
        const ctx = document.getElementById('priceChart').getContext('2d');
        
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(chart_data['labels'])},
                datasets: [{{
                    label: 'Price (€/MWh)',
                    data: {json.dumps(chart_data['prices'])},
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52, 152, 219, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }},
                scales: {{
                    y: {{
                        title: {{
                            display: true,
                            text: 'Price (€/MWh)'
                        }},
                        beginAtZero: false
                    }},
                    x: {{
                        title: {{
                            display: true,
                            text: 'Hour'
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
    """Generate simple error page"""
    return """<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Belgian Electricity Prices - No Data</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 50px;
            text-align: center;
            background: #f9f9f9;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚠️ No Price Data Available</h1>
        <p>Day-ahead electricity prices are currently not available.</p>
        <p>Please try again later or check the GitHub Actions for more information.</p>
        <p><a href="https://github.com/dsoubry/machinery/actions">View GitHub Actions</a></p>
    </div>
</body>
</html>"""

def main():
    """Generate clean HTML report"""
    print("🌐 Generating clean HTML report...")
    
    data = load_latest_data()
    html_content = generate_html_report(data)
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("✅ Clean index.html generated")

if __name__ == "__main__":
    main()
