#!/usr/bin/env python3
"""
Test script to extract movie data from BFI HTML

The BFI page uses JavaScript to render search results client-side.
Data is embedded in the page as a JavaScript array called searchResults.
"""

import re
import json
from bs4 import BeautifulSoup


def extract_search_results_from_html(html_file):
    """Extract searchResults JavaScript array from HTML"""
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the searchResults array in the JavaScript
    # It's in the format: searchResults : [ [array1], [array2], ... ]
    pattern = r'searchResults\s*:\s*\[\s*((?:\[.*?\],?\s*)+)\]'
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        print("Could not find searchResults array")
        return None

    # Extract the array content
    array_content = match.group(1)

    # Clean up and parse as JSON
    # Wrap in array brackets and parse
    try:
        json_str = f"[{array_content}]"
        results = json.loads(json_str)
        return results
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        return None


def parse_movie_record(record):
    """Parse a single movie record array into a structured dict

    Based on searchHeaders array, the indices are:
    0: id
    1: object_type
    2: type
    3: category
    4: name (slug)
    5: description (movie title)
    6: short_description
    7: start_date (full date time string)
    8: start_date_time (time only)
    9: start_date_date (day of month)
    10: start_date_month (0-indexed month)
    11: start_date_year
    17: keywords (format indicators like "IMAX with Laser", "3D", "70mm")
    18: additional_info (relative URL for movie detail page)
    60: venue_id
    61: venue_name
    77: min_price
    78: max_price
    """

    # Convert 0-indexed month to 1-indexed
    month = int(record[10]) + 1 if record[10] else None

    return {
        'id': record[0],
        'movie_title': record[5],
        'movie_slug': record[4],
        'showing_datetime': record[7],
        'showing_time': record[8],
        'showing_date': f"{record[11]}-{month:02d}-{int(record[9]):02d}" if all([record[11], month, record[9]]) else None,
        'format_keywords': record[17],
        'detail_url_path': record[18],
        'venue_name': record[61],
        'min_price': record[77],
        'max_price': record[78],
    }


def main():
    html_file = 'experiments/bfi_cloudscraper_2025-10-26.html'

    print("Extracting search results from HTML...")
    results = extract_search_results_from_html(html_file)

    if results:
        print(f"\nFound {len(results)} movie listings\n")

        for i, record in enumerate(results[:5]):  # Show first 5
            print(f"--- Record {i+1} ---")
            parsed = parse_movie_record(record)
            for key, value in parsed.items():
                print(f"  {key}: {value}")
            print()

        # Save parsed results
        parsed_all = [parse_movie_record(r) for r in results]
        with open('experiments/parsed_listings.json', 'w', encoding='utf-8') as f:
            json.dump(parsed_all, f, indent=2)
        print(f"Saved {len(parsed_all)} parsed listings to experiments/parsed_listings.json")
    else:
        print("Failed to extract results")


if __name__ == '__main__':
    main()
