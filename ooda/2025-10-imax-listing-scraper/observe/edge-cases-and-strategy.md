# Edge Cases and Scraping Strategy

**Date**: 2025-10-25
**Status**: [x] Complete

## Edge Case Testing Results

### 1. No Results (Oct 27, 2025)

**Test**: Fetch `2025-10-27` (Monday with no showings)

**Result**:
- HTTP 200 OK response
- HTML size: 89,645 bytes (vs 103,852 bytes with results)
- **No `searchResults` array present** in JavaScript
- Page contains `no_results_message` in `searchLabels`

**Message Shown**:
> "We cannot find the film or event you're looking for. This may be because the date it was on has passed.
>
> This search is only for films and events. For other information and pages, use our top menu or the footer."

**Parser Implication**:
```python
# Check for presence of searchResults
pattern = r'searchResults\s*:\s*\['
if not re.search(pattern, html):
    return []  # No showings
```

**Files**: `experiments/bfi_no_results_2025-10-27.html`

---

### 2. Partial Day (Nov 12, 2025)

**Test**: Fetch `2025-11-12` (day with only 1 showing)

**Result**:
- HTTP 200 OK response
- HTML size: 100,784 bytes
- `searchResults` array present with 1 entry
- Showing: "j-Hope Tour 'Hope on the Stage' The Movie" at 20:45

**Observation**: BFI **does add listings ad hoc**, not whole days at once.

**Strategy Implication**:
- Need to track partial vs complete days
- Re-scrape days that might get additional showings
- Watch Nov 12 to see if more showings are added

---

### 3. Calendar Sparsity Analysis

**Test**: Extract all `performanceDays` from Oct 26 fetch

**Results**:
```
Total datetimes found: 78
Unique days with showings: 23
Date range: 2025-10-26 to 2026-07-19
Span: 267 days
Days with showings: 23 days
Gaps (no showings): 244 days
Sparsity: 91.4% empty
```

**Distribution**:
```
2025-10-26: 5 showings
2025-10-28: 5 showings   <- Oct 27 has zero (gap)
2025-10-29: 4 showings
2025-10-30: 3 showings
2025-10-31: 6 showings
2025-11-01: 6 showings
2025-11-02: 4 showings
2025-11-03: 3 showings
2025-11-04: 3 showings
2025-11-05: 1 showing
2025-11-12: 1 showing    <- Gap from Nov 5-12
2025-12-10: 1 showing    <- Gap from Nov 17 to Dec 10
2026-07-17: 2 showings   <- Gap from Dec 10 to Jul 17 (7 months!)
```

**Key Finding**: Calendar is **extremely sparse** (91.4% empty).

---

## Refined Scraping Strategy

### Core Approach: Date-Based Querying

Your assumption is **correct**: Query individual dates, not date ranges.

**Rationale**:
1. URL pattern is `search_from=YYYY-MM-DD&search_to=YYYY-MM-DD`
2. For single day: both params set to same date
3. No evidence BFI expects or optimizes multi-day queries
4. Single-day queries keep responses small and parsing simple

**Rejected Alternative**: Multi-day range queries
- Not needed
- Larger responses
- More complex to track what was fetched

---

### Discovery: Use performanceDays Array

**What it is**: JavaScript array containing ALL performance datetimes across the entire calendar.

**Location**: `articleContext.performanceDays[0].values`

**Format**: Array of `[datetime, "1"]` pairs
```javascript
values: [
  ["2025-10-26T10:45:00.000", "1"],
  ["2025-10-26T14:10:00.000", "1"],
  ...
]
```

**Extraction Strategy**:
```python
# Extract all ISO datetime strings from HTML
datetimes = re.findall(r'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3})"', html)

# Get unique days
unique_days = set(dt.split('T')[0] for dt in datetimes)
```

**Use Cases**:
1. **Horizon scan**: Query any date to get full list of days with showings
2. **Gap detection**: Identify days with zero showings (don't query them)
3. **Incremental updates**: Compare to previous scan to detect new days

---

### Proposed: dates_to_query List

**Data Structure**:
```python
dates_to_query = {
    '2025-10-26': {'status': 'complete', 'showing_count': 4, 'last_scraped': '2025-10-25'},
    '2025-10-27': {'status': 'empty', 'last_checked': '2025-10-25'},
    '2025-10-28': {'status': 'partial', 'showing_count': 5, 'last_scraped': '2025-10-25'},
    '2025-11-12': {'status': 'partial', 'showing_count': 1, 'last_scraped': '2025-10-25'},
    ...
}
```

**Status Definitions**:
- `empty`: Date has no showings (verified)
- `partial`: Date has showings but might get more
- `complete`: Date is in the past or all showings are sold out/locked
- `unknown`: Not yet checked

**Re-scrape Logic**:
```python
def should_rescrape(date_entry):
    # Always re-scrape partial days until they're in the past
    if date_entry['status'] == 'partial' and date < today:
        return False  # In past, mark complete

    if date_entry['status'] == 'partial':
        return True  # Might get more showings

    if date_entry['status'] == 'empty' and date >= today:
        # Re-check empty dates occasionally (weekly?)
        days_since_check = (today - date_entry['last_checked']).days
        return days_since_check > 7

    return False  # Don't re-scrape complete/past dates
```

---

### Horizon Scanning Strategy

**Approach**: Use performanceDays to build horizon efficiently

**Algorithm**:
```python
def update_horizon():
    # 1. Fetch any single date (e.g., today)
    html = fetcher.fetch(today)

    # 2. Extract ALL days with showings from performanceDays
    all_days_with_showings = extract_performance_days(html)

    # 3. Update dates_to_query
    for day in all_days_with_showings:
        if day not in dates_to_query:
            dates_to_query[day] = {'status': 'unknown'}

    # 4. Mark days not in performanceDays as 'empty'
    for day in dates_within_horizon:
        if day not in all_days_with_showings:
            dates_to_query[day] = {'status': 'empty'}

    return dates_to_query
```

**Benefit**: Single HTTP request discovers all dates with showings across entire calendar.

---

### Daily Maintenance Workflow

**Goal**: Minimize requests, catch all updates

**Steps**:
1. **Horizon scan** (1 request)
   ```python
   html = fetcher.fetch(today)
   new_days = extract_performance_days(html)
   update_dates_to_query(new_days)
   ```

2. **Scrape new/partial days** (~10-20 requests/day)
   ```python
   for date, entry in dates_to_query.items():
       if should_rescrape(entry):
           html = fetcher.fetch(date)
           showings = parse_showings(html)
           update_database(date, showings)
           entry['last_scraped'] = today
   ```

3. **Cleanup** (database)
   ```python
   DELETE FROM listings WHERE showing_date < today
   ```

**Estimated Load**:
- Horizon scan: 1 request
- New/partial days: ~15 requests (based on 91% sparsity)
- **Total: ~16 requests/day**

Much better than the proposed 25 requests/day.

---

### Testing Nov 12, 2025 Hypothesis

**Observation**: Nov 12 currently has 1 showing at 20:45

**Hypothesis**: BFI adds showings to days ad hoc, not all at once

**Test Plan**:
1. Record current state (1 showing)
2. Monitor Nov 12 over next week
3. Check if more showings are added

**Possible Outcomes**:
- **More showings added**: Confirms ad hoc addition, keep "partial" status
- **No changes**: Day might be complete (one-off event)
- **Showing removed**: Indicates cancellations happen (rare?)

**Action**: Add monitoring to scraper logs to track changes to specific days.

---

## Updated Architecture Decisions

### dates_to_query Database Table

**Schema**:
```sql
CREATE TABLE scrape_schedule (
    date DATE PRIMARY KEY,
    status TEXT NOT NULL,  -- 'empty', 'partial', 'complete', 'unknown'
    showing_count INTEGER DEFAULT 0,
    last_scraped TIMESTAMP,
    last_checked TIMESTAMP,
    notes TEXT  -- For tracking changes, e.g., "added 3 showings"
);
```

**Indices**:
```sql
CREATE INDEX idx_status ON scrape_schedule(status);
CREATE INDEX idx_last_scraped ON scrape_schedule(last_scraped);
```

---

### Revised Backfill Strategy

**Original Proposal**: Two-tier polling (daily horizon + weekly lookahead)

**Revised Proposal**: Horizon scan + selective scraping

**Comparison**:

| Metric | Original | Revised |
|--------|----------|---------|
| Daily requests | ~25 | ~16 |
| Horizon coverage | 90 days (14 daily + 75 weekly) | Full calendar (267 days) |
| Discovery method | Brute force | performanceDays scan |
| Wasted requests | ~15/day on empty dates | ~0 (we know which are empty) |
| Update detection | Periodic polling | Active monitoring |

**Decision**: Use revised strategy.

---

## Open Questions

### 1. How often does BFI add new showings?

**Hypothesis**: Weekly or bi-weekly schedule updates

**Test**: Monitor dates_to_query changes over 2 weeks

**Metric**: Count of days changing from 'unknown' → 'partial' per day

---

### 2. Do they add/remove showings or entire days?

**Hypothesis**: Add showings ad hoc, rarely remove

**Evidence**: Nov 12 has 1 showing (suggests ad hoc)

**Test**: Track `showing_count` changes for same date

---

### 3. How far ahead do they schedule?

**Current**: Latest showing is 2026-07-19 (267 days ahead)

**Question**: Is this typical or exceptional?

**Test**: Monitor max date in performanceDays over time

**Observation**: Large gap (Dec 10 to Jul 17) suggests sporadic far-future bookings

---

### 4. What triggers a day to go from 'partial' to 'complete'?

**Possible Triggers**:
- Date passes (most certain)
- All showings sold out
- BFI marks schedule as final (unknown mechanism)

**Strategy**: Mark dates as 'complete' once they're in the past.

---

## Implementation Plan (ORIENT Phase)

### Phase 1: Parser Module

**File**: `src/dynamicalsystem/listing/scraper/parse.py`

**Functions**:
- `parse_search_results(html: str) -> List[Dict]`
- `extract_performance_days(html: str) -> Set[str]`
- `detect_empty_results(html: str) -> bool`

---

### Phase 2: Scrape Schedule Manager

**File**: `src/dynamicalsystem/listing/scraper/schedule.py`

**Functions**:
- `update_horizon() -> Set[str]`
- `should_rescrape(date: str) -> bool`
- `mark_complete(date: str)`
- `get_dates_to_scrape() -> List[str]`

---

### Phase 3: Daily Maintenance Script

**File**: `src/dynamicalsystem/listing/maintenance/daily.py`

**Steps**:
1. Horizon scan
2. Scrape new/partial days
3. Update database
4. Cleanup old listings
5. Log statistics

---

## Files Created

- `experiments/bfi_no_results_2025-10-27.html` - Empty results sample
- `experiments/test_parser.py` - Parser validation script

---

## Next Steps

1. **ORIENT Phase**: Design parser and schedule manager modules
2. **Create**: SQLite schema for `scrape_schedule` table
3. **Monitor**: Nov 12, 2025 for additional showings
4. **Implement**: performanceDays extraction function
5. **Test**: Full horizon scan → selective scrape workflow
