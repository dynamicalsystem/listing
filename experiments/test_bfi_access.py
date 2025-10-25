#!/usr/bin/env python3
"""
Test different approaches to access BFI IMAX website.

OBSERVE phase experiment: Determine if HTTP library can access site,
or if headless browser is required.
"""

import sys
from datetime import datetime, timedelta
from urllib.parse import urlencode

# Test date: tomorrow
test_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

# BFI IMAX URL structure
BASE_URL = "https://whatson.bfi.org.uk/imax/Online/default.asp"
PARAMS = {
    'BOset::WScontent::SearchCriteria::venue_filter': '',
    'BOset::WScontent::SearchCriteria::city_filter': '',
    'BOset::WScontent::SearchCriteria::month_filter': '',
    'BOset::WScontent::SearchCriteria::object_type_filter': '',
    'BOset::WScontent::SearchCriteria::category_filter': '',
    'BOset::WScontent::SearchCriteria::search_from': test_date,
    'BOset::WScontent::SearchCriteria::search_to': test_date,
    'doWork::WScontent::search': '1',
    'BOparam::WScontent::search::article_search_id': '49C49C83-6BA0-420C-A784-9B485E36E2E0',
    'BOset::WScontent::SearchCriteria::search_criteria': '',
}

url = f"{BASE_URL}?{urlencode(PARAMS)}"

print(f"Testing BFI website access for date: {test_date}")
print(f"URL: {url}\n")
print("=" * 80)

# Test 1: Basic requests (no special headers)
print("\n[TEST 1] Basic requests library (no User-Agent)")
print("-" * 80)
try:
    import requests

    response = requests.get(url, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Content Length: {len(response.text)}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")

    if response.status_code == 200:
        print("[/] SUCCESS - Basic requests works!")
        print(f"\nFirst 500 chars:\n{response.text[:500]}")
    else:
        print(f"[x] FAILED - Got {response.status_code}")

except requests.exceptions.RequestException as e:
    print(f"[x] ERROR: {e}")
except ImportError:
    print("[x] requests library not installed")

# Test 2: Requests with browser User-Agent
print("\n[TEST 2] Requests with browser User-Agent")
print("-" * 80)
try:
    import requests

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    response = requests.get(url, headers=headers, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Content Length: {len(response.text)}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")

    if response.status_code == 200:
        print("[/] SUCCESS - User-Agent header works!")
        print(f"\nFirst 500 chars:\n{response.text[:500]}")
    else:
        print(f"[x] FAILED - Got {response.status_code}")

except requests.exceptions.RequestException as e:
    print(f"[x] ERROR: {e}")
except ImportError:
    print("[x] requests library not installed")

# Test 3: Requests with full browser headers
print("\n[TEST 3] Requests with full browser headers")
print("-" * 80)
try:
    import requests

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }

    response = requests.get(url, headers=headers, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Content Length: {len(response.text)}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")

    if response.status_code == 200:
        print("[/] SUCCESS - Full browser headers work!")

        # Check if we got HTML
        if '<html' in response.text.lower():
            print("[/] Response contains HTML")

            # Try to find movie listings
            if 'imax' in response.text.lower():
                print("[/] Response mentions 'imax'")

            # Save sample for inspection
            sample_file = f'/Users/dynamicalsystem/Documents/dynamicalsystem/bfiimax/experiments/bfi_sample_{test_date}.html'
            with open(sample_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            print(f"[/] Saved full response to: {sample_file}")

        print(f"\nFirst 500 chars:\n{response.text[:500]}")
    else:
        print(f"[x] FAILED - Got {response.status_code}")

except requests.exceptions.RequestException as e:
    print(f"[x] ERROR: {e}")
except ImportError:
    print("[x] requests library not installed")

print("\n" + "=" * 80)
print("\nSummary:")
print("  - If any test shows [/] SUCCESS, HTTP library approach is viable")
print("  - If all tests show [x] FAILED with 403, need headless browser")
print("  - Check saved HTML file for structure if successful")
print("\nNext steps:")
print("  1. If HTTP works: Examine HTML structure in saved file")
print("  2. If HTTP fails: Try headless browser (Playwright/Selenium)")
print("  3. Document findings in ooda/2025-10-imax-listing-scraper/observe/website-constraints.md")
