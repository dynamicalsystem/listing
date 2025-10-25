#!/usr/bin/env python3
"""
BFI IMAX Parser Module

Extract structured movie listing data from BFI HTML responses.
"""

import re
import json
import logging
from typing import List, Dict, Set, Optional

logger = logging.getLogger(__name__)


# Field indices in searchResults array (from searchHeaders)
FIELD_INDICES = {
    'id': 0,
    'object_type': 1,
    'type': 2,
    'category': 3,
    'movie_slug': 4,
    'movie_title': 5,
    'short_description': 6,
    'full_datetime': 7,
    'time': 8,
    'day': 9,
    'month': 10,  # 0-indexed (October = 9)
    'year': 11,
    'availability_status': 15,
    'availability_count': 16,
    'keywords': 17,
    'detail_url_path': 18,
    'performance_id': 42,
    'rating': 43,
}


def parse_search_results(html: str) -> List[Dict]:
    """
    Extract showing records from BFI search results HTML

    Args:
        html: Raw HTML from BFI search endpoint

    Returns:
        List of showing dictionaries with fields:
        - id: Unique showing ID
        - movie_title: Film title
        - movie_slug: Internal BFI slug
        - showing_datetime: Full datetime string
        - showing_date: YYYY-MM-DD
        - showing_time: HH:MM
        - format_keywords: Format indicators (3D, 70mm, etc)
        - detail_url_path: Relative URL to movie detail page
        - availability_status: L/G/S (Limited/Good/Sold out)
        - availability_count: Seats remaining
        - rating: Age rating (15, 12A, etc)

    Returns empty list if no results found

    Example:
        >>> html = fetcher.fetch('2025-10-26')
        >>> showings = parse_search_results(html)
        >>> len(showings)
        4
        >>> showings[0]['movie_title']
        'Frankenstein'
    """
    # Validate input
    if not html or len(html) < 1000:
        logger.warning("HTML too small, likely error page")
        return []

    # Check for no results indicator
    if 'no_results_message' in html and 'searchResults' not in html:
        logger.info("No results found for query")
        return []

    # Find searchResults array in JavaScript
    pattern = r'searchResults\s*:\s*\[\s*((?:\[.*?\],?\s*)+)\]'
    match = re.search(pattern, html, re.DOTALL)

    if not match:
        logger.warning("searchResults array not found in HTML")
        return []

    # Extract array content
    array_content = match.group(1).strip()

    if not array_content:
        logger.info("searchResults array is empty")
        return []

    # Parse as JSON
    json_str = f'[{array_content}]'

    try:
        raw_results = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse searchResults: {e}")
        logger.debug(f"Attempted to parse: {json_str[:500]}...")
        return []

    # Map to structured records
    showings = []
    for record in raw_results:
        try:
            showing = _parse_showing_record(record)
            showings.append(showing)
        except Exception as e:
            logger.error(f"Failed to parse showing record: {e}")
            logger.debug(f"Record: {record}")
            continue

    logger.info(f"Parsed {len(showings)} showings from HTML")
    return showings


def _parse_showing_record(record: List) -> Dict:
    """
    Convert raw searchResults array entry to structured dict

    Args:
        record: Array from searchResults (90+ fields)

    Returns:
        Structured showing dictionary
    """
    def safe_get(index: int, default='') -> str:
        """Safely extract field with default"""
        try:
            return record[index] if index < len(record) and record[index] else default
        except (IndexError, TypeError):
            return default

    # Extract date components
    day = safe_get(FIELD_INDICES['day'])
    month = safe_get(FIELD_INDICES['month'])  # 0-indexed
    year = safe_get(FIELD_INDICES['year'])

    # Convert to YYYY-MM-DD
    showing_date = None
    if all([year, month, day]):
        try:
            month_int = int(month) + 1  # Convert 0-indexed to 1-indexed
            day_int = int(day)
            year_int = int(year)
            showing_date = f"{year_int}-{month_int:02d}-{day_int:02d}"
        except (ValueError, TypeError):
            logger.warning(f"Invalid date components: year={year}, month={month}, day={day}")

    return {
        'id': safe_get(FIELD_INDICES['id']),
        'movie_title': safe_get(FIELD_INDICES['movie_title']),
        'movie_slug': safe_get(FIELD_INDICES['movie_slug']),
        'showing_datetime': safe_get(FIELD_INDICES['full_datetime']),
        'showing_date': showing_date or '',
        'showing_time': safe_get(FIELD_INDICES['time']),
        'format_keywords': safe_get(FIELD_INDICES['keywords']),
        'detail_url_path': safe_get(FIELD_INDICES['detail_url_path']),
        'availability_status': safe_get(FIELD_INDICES['availability_status']),
        'availability_count': safe_get(FIELD_INDICES['availability_count']),
        'rating': safe_get(FIELD_INDICES['rating']),
    }


def extract_performance_days(html: str) -> Set[str]:
    """
    Extract all dates with showings from performanceDays array

    Args:
        html: Raw HTML from any BFI search page

    Returns:
        Set of date strings in YYYY-MM-DD format

    Example:
        >>> html = fetcher.fetch('2025-10-26')
        >>> dates = extract_performance_days(html)
        >>> '2025-10-26' in dates
        True
        >>> '2025-11-12' in dates
        True
        >>> len(dates)
        23
    """
    # Find all ISO datetime strings (YYYY-MM-DDTHH:MM:SS.mmm)
    datetimes = re.findall(r'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3})"', html)

    # Extract unique dates (YYYY-MM-DD part only)
    unique_dates = set()
    for dt_str in datetimes:
        date_part = dt_str.split('T')[0]
        unique_dates.add(date_part)

    logger.info(f"Extracted {len(unique_dates)} unique dates from performanceDays")
    return unique_dates


def has_results(html: str) -> bool:
    """
    Quick check if page has any showings

    Args:
        html: Raw HTML from BFI search page

    Returns:
        True if searchResults array present, False otherwise

    Example:
        >>> html = fetcher.fetch('2025-10-26')
        >>> has_results(html)
        True
        >>> html_empty = fetcher.fetch('2025-10-27')
        >>> has_results(html_empty)
        False
    """
    # Quick regex for searchResults presence
    pattern = r'searchResults\s*:\s*\['
    return bool(re.search(pattern, html))


def parse_format_keywords(keywords: str) -> Dict[str, bool]:
    """
    Parse format indicators into boolean flags

    Args:
        keywords: Comma-separated keywords (e.g., "IMAX with Laser,3D,subtitles")

    Returns:
        Dictionary of format flags

    Example:
        >>> parse_format_keywords("IMAX with Laser,3D,subtitles")
        {'is_3d': True, 'is_70mm': False, 'is_laser': True, 'has_subtitles': True}
    """
    keywords_lower = keywords.lower()

    return {
        'is_3d': '3d' in keywords_lower,
        'is_70mm': '70mm' in keywords_lower or '15/70' in keywords_lower,
        'is_laser': 'laser' in keywords_lower,
        'has_subtitles': 'subtitle' in keywords_lower,
    }


def build_detail_url(detail_url_path: str) -> str:
    """
    Build full URL to movie detail page

    Args:
        detail_url_path: Relative path from searchResults

    Returns:
        Full URL to detail page

    Example:
        >>> path = "default.asp?doWork::WScontent::loadArticle=Load&..."
        >>> build_detail_url(path)
        'https://whatson.bfi.org.uk/imax/Online/default.asp?...'
    """
    base_url = 'https://whatson.bfi.org.uk/imax/Online/'
    return f"{base_url}{detail_url_path}"
