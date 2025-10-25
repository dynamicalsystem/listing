#!/usr/bin/env python3
"""
Test cloudscraper's ability to bypass Cloudflare on BFI website.

OBSERVE phase experiment: Validate if cloudscraper can access BFI IMAX site
without needing headless browser.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dynamicalsystem.bfiimax.scraper.fetch import BFIFetcher


def test_cloudscraper():
    """Test cloudscraper against BFI website."""
    # Test date: tomorrow
    test_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    print("=" * 80)
    print("CLOUDSCRAPER TEST - BFI IMAX Website Access")
    print("=" * 80)
    print(f"\nTest date: {test_date}")
    print(f"Testing: Cloudflare bypass with cloudscraper library")
    print()

    try:
        fetcher = BFIFetcher()
        url = fetcher.build_url(test_date)
        print(f"URL: {url}\n")

        print("[...] Attempting to fetch page (this may take 10-30 seconds)...")
        html = fetcher.fetch(test_date)

        print(f"[/] SUCCESS - Got {len(html)} bytes")
        print()

        # Analyze response
        html_lower = html.lower()

        # Check for Cloudflare challenge
        if 'cloudflare' in html_lower and 'challenge' in html_lower:
            print("[x] FAILED - Still getting Cloudflare challenge page")
            print("    cloudscraper did not bypass Cloudflare")
            return False

        # Check for HTML structure
        if '<html' not in html_lower:
            print("[x] FAILED - Response doesn't look like HTML")
            return False

        print("[/] Response contains valid HTML")

        # Check for BFI-specific content
        if 'bfi' in html_lower or 'imax' in html_lower:
            print("[/] Response contains BFI/IMAX content")
        else:
            print("[?] WARNING - No obvious BFI/IMAX content found")

        # Save sample
        sample_file = Path(__file__).parent / f'bfi_cloudscraper_{test_date}.html'
        sample_file.write_text(html, encoding='utf-8')
        print(f"[/] Saved HTML to: {sample_file}")
        print()

        # Show preview
        print("First 500 characters:")
        print("-" * 80)
        print(html[:500])
        print("-" * 80)
        print()

        # Test BeautifulSoup parsing
        print("[...] Testing BeautifulSoup parsing...")
        soup = fetcher.fetch_soup(test_date)
        print(f"[/] BeautifulSoup parsed successfully")
        print(f"    Title: {soup.title.string if soup.title else 'N/A'}")
        print()

        print("=" * 80)
        print("RESULT: [/] CLOUDSCRAPER WORKS")
        print("=" * 80)
        print()
        print("Next steps:")
        print("  1. Examine saved HTML file for structure")
        print("  2. Identify movie listing elements")
        print("  3. Write parser for listings")
        print("  4. Document findings in website-constraints.md")
        print()

        return True

    except Exception as e:
        print(f"[x] FAILED - Exception occurred")
        print(f"    Error: {e}")
        print()
        print("=" * 80)
        print("RESULT: [x] CLOUDSCRAPER FAILED")
        print("=" * 80)
        print()
        print("Next steps:")
        print("  1. Try headless browser (Playwright/Selenium)")
        print("  2. Document findings in website-constraints.md")
        print()

        return False


if __name__ == "__main__":
    success = test_cloudscraper()
    sys.exit(0 if success else 1)
