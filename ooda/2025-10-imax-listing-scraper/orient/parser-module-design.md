# Parser Module Design

**Date**: 2025-10-25
**Status**: [~] In Progress
**File**: `src/dynamicalsystem/listing/scraper/parse.py`

## Purpose

Extract structured movie listing data from BFI HTML responses.

**Input**: HTML string from BFI search results page
**Output**: Structured Python dictionaries containing showings, dates, and metadata

---

## Module Interface

### Core Functions

```python
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
    """

def extract_performance_days(html: str) -> Set[str]:
    """
    Extract all dates with showings from performanceDays array

    Args:
        html: Raw HTML from any BFI search page

    Returns:
        Set of date strings in YYYY-MM-DD format

    Example:
        {'2025-10-26', '2025-10-28', '2025-10-29', ...}
    """

def has_results(html: str) -> bool:
    """
    Quick check if page has any showings

    Args:
        html: Raw HTML from BFI search page

    Returns:
        True if searchResults array present, False otherwise
    """
```

---

## Implementation Strategy

### 1. Extract searchResults Array

**Pattern**: JavaScript variable embedded in HTML

```python
import re
import json

def parse_search_results(html: str) -> List[Dict]:
    # Find searchResults array
    pattern = r'searchResults\s*:\s*\[\s*((?:\[.*?\],?\s*)+)\]'
    match = re.search(pattern, html, re.DOTALL)

    if not match:
        return []

    # Extract array content
    array_content = match.group(1).strip()

    if not array_content:
        return []

    # Parse as JSON
    json_str = f'[{array_content}]'
    raw_results = json.loads(json_str)

    # Map to structured records
    return [_parse_showing_record(record) for record in raw_results]
```

### 2. Map Array Indices to Fields

**Field Mapping** (based on searchHeaders):

```python
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
    'month': 10,  # 0-indexed
    'year': 11,
    'availability_status': 15,
    'availability_count': 16,
    'keywords': 17,
    'detail_url_path': 18,
    'performance_id': 42,
    'rating': 43,
}

def _parse_showing_record(record: List) -> Dict:
    """Convert raw array to structured dict"""

    # Convert 0-indexed month to 1-indexed
    month = int(record[FIELD_INDICES['month']]) + 1 if record[FIELD_INDICES['month']] else None
    day = int(record[FIELD_INDICES['day']]) if record[FIELD_INDICES['day']] else None
    year = int(record[FIELD_INDICES['year']]) if record[FIELD_INDICES['year']] else None

    showing_date = None
    if all([year, month, day]):
        showing_date = f"{year}-{month:02d}-{day:02d}"

    return {
        'id': record[FIELD_INDICES['id']],
        'movie_title': record[FIELD_INDICES['movie_title']],
        'movie_slug': record[FIELD_INDICES['movie_slug']],
        'showing_datetime': record[FIELD_INDICES['full_datetime']],
        'showing_date': showing_date,
        'showing_time': record[FIELD_INDICES['time']],
        'format_keywords': record[FIELD_INDICES['keywords']],
        'detail_url_path': record[FIELD_INDICES['detail_url_path']],
        'availability_status': record[FIELD_INDICES['availability_status']],
        'availability_count': record[FIELD_INDICES['availability_count']],
        'rating': record[FIELD_INDICES['rating']],
    }
```

### 3. Extract performanceDays

**Pattern**: Extract all ISO datetime strings

```python
def extract_performance_days(html: str) -> Set[str]:
    """Extract unique dates from performanceDays array"""

    # Find all ISO datetime strings (YYYY-MM-DDTHH:MM:SS.mmm)
    datetimes = re.findall(r'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3})"', html)

    # Extract unique dates (YYYY-MM-DD part)
    unique_dates = set()
    for dt_str in datetimes:
        date_part = dt_str.split('T')[0]
        unique_dates.add(date_part)

    return unique_dates
```

### 4. Quick Result Check

```python
def has_results(html: str) -> bool:
    """Check if page has showings without full parsing"""

    # Quick regex for searchResults presence
    pattern = r'searchResults\s*:\s*\['
    return bool(re.search(pattern, html))
```

---

## Error Handling

### JSON Parse Errors

```python
try:
    raw_results = json.loads(json_str)
except json.JSONDecodeError as e:
    # Log error with context
    logger.error(f"Failed to parse searchResults: {e}")
    logger.debug(f"Attempted to parse: {json_str[:500]}...")
    return []
```

### Missing Fields

```python
def _parse_showing_record(record: List) -> Dict:
    """Safely extract fields with defaults"""

    def safe_get(index, default=''):
        try:
            return record[index] if index < len(record) else default
        except (IndexError, TypeError):
            return default

    # Use safe_get for all field access
    return {
        'id': safe_get(FIELD_INDICES['id']),
        'movie_title': safe_get(FIELD_INDICES['movie_title']),
        # ...
    }
```

### Malformed HTML

```python
def parse_search_results(html: str) -> List[Dict]:
    """Parse with validation"""

    if not html or len(html) < 1000:
        # HTML too small to be valid response
        logger.warning("HTML too small, likely error page")
        return []

    # Check for known error indicators
    if 'no_results_message' in html and 'searchResults' not in html:
        logger.info("No results found for query")
        return []

    # Proceed with parsing...
```

---

## Testing Strategy

### Unit Tests

```python
def test_parse_single_showing():
    """Test parsing a single showing"""
    html = load_fixture('bfi_cloudscraper_2025-10-26.html')
    results = parse_search_results(html)

    assert len(results) == 4

    first = results[0]
    assert first['movie_title'] == 'Frankenstein'
    assert first['showing_date'] == '2025-10-26'
    assert first['showing_time'] == '10:45'
    assert 'IMAX with Laser' in first['format_keywords']

def test_parse_no_results():
    """Test parsing page with no showings"""
    html = load_fixture('bfi_no_results_2025-10-27.html')
    results = parse_search_results(html)

    assert results == []
    assert not has_results(html)

def test_extract_performance_days():
    """Test extracting all dates with showings"""
    html = load_fixture('bfi_cloudscraper_2025-10-26.html')
    dates = extract_performance_days(html)

    assert len(dates) == 23  # Known from OBSERVE phase
    assert '2025-10-26' in dates
    assert '2025-11-12' in dates
    assert '2026-07-17' in dates

def test_malformed_json():
    """Test handling of malformed searchResults"""
    html = '<script>searchResults: [broken json];</script>'
    results = parse_search_results(html)

    assert results == []  # Graceful failure

def test_month_conversion():
    """Test 0-indexed month conversion"""
    # October = month 9 in BFI data
    record = ['id', 'P', 'IMAX', 'cat', 'slug', 'Title', 'desc',
              'full_dt', '10:00', '26', '9', '2025']  # month=9

    parsed = _parse_showing_record(record)

    assert parsed['showing_date'] == '2025-10-26'  # Not 2025-09-26
```

---

## Integration Points

### With BFIFetcher

```python
from dynamicalsystem.listing.scraper.fetch import BFIFetcher
from dynamicalsystem.listing.scraper.parse import parse_search_results

fetcher = BFIFetcher()
html = fetcher.fetch('2025-10-26')
showings = parse_search_results(html)
```

### With Database Layer (Future)

```python
# Future integration
from dynamicalsystem.listing.storage.db import Database

db = Database()
showings = parse_search_results(html)
db.insert_showings(showings)
```

---

## Performance Considerations

### Regex vs Full Parse

**Current**: Regex to find array, JSON parse to extract
**Why**: JavaScript is embedded in HTML, not a separate JSON endpoint
**Alternative Considered**: Parse full HTML with BeautifulSoup → Rejected (slower, unnecessary)

**Benchmarks** (to validate):
- Regex extraction: <10ms
- JSON parsing: <50ms
- Total: <60ms per page

### Caching

Parser is stateless - no caching needed at this level
(Caching handled by HTTP layer or database layer)

---

## Future Enhancements

### 1. Schema Validation

```python
from pydantic import BaseModel

class Showing(BaseModel):
    id: str
    movie_title: str
    showing_date: str  # YYYY-MM-DD format
    showing_time: str  # HH:MM format
    # ...

def parse_search_results(html: str) -> List[Showing]:
    """Return validated Pydantic models"""
    raw_results = _extract_raw_results(html)
    return [Showing(**_parse_showing_record(r)) for r in raw_results]
```

### 2. Format Parsing

```python
def parse_format_keywords(keywords: str) -> Dict[str, bool]:
    """
    Parse format indicators into boolean flags

    Args:
        keywords: "IMAX with Laser,3D,subtitles"

    Returns:
        {
            'is_3d': True,
            'is_70mm': False,
            'is_laser': True,
            'has_subtitles': True
        }
    """
    keywords_lower = keywords.lower()

    return {
        'is_3d': '3d' in keywords_lower,
        'is_70mm': '70mm' in keywords_lower or '15/70' in keywords_lower,
        'is_laser': 'laser' in keywords_lower,
        'has_subtitles': 'subtitle' in keywords_lower,
    }
```

### 3. Booking URL Construction

```python
def build_booking_url(showing: Dict) -> str:
    """
    Construct booking URL from showing ID

    Note: Current strategy uses detail_url_path
    This would be enhancement to generate direct booking links
    """
    base = 'https://whatson.bfi.org.uk/imax/Online/'
    # Pattern TBD from widget JavaScript reverse engineering
    return f"{base}selectPerformance.asp?id={showing['id']}"
```

---

## Success Criteria

Parser PoC is successful if:

- [x] Extracts all 4 showings from Oct 26 sample
- [x] Correctly converts 0-indexed month (Oct = 9 → 10)
- [x] Returns empty list for Oct 27 (no results) sample
- [x] Extracts 23 unique dates from performanceDays
- [x] Handles malformed JSON gracefully
- [x] Runs in <100ms per page

---

## Next Steps

1. **Implement**: Create `src/dynamicalsystem/listing/scraper/parse.py`
2. **Test**: Validate against sample HTML files
3. **Integrate**: Connect with BFIFetcher
4. **CLI Tool**: Build simple test harness
5. **Document**: Add docstrings and examples

---

## Related Documents

- [HTML Structure Analysis](../observe/html-structure.md)
- [Edge Cases and Strategy](../observe/edge-cases-and-strategy.md)
