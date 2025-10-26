#!/usr/bin/env python3
"""Manual test script for RuntimeFetcher with live data.

Run this to verify runtime extraction works with real BFI/Wikipedia pages.
"""

import tempfile
import logging
from pathlib import Path

from dynamicalsystem.listing.scraper.runtime import RuntimeFetcher
from dynamicalsystem.listing.storage.db import Database
from dynamicalsystem.listing.storage.schema import init_database


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)


def test_runtime_fetcher():
    """Test RuntimeFetcher with real data."""
    print("=" * 70)
    print("RuntimeFetcher Manual Test - Live Data")
    print("=" * 70)
    print()

    # Create temp database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        init_database(db_path)
        db = Database(db_path)
        fetcher = RuntimeFetcher(db)

        # Test cases: (title, detail_url_path, expected_source)
        test_cases = [
            # Real BFI films (may change over time)
            ("Interstellar", "film/interstellar.asp", "BFI or Wikipedia"),
            ("Nosferatu", "film/nosferatu.asp", "BFI or Wikipedia"),

            # Wikipedia fallback (titles without BFI URL)
            ("The Dark Knight", None, "Wikipedia"),
            ("Inception", None, "Wikipedia"),

            # Edge case: title with format suffix
            ("Interstellar - The IMAX 2D Experience", None, "Wikipedia"),
        ]

        print("Testing runtime extraction from live sources...")
        print()

        for i, (title, detail_url, expected_source) in enumerate(test_cases, 1):
            print(f"Test {i}: {title}")
            print(f"  Detail URL: {detail_url or 'None (Wikipedia only)'}")

            try:
                runtime = fetcher.get_runtime(title, detail_url_path=detail_url)

                if runtime:
                    print(f"  ✓ Found: {runtime} minutes")

                    # Check if cached
                    cached = db.get_runtime(title)
                    if cached:
                        print(f"  ✓ Cached successfully")
                else:
                    print(f"  ✗ Not found (returned None)")

            except Exception as e:
                print(f"  ✗ Error: {e}")
                logger.exception(f"Failed to fetch runtime for {title}")

            print()

        # Test cache hits
        print("-" * 70)
        print("Testing cache hits...")
        print()

        for title, _, _ in test_cases:
            cached = db.get_runtime(title)
            if cached:
                print(f"✓ {title}: {cached} min (from cache)")
            else:
                print(f"✗ {title}: Not cached")

        print()
        print("=" * 70)
        print("Test complete!")
        print("=" * 70)

    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)


if __name__ == '__main__':
    test_runtime_fetcher()
