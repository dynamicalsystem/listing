# Runtime Fetcher Design

**Date**: 2025-10-26
**Status**: [x] Approved
**File**: `src/dynamicalsystem/listing/scraper/runtime.py`
**Purpose**: Fetch and cache film runtimes for schedule completion detection

---

## Purpose

Extract film runtimes to enable runtime-based schedule completion heuristic (completion-heuristic.md).

**Input**: Movie title
**Output**: Runtime in minutes, source, confidence level

**Sources** (priority order):
1. Database cache (instant)
2. BFI detail page (authoritative)
3. Wikipedia (reliable fallback)
4. IMDb (additional fallback)
5. TMDb (API-based fallback)

---

## Module Interface

### Core Function

```python
def get_runtime(movie_title: str, detail_url_path: str = None, db = None) -> Optional[RuntimeResult]:
    """
    Get runtime for a movie with multi-tier fallback

    Args:
        movie_title: Film title (e.g., "Frankenstein")
        detail_url_path: BFI detail page relative path (if available)
        db: Database connection for caching

    Returns:
        RuntimeResult with fields:
        - runtime_minutes: int
        - source: 'BFI' | 'Wikipedia' | 'IMDb' | 'TMDb' | 'cache'
        - confidence: 'confirmed' | 'estimated' | 'uncertain'
        - source_url: str (where runtime was found)

        Returns None if runtime cannot be determined
    """
```

### Supporting Functions

```python
def fetch_from_bfi(detail_url_path: str) -> Optional[RuntimeResult]:
    """Extract runtime from BFI detail page"""

def fetch_from_wikipedia(movie_title: str) -> Optional[RuntimeResult]:
    """Search Wikipedia and extract runtime"""

def fetch_from_imdb(movie_title: str) -> Optional[RuntimeResult]:
    """Search IMDb and extract runtime"""

def fetch_from_tmdb(movie_title: str, api_key: str) -> Optional[RuntimeResult]:
    """Query TMDb API for runtime"""

def normalize_title_for_search(title: str) -> str:
    """Clean title for external searches (remove format indicators)"""
```

---

## Implementation Strategy

### 1. Database Cache Check (First)

```python
def get_runtime(movie_title: str, detail_url_path: str = None, db = None) -> Optional[RuntimeResult]:
    # Check cache first
    if db:
        cached = db.get_runtime(movie_title)
        if cached:
            return RuntimeResult(
                runtime_minutes=cached['runtime_minutes'],
                source='cache',
                confidence=cached['confidence'],
                source_url=cached['source_url']
            )

    # Cache miss, fetch from sources...
```

**Rationale**: Avoid repeated fetches for same film. BFI shows films multiple times.

### 2. BFI Detail Page Extraction

**URL Construction**:
```python
def fetch_from_bfi(detail_url_path: str) -> Optional[RuntimeResult]:
    """
    Extract runtime from BFI detail page

    Example URL:
    https://whatson.bfi.org.uk/imax/Online/default.asp?doWork::WScontent::loadArticle=Load&...
    """
    if not detail_url_path:
        return None

    base_url = 'https://whatson.bfi.org.uk/imax/Online/'
    full_url = f"{base_url}{detail_url_path}"

    # Fetch with cloudscraper (reuse BFIFetcher)
    html = fetcher.fetch_url(full_url)

    # Extract runtime
    return extract_runtime_from_html(html, full_url)
```

**Extraction Pattern**:
```python
def extract_runtime_from_html(html: str, source_url: str) -> Optional[RuntimeResult]:
    """
    Extract runtime from BFI detail page HTML

    Pattern: "YYYY. XXmin"
    Example: "Republic of Korea 2025. 90min"

    Special cases:
    - "Tbc" or "TBC" → return None (runtime not confirmed)
    - Multiple matches → take first (main feature)
    """
    # Pattern: year followed by runtime in minutes
    runtime_pattern = r'(\d{4})\.\s*(\d+)min'
    match = re.search(runtime_pattern, html)

    if match:
        year, minutes = match.groups()
        return RuntimeResult(
            runtime_minutes=int(minutes),
            source='BFI',
            confidence='confirmed',
            source_url=source_url
        )

    # Check for TBC
    if re.search(r'\bTbc\b|\bTBC\b', html, re.IGNORECASE):
        # Runtime not confirmed, trigger external fallback
        return None

    # No runtime found
    return None
```

**BFI Detail Page Structure** (from experiments):
```html
<div class="articleBody">
    <p>
        Republic of Korea 2025. 90min<br>
        IMAX with Laser<br>
        Cert 15
    </p>
</div>
```

### 3. Wikipedia Fallback

**Search Strategy**:
```python
def fetch_from_wikipedia(movie_title: str) -> Optional[RuntimeResult]:
    """
    Fetch runtime from Wikipedia

    Strategy:
    1. Normalize title (remove format indicators: "3D", "(3D)", etc.)
    2. Try direct article: https://en.wikipedia.org/wiki/{title}_(film)
    3. If 404, try without "_(film)" suffix
    4. Extract from infobox "Running time" field
    """
    normalized = normalize_title_for_search(movie_title)

    # Try with _(film) suffix first (most common for films)
    urls = [
        f"https://en.wikipedia.org/wiki/{normalized}_(film)",
        f"https://en.wikipedia.org/wiki/{normalized}_(2025_film)",
        f"https://en.wikipedia.org/wiki/{normalized}_(2024_film)",
        f"https://en.wikipedia.org/wiki/{normalized}"
    ]

    for url in urls:
        html = safe_fetch(url)
        if html and 'Wikipedia does not have an article' not in html:
            runtime = extract_wikipedia_runtime(html)
            if runtime:
                return RuntimeResult(
                    runtime_minutes=runtime,
                    source='Wikipedia',
                    confidence='confirmed',
                    source_url=url
                )

    return None
```

**Title Normalization**:
```python
def normalize_title_for_search(title: str) -> str:
    """
    Clean title for external searches

    Examples:
    "Frankenstein" → "Frankenstein"
    "Tron: Ares (3D)" → "Tron: Ares"
    "Blue Whales 3D" → "Blue Whales"
    "Chainsaw Man - The Movie: Reze Arc" → "Chainsaw Man: Reze Arc"
    """
    # Remove format indicators
    title = re.sub(r'\s*\(3D\)\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+3D$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*\(IMAX\)\s*', '', title, flags=re.IGNORECASE)

    # Remove "The Movie" subtitle prefix (common for anime)
    title = re.sub(r'\s+-\s+The Movie:\s+', ': ', title)

    # URL-encode for Wikipedia
    title = title.replace(' ', '_')

    return title
```

**Wikipedia Extraction**:
```python
def extract_wikipedia_runtime(html: str) -> Optional[int]:
    """
    Extract runtime from Wikipedia infobox

    Pattern: "Running time" row with "XXX minutes" or "XX min"

    Examples:
    - "150 minutes"
    - "2 hours 30 minutes"
    - "150 min"
    """
    # Pattern 1: Direct minutes
    pattern1 = r'Running time.*?(\d+)\s*min'
    match = re.search(pattern1, html, re.IGNORECASE | re.DOTALL)
    if match:
        return int(match.group(1))

    # Pattern 2: Hours and minutes
    pattern2 = r'Running time.*?(\d+)\s*hour[s]?\s*(\d+)?\s*min'
    match = re.search(pattern2, html, re.IGNORECASE | re.DOTALL)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2)) if match.group(2) else 0
        return hours * 60 + minutes

    return None
```

### 4. IMDb Fallback

**Search Strategy**:
```python
def fetch_from_imdb(movie_title: str) -> Optional[RuntimeResult]:
    """
    Fetch runtime from IMDb

    Strategy:
    1. Use IMDb search: https://www.imdb.com/find?q={title}&s=tt
    2. Extract first film result
    3. Fetch film page
    4. Extract runtime from JSON-LD metadata

    Note: IMDb may block scrapers, use conservatively
    """
    normalized = normalize_title_for_search(movie_title)
    search_url = f"https://www.imdb.com/find?q={normalized}&s=tt"

    # Fetch search results
    html = safe_fetch(search_url, headers={'User-Agent': 'Mozilla/5.0...'})
    if not html:
        return None

    # Extract first film result
    film_url = extract_first_imdb_result(html)
    if not film_url:
        return None

    # Fetch film page
    film_html = safe_fetch(film_url)
    if not film_html:
        return None

    # Extract runtime from JSON-LD
    runtime = extract_imdb_runtime(film_html)
    if runtime:
        return RuntimeResult(
            runtime_minutes=runtime,
            source='IMDb',
            confidence='confirmed',
            source_url=film_url
        )

    return None
```

**IMDb JSON-LD Extraction**:
```python
def extract_imdb_runtime(html: str) -> Optional[int]:
    """
    Extract runtime from IMDb JSON-LD metadata

    IMDb embeds structured data:
    <script type="application/ld+json">
    {
        "@type": "Movie",
        "duration": "PT2H30M"  // ISO 8601 duration
    }
    </script>
    """
    # Find JSON-LD script
    pattern = r'<script type="application/ld\+json">(.*?)</script>'
    matches = re.findall(pattern, html, re.DOTALL)

    for match in matches:
        try:
            data = json.loads(match)
            if data.get('@type') == 'Movie' and 'duration' in data:
                # Parse ISO 8601 duration (PT2H30M)
                duration = data['duration']
                return parse_iso_duration(duration)
        except json.JSONDecodeError:
            continue

    return None

def parse_iso_duration(duration: str) -> int:
    """
    Parse ISO 8601 duration to minutes

    Examples:
    "PT2H30M" → 150
    "PT90M" → 90
    "PT1H45M" → 105
    """
    hours = 0
    minutes = 0

    hour_match = re.search(r'(\d+)H', duration)
    if hour_match:
        hours = int(hour_match.group(1))

    min_match = re.search(r'(\d+)M', duration)
    if min_match:
        minutes = int(min_match.group(1))

    return hours * 60 + minutes
```

### 5. TMDb API Fallback

**API Strategy**:
```python
def fetch_from_tmdb(movie_title: str, api_key: str) -> Optional[RuntimeResult]:
    """
    Fetch runtime from The Movie Database API

    Requires: TMDb API key (free, rate-limited)
    Docs: https://developers.themoviedb.org/3/movies

    Strategy:
    1. Search for movie: /search/movie?query={title}
    2. Get first result ID
    3. Fetch movie details: /movie/{id}
    4. Extract runtime field
    """
    if not api_key:
        return None

    normalized = normalize_title_for_search(movie_title)

    # Search for movie
    search_url = f"https://api.themoviedb.org/3/search/movie"
    params = {
        'api_key': api_key,
        'query': normalized,
        'year': 2025  # Optional: filter by current year
    }

    response = requests.get(search_url, params=params)
    if response.status_code != 200:
        return None

    results = response.json().get('results', [])
    if not results:
        return None

    # Get first result
    movie_id = results[0]['id']

    # Fetch movie details
    detail_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    detail_response = requests.get(detail_url, params={'api_key': api_key})
    if detail_response.status_code != 200:
        return None

    movie_data = detail_response.json()
    runtime = movie_data.get('runtime')

    if runtime:
        return RuntimeResult(
            runtime_minutes=runtime,
            source='TMDb',
            confidence='confirmed',
            source_url=f"https://www.themoviedb.org/movie/{movie_id}"
        )

    return None
```

---

## Caching Strategy

### Cache on First Fetch

```python
def get_runtime(movie_title: str, detail_url_path: str = None, db = None) -> Optional[RuntimeResult]:
    # ... check cache ...

    # Try fetching from sources
    sources = [
        (fetch_from_bfi, detail_url_path),
        (fetch_from_wikipedia, movie_title),
        (fetch_from_imdb, movie_title),
        (fetch_from_tmdb, movie_title)
    ]

    for fetch_func, arg in sources:
        if arg is None:
            continue

        try:
            result = fetch_func(arg)
            if result:
                # Cache successful fetch
                if db:
                    db.cache_runtime(
                        movie_title=movie_title,
                        runtime_minutes=result.runtime_minutes,
                        source=result.source,
                        source_url=result.source_url,
                        confidence=result.confidence
                    )
                return result
        except Exception as e:
            logger.warning(f"Failed to fetch runtime from {fetch_func.__name__}: {e}")
            continue

    # No runtime found from any source
    return None
```

### Cache Miss Handling

```python
# If no runtime found, cache a "not found" marker to avoid repeated lookups
if db and result is None:
    db.cache_runtime(
        movie_title=movie_title,
        runtime_minutes=120,  # Default estimate
        source='estimated',
        source_url=None,
        confidence='uncertain'
    )
```

---

## Rate Limiting

### Respectful Scraping

```python
from time import sleep
from functools import lru_cache

class RateLimiter:
    """Simple rate limiter for external requests"""

    def __init__(self):
        self.last_request = {}
        self.delays = {
            'wikipedia': 1.0,  # 1 second between Wikipedia requests
            'imdb': 2.0,       # 2 seconds between IMDb requests
            'tmdb': 0.5        # 0.5 seconds for API (has built-in rate limits)
        }

    def wait(self, service: str):
        """Wait if needed before making request to service"""
        if service in self.last_request:
            elapsed = time.time() - self.last_request[service]
            delay = self.delays.get(service, 1.0)
            if elapsed < delay:
                sleep(delay - elapsed)

        self.last_request[service] = time.time()

# Global rate limiter
rate_limiter = RateLimiter()

def safe_fetch(url: str, service: str = None) -> Optional[str]:
    """Fetch URL with rate limiting and error handling"""
    if service:
        rate_limiter.wait(service)

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")

    return None
```

---

## Error Handling

### Graceful Degradation

```python
def get_runtime(movie_title: str, detail_url_path: str = None, db = None) -> Optional[RuntimeResult]:
    """Runtime fetcher never raises exceptions, always returns None on failure"""

    try:
        # ... fetch logic ...
    except requests.RequestException as e:
        logger.error(f"Network error fetching runtime for {movie_title}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for {movie_title}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching runtime for {movie_title}: {e}")
        return None
```

### Logging

```python
import logging

logger = logging.getLogger('listing.runtime')

def get_runtime(movie_title: str, detail_url_path: str = None, db = None) -> Optional[RuntimeResult]:
    logger.info(f"Fetching runtime for: {movie_title}")

    # Check cache
    if cached:
        logger.info(f"Runtime cache hit: {movie_title} → {cached['runtime_minutes']}min ({cached['source']})")
        return cached

    # Try sources
    logger.debug(f"Cache miss, trying external sources for: {movie_title}")

    # ... fetch ...

    if result:
        logger.info(f"Runtime found: {movie_title} → {result.runtime_minutes}min (source: {result.source})")
    else:
        logger.warning(f"Runtime not found for: {movie_title}")
```

---

## Testing Strategy

### Unit Tests

```python
def test_extract_bfi_runtime():
    """Test BFI runtime extraction from HTML"""
    html = """
    <div class="articleBody">
        <p>Republic of Korea 2025. 90min<br>IMAX with Laser</p>
    </div>
    """
    result = extract_runtime_from_html(html, 'test_url')
    assert result.runtime_minutes == 90
    assert result.source == 'BFI'
    assert result.confidence == 'confirmed'

def test_bfi_runtime_tbc():
    """Test TBC handling"""
    html = "<p>Republic of Korea 2025. Tbc<br>IMAX with Laser</p>"
    result = extract_runtime_from_html(html, 'test_url')
    assert result is None

def test_normalize_title():
    """Test title normalization for search"""
    assert normalize_title_for_search("Tron: Ares (3D)") == "Tron:_Ares"
    assert normalize_title_for_search("Blue Whales 3D") == "Blue_Whales"
    assert normalize_title_for_search("Frankenstein") == "Frankenstein"

def test_wikipedia_runtime_extraction():
    """Test Wikipedia infobox parsing"""
    html = """
    <tr><th>Running time</th><td>150 minutes</td></tr>
    """
    assert extract_wikipedia_runtime(html) == 150

    html2 = """
    <tr><th>Running time</th><td>2 hours 30 minutes</td></tr>
    """
    assert extract_wikipedia_runtime(html2) == 150

def test_iso_duration_parsing():
    """Test ISO 8601 duration parsing"""
    assert parse_iso_duration("PT2H30M") == 150
    assert parse_iso_duration("PT90M") == 90
    assert parse_iso_duration("PT1H45M") == 105
```

### Integration Tests (with Fixtures)

```python
def test_get_runtime_with_cache(db):
    """Test cache hit"""
    # Prime cache
    db.cache_runtime("Frankenstein", 150, "BFI", "url", "confirmed")

    # Fetch should hit cache
    result = get_runtime("Frankenstein", db=db)
    assert result.runtime_minutes == 150
    assert result.source == "cache"

def test_get_runtime_bfi_fetch(mock_fetcher):
    """Test BFI fetch on cache miss"""
    mock_fetcher.return_value = "<p>2025. 150min</p>"

    result = get_runtime("Test Movie", detail_url_path="test.asp")
    assert result.runtime_minutes == 150
    assert result.source == "BFI"

def test_get_runtime_wikipedia_fallback(mock_fetcher):
    """Test Wikipedia fallback when BFI has TBC"""
    mock_fetcher.side_effect = [
        "<p>2025. Tbc</p>",  # BFI returns TBC
        "<tr><th>Running time</th><td>150 minutes</td></tr>"  # Wikipedia
    ]

    result = get_runtime("Test Movie", detail_url_path="test.asp")
    assert result.runtime_minutes == 150
    assert result.source == "Wikipedia"
```

### Live Tests (Manual)

```python
def test_live_frankenstein_wikipedia():
    """Live test against Wikipedia (manual, not in CI)"""
    result = fetch_from_wikipedia("Frankenstein (2025 film)")
    assert result is not None
    assert result.runtime_minutes > 0
    assert result.source == "Wikipedia"

# Mark as manual/skip in CI
test_live_frankenstein_wikipedia.__test__ = False
```

---

## Configuration

### Settings

```python
# src/dynamicalsystem/listing/config.py

class Config:
    # External API keys
    TMDB_API_KEY = os.getenv('TMDB_API_KEY', None)

    # Rate limits (seconds between requests)
    WIKIPEDIA_DELAY = 1.0
    IMDB_DELAY = 2.0
    TMDB_DELAY = 0.5

    # Timeouts
    HTTP_TIMEOUT = 10  # seconds

    # Caching
    CACHE_DEFAULT_RUNTIME = 120  # minutes (estimate when nothing found)

    # Retry
    MAX_RETRIES = 2
    RETRY_DELAY = 5  # seconds
```

---

## Integration Points

### With Database Layer

```python
# In db.py

def get_runtime(self, movie_title: str) -> Optional[Dict]:
    """Get cached runtime from database"""
    cursor = self.conn.execute(
        "SELECT runtime_minutes, source, source_url, confidence, fetched_at "
        "FROM movie_runtimes WHERE movie_title = ?",
        (movie_title,)
    )
    row = cursor.fetchone()
    return dict(row) if row else None

def cache_runtime(self, movie_title: str, runtime_minutes: int, source: str,
                  source_url: str = None, confidence: str = 'confirmed'):
    """Cache runtime to database"""
    self.conn.execute(
        """INSERT OR REPLACE INTO movie_runtimes
           (movie_title, runtime_minutes, source, source_url, confidence)
           VALUES (?, ?, ?, ?, ?)""",
        (movie_title, runtime_minutes, source, source_url, confidence)
    )
    self.conn.commit()
```

### With Schedule Manager

```python
# In schedule.py

def is_day_complete(date: str, showings: List[Dict]) -> bool:
    """Check if day's schedule is complete using runtime model"""

    # Get runtimes for all showings
    runtimes = {}
    for showing in showings:
        runtime_result = get_runtime(
            showing['movie_title'],
            showing.get('detail_url_path'),
            db=db
        )
        if runtime_result:
            runtimes[showing['id']] = runtime_result.runtime_minutes
        else:
            # Can't model without runtime, assume incomplete
            return False

    # Model schedule with runtimes
    return model_schedule_gaps(showings, runtimes)
```

---

## Performance Considerations

### Batch Processing

```python
def get_runtimes_batch(movies: List[Dict], db = None) -> Dict[str, RuntimeResult]:
    """
    Fetch runtimes for multiple movies efficiently

    Strategy:
    1. Check cache for all movies first
    2. Batch external requests where possible
    3. Return partial results if some fail
    """
    results = {}

    # Check cache for all
    cache_hits = {}
    cache_misses = []

    for movie in movies:
        cached = db.get_runtime(movie['title']) if db else None
        if cached:
            cache_hits[movie['title']] = cached
        else:
            cache_misses.append(movie)

    logger.info(f"Runtime cache: {len(cache_hits)} hits, {len(cache_misses)} misses")

    # Fetch misses (with rate limiting)
    for movie in cache_misses:
        result = get_runtime(movie['title'], movie.get('detail_url_path'), db)
        if result:
            results[movie['title']] = result

    # Combine cache hits and fresh fetches
    results.update(cache_hits)

    return results
```

### Concurrent Fetching

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_runtimes_concurrent(movies: List[Dict], db = None, max_workers: int = 3) -> Dict[str, RuntimeResult]:
    """
    Fetch runtimes concurrently (respecting rate limits)

    Note: Be conservative with concurrency to respect external sites
    """
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(get_runtime, m['title'], m.get('detail_url_path'), db): m['title']
            for m in movies
        }

        for future in as_completed(futures):
            title = futures[future]
            try:
                result = future.result()
                if result:
                    results[title] = result
            except Exception as e:
                logger.error(f"Concurrent fetch failed for {title}: {e}")

    return results
```

---

## Estimated Performance

### Cache Hit (Database)
- **Latency**: <1ms
- **Cost**: Zero external requests

### BFI Detail Page Fetch
- **Latency**: ~10-15 seconds (Cloudflare challenge)
- **Cost**: 1 request to BFI

### Wikipedia Fallback
- **Latency**: ~1-2 seconds
- **Cost**: 1-4 requests (trying different URL patterns)

### Daily Load Estimate
- **New films per day**: ~2-3
- **Total runtime fetches**: 2-3 (rest from cache)
- **External requests**: 2-3 × 1-2 = ~3-6 requests/day

**Acceptable**: Low impact on external sites.

---

## Design Decisions (2025-10-26)

### 1. Simplified External Sources

**Decision**: BFI detail page → Wikipedia fallback only. Remove IMDb and TMDb.

**Rationale**:
- Wikipedia has good coverage for mainstream films
- More stable/reliable than IMDb (less likely to block)
- Simpler implementation (direct URL, no search step)
- Two-tier approach is sufficient for our needs

**Impact**:
- Fewer external requests (~2-3/day vs 6-9/day)
- Simpler error handling
- Less maintenance (fewer APIs to track)

### 2. Simplified Confidence Model

**Decision**: Remove confidence field entirely. Runtime is either known (INTEGER) or unknown (NULL).

**Rationale**:
- Over-engineered: 'confirmed' vs 'estimated' vs 'uncertain' adds no value
- NULL clearly means "we haven't found it yet, retry next time"
- INTEGER clearly means "we know it, use it for completion detection"
- Database schema is simpler

**Old Schema**:
```sql
confidence TEXT  -- 'confirmed', 'estimated', 'uncertain'
```

**New Schema**:
```sql
runtime_minutes INTEGER  -- NULL = unknown, INTEGER = known
```

**Impact**:
- Completion detection only uses known runtimes (NULL = mark day incomplete)
- No need for confidence thresholds or special handling
- Cache logic simplified: only cache successful finds

### 3. No Stale Runtime Tracking

**Decision**: Don't cache unavailable runtimes. Simply return None and retry next time.

**Rationale**:
- If runtime not found, don't cache NULL (or cache failure)
- Next scrape will naturally retry
- No need for `last_checked` field or weekly re-check logic
- Simpler database queries

**Impact**:
- Slight increase in external requests (retry on each scrape until found)
- But most films will be found first try (BFI or Wikipedia)
- Trade simplicity for minimal extra requests

### 4. Minimal Database Fields

**Decision**: Keep only essential fields in movie_runtimes table.

**Fields**:
- `movie_title` (PRIMARY KEY)
- `runtime_minutes` (INTEGER, NULL if unknown)
- `source` (TEXT: 'BFI' or 'Wikipedia' - for audit only)
- `fetched_at` (TEXT: ISO 8601 UTC timestamp)

**Removed**:
- `confidence` (redundant - covered by NULL vs INTEGER)
- `source_url` (adds complexity, not needed for operation)
- `last_checked` (not needed with no-cache-on-failure approach)

**Impact on schema.py**: Requires update to movie_runtimes table definition
**Impact on db.py**: Requires update to cache_runtime() and get_runtime() methods

---

## Next Steps

1. [ ] **Review**: Simon reviews design
2. [ ] **Implement**: Core module (`runtime.py`)
3. [ ] **Implement**: BFI extraction
4. [ ] **Implement**: Wikipedia fallback
5. [ ] **Test**: Unit tests for extraction patterns
6. [ ] **Test**: Integration test with database caching
7. [ ] **Integrate**: Connect to schedule manager
8. [ ] **Document**: Update decision.md

---

## Success Criteria

Runtime fetcher is successful if:

- [ ] BFI runtime extraction works for 90%+ of films
- [ ] Wikipedia fallback finds runtime for 80%+ of "TBC" films
- [ ] Cache hit rate >90% after first day
- [ ] External requests <10/day average
- [ ] No external service blocking/rate limiting
- [ ] Graceful failure (never crashes scraper)

---

## Related Documents

- [Completion Heuristic](../observe/completion-heuristic.md) - Why runtimes are needed
- [SQLite Schema](./sqlite-schema-design.md) - movie_runtimes table
- [Parser Module](./parser-module-design.md) - Provides detail_url_path
- [Decision](../decision.md) - Architecture decisions
