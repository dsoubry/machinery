#!/usr/bin/env python3
"""
Fixed Belgian Day-Ahead Price Scraper - Luminus Alternative Version
This script tries multiple approaches to get pricing data from Luminus or alternatives

Requirements:
- pip install requests beautifulsoup4 --break-system-packages
"""

import requests
import json
import sys
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

def try_luminus_api_v1():
    """Try original API endpoint"""
    url = "https://my.luminusbusiness.be/api/gas-electricity/dynamic-price"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'nl-BE,nl;q=0.9,en;q=0.8',
        'Referer': 'https://my.luminusbusiness.be/',
    }
    
    try:
        print("Trying original Luminus API endpoint...")
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 404:
            print("❌ Original endpoint returns 404 - API has moved or changed")
            return None
        
        resp.raise_for_status()
        return resp.json()
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Original endpoint failed: {e}")
        return None

def try_luminus_api_v2():
    """Try alternative API endpoints"""
    alternative_urls = [
        "https://www.luminus.be/api/dynamic-prices",
        "https://www.luminus.be/api/spot-prices", 
        "https://api.luminus.be/spot-prices",
        "https://my.luminus.be/api/dynamic-price",
        "https://my.luminus.be/api/gas-electricity/dynamic-price"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'nl-BE,nl;q=0.9,en;q=0.8',
    }
    
    for url in alternative_urls:
        try:
            print(f"Trying alternative endpoint: {url}")
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data:  # Check if we got meaningful data
                        print(f"✅ Success with: {url}")
                        return data
                except json.JSONDecodeError:
                    print(f"❌ Invalid JSON response from: {url}")
                    continue
            else:
                print(f"❌ HTTP {resp.status_code} from: {url}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error with {url}: {e}")
            continue
    
    return None

def try_luminus_scrape():
    """Try to scrape pricing data from Luminus website"""
    try:
        print("Trying to scrape Luminus website...")
        
        # Try main dynamic pricing page
        url = "https://www.luminus.be/nl/particulier/elektriciteit-gas/dynamisch-contract"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        # Look for price information in the page
        # This would need to be adapted based on the actual page structure
        price_elements = soup.find_all(['span', 'div', 'p'], string=lambda text: text and ('€' in text or 'EUR' in text))
        
        if price_elements:
            print("Found potential price elements on the page:")
            for elem in price_elements[:5]:  # Show first 5 matches
                print(f"- {elem.get_text().strip()}")
        
        # Look for JavaScript data or embedded JSON
        script_tags = soup.find_all('script', string=lambda text: text and ('price' in text.lower() or 'euro' in text.lower()))
        
        if script_tags:
            print(f"Found {len(script_tags)} script tags with potential price data")
            # Here you would parse the JavaScript to extract actual price data
        
        print("ℹ️  Website scraping requires manual inspection of page structure")
        return None
        
    except Exception as e:
        print(f"❌ Website scraping failed: {e}")
        return None

def try_elia_spot_price():
    """Try to get spot prices from Elia (Belgian TSO)"""
    try:
        print("Trying Elia day-ahead reference price...")
        
        # Elia provides day-ahead reference prices
        url = "https://www.elia.be/en/grid-data/transmission/day-ahead-reference-price"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        # Look for API endpoints in the page source
        if 'api' in resp.text.lower():
            print("✅ Elia page loaded, but API endpoint extraction needed")
            print("ℹ️  Elia provides official Belgian day-ahead prices")
            print("ℹ️  Consider using ENTSO-E Transparency Platform for direct API access")
        
        return None
        
    except Exception as e:
        print(f"❌ Elia website check failed: {e}")
        return None

def fetch_prices():
    """Try multiple methods to fetch day-ahead prices"""
    print("🔌 Prijsgegevens ophalen van Luminus API...")
    
    # Try original endpoint first
    data = try_luminus_api_v1()
    if data:
        return data
    
    # Try alternative endpoints
    data = try_luminus_api_v2() 
    if data:
        return data
    
    # Try scraping approach
    try_luminus_scrape()
    
    # Try Elia as reference
    try_elia_spot_price()
    
    # If all fails, provide guidance
    print("\n❌ Alle Luminus endpoints gefaald")
    print("\n🔧 OPLOSSINGEN:")
    print("1. Gebruik het nieuwe ENTSO-E script (scrape_entsoe.py)")
    print("2. Registreer op transparency.entsoe.eu voor een gratis API token") 
    print("3. ENTSO-E biedt officiële Europese dag-vooruit prijzen")
    print("4. Meer betrouwbaar dan leverancier-specifieke APIs")
    print("\n📚 Documentatie:")
    print("- ENTSO-E Transparency Platform: https://transparency.entsoe.eu/")
    print("- EPEX SPOT (official Belgian market): https://www.epexspot.com/")
    
    return None

def save_prices(json_data, filename="day_ahead_prices.json"):
    """Save price data to JSON file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"💾 Data saved to {filename}")
        return filename
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        return None

def main():
    """Main function with enhanced error handling"""
    print("🔌 Belgian Day-Ahead Price Scraper (Luminus - Fixed Version)")
    print("=" * 65)
    
    try:
        json_data = fetch_prices()
        
        if json_data:
            print("✅ Pricing data retrieved successfully!")
            
            # Save to file
            filename = save_prices(json_data)
            
            # Display summary if data structure is known
            if isinstance(json_data, dict):
                print(f"\n📊 Data keys: {list(json_data.keys())}")
            elif isinstance(json_data, list):
                print(f"\n📊 Retrieved {len(json_data)} price records")
        else:
            print("\n💡 AANBEVELING: Gebruik scrape_entsoe.py voor betrouwbare prijsdata")
            
    except KeyboardInterrupt:
        print("\n⏹️  Script interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error in main(): {e}")
        print("💡 Try using scrape_entsoe.py instead")

if __name__ == "__main__":
    main()
