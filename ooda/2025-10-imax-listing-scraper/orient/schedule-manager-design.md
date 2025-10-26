# Schedule Manager Design

**Date**: 2025-10-26
**Status**: [x] Approved
**Files**: `schedule.py`, `changes.py`, `completion.py`
**Purpose**: Orchestrate horizon scanning, re-scrape decisions, and change detection

---

## Design Decisions

### Decision 1: Module Split (2025-10-26)

**Problem**: Initial design had single ScheduleManager class doing too much (horizon scanning, priority logic, scraping, change detection, completion detection, batch operations).

**Decision**: Split into 3 focused modules:

1. **`changes.py`** - ChangeDetector
   - Compare snapshots (hash-based quick check)
   - Detect field-level changes (added/removed/modified)
   - Pure comparison logic, no external dependencies

2. **`completion.py`** - CompletionChecker
   - Runtime-based gap modeling
   - Operating hours analysis
   - Pure function of (showings + runtimes)

3. **`schedule.py`** - ScheduleManager (orchestrator)
   - Horizon scanning
   - Simple scraping logic
   - Batch scraping
   - Delegates to ChangeDetector and CompletionChecker

**Rationale**:
- Smaller, focused modules (easier to understand)
- Each testable in isolation
- Clear separation of concerns
- ScheduleManager becomes simpler orchestration layer

**Impact**:
- 3 files instead of 1
- ChangeDetector and CompletionChecker are reusable
- Easier to test edge cases in isolation
- Reduced complexity in each module

### Decision 2: Simplify Re-scrape Logic (2025-10-26)

**Problem**: Original design had 5-tier priority system (unknown, near-term partial, recently changed, far-future partial, empty re-checks). Too complex.

**Analysis**:
- We run daily anyway, so near-term vs far-future distinction is irrelevant
- "Recently changed" is premature - we don't have data showing BFI schedules are unstable
- Empty re-checks redundant - horizon scan catches dates that get showings added
- Priority tiers don't add value when checking daily

**Decision**: Simple binary logic:
1. **Horizon scan** → get all dates with showings (from `performanceDays`)
2. **Filter**: Skip dates marked "complete"
3. **Scrape everything else**
4. **Mark complete** when CompletionChecker confirms

**Rationale**:
- We check daily anyway, so no need for priority tiers
- Horizon scan automatically discovers new dates
- "Complete" status is the only meaningful filter
- Much simpler to implement and understand

**Impact**:
- Removed 5-tier priority system
- No weekly re-check logic needed
- No near-term vs far-future distinction
- Database statuses simplified: unknown, partial, complete, empty
- get_dates_to_scrape() becomes trivial: horizon - complete_dates

---

## Purpose

Manage the lifecycle of date scraping:
1. Discover dates with showings (horizon scan)
2. Track scrape state for each date (scrape_schedule table)
3. Decide which dates need re-scraping today
4. Detect and record schedule changes
5. Determine when dates are "complete" (runtime-based heuristic)

**Key Insight**: We don't blindly scrape all dates. We learn which dates need attention.

---

## Module Interfaces

### 1. ChangeDetector (changes.py)

```python
class ChangeDetector:
    """
    Detects changes between schedule snapshots

    Pure comparison logic - no external dependencies
    """

    def __init__(self, db: Database):
        self.db = db

    def detect_changes(
        self,
        date: str,
        current_showings: List[Dict],
        previous_hash: Optional[str]
    ) -> List[Change]:
        """
        Compare current showings to previous snapshot

        Returns: List of Change objects (added/removed/modified)
        """
```

### 2. CompletionChecker (completion.py)

```python
class CompletionChecker:
    """
    Determines if a date's schedule is complete

    Pure function of showings + runtimes
    """

    def __init__(self, runtime_fetcher: RuntimeFetcher, config: Config):
        self.runtime_fetcher = runtime_fetcher
        self.config = config

    def is_complete(
        self,
        date: str,
        showings: List[Dict]
    ) -> bool:
        """
        Check if schedule is complete using runtime-based modeling

        Algorithm:
        1. Get runtimes for all films
        2. Model time slots (runtime + ads + changeover)
        3. Check for gaps that could fit another showing
        4. Consider operating hours

        Returns: True if complete, False if partial
        """
```

### 3. ScheduleManager (schedule.py)

```python
class ScheduleManager:
    """
    Orchestrates scraping lifecycle

    Delegates to ChangeDetector and CompletionChecker
    """

    def __init__(
        self,
        db: Database,
        fetcher: BFIFetcher,
        runtime_fetcher: RuntimeFetcher,
        change_detector: ChangeDetector,
        completion_checker: CompletionChecker
    ):
        self.db = db
        self.fetcher = fetcher
        self.runtime_fetcher = runtime_fetcher
        self.change_detector = change_detector
        self.completion_checker = completion_checker

    def update_horizon(self) -> HorizonScanResult:
        """
        Scan horizon to discover all dates with showings

        Returns: HorizonScanResult with:
        - dates_discovered: Set[str]
        - new_dates: Set[str] (not in scrape_schedule)
        - removed_dates: Set[str] (no longer in horizon)
        """

    def get_dates_to_scrape(self) -> List[str]:
        """
        Get prioritized list of dates to scrape today

        Returns: List of dates (YYYY-MM-DD) ordered by priority
        """

    def scrape_date(self, date: str) -> ScrapeDateResult:
        """
        Scrape a single date, detect changes, update state

        Returns: ScrapeDateResult with:
        - showing_count: int
        - changes_detected: List[Change]
        - is_complete: bool
        - status: 'empty' | 'partial' | 'complete'
        """

    def scrape_all_pending(self) -> ScrapeRunSummary:
        """
        Scrape all dates that need checking today

        Returns: ScrapeRunSummary with:
        - dates_scraped: int
        - changes_detected: int
        - new_dates_found: int
        - errors: List[str]
        """
```

---

## 1. Horizon Scanning

### Strategy

Use `performanceDays` array to discover all dates with showings in single request.

```python
def update_horizon(self) -> HorizonScanResult:
    """
    Scan horizon to discover dates with showings

    Algorithm:
    1. Fetch any date (use today for speed)
    2. Extract performanceDays array (all dates with showings)
    3. Compare to scrape_schedule (detect new/removed dates)
    4. Update scrape_schedule with new dates
    5. Mark removed dates as 'empty'
    """
    logger.info("Starting horizon scan")

    # Fetch today's page to get performanceDays
    today = datetime.now(ZoneInfo("UTC")).date().isoformat()
    html = self.fetcher.fetch(today)

    if not html:
        logger.error("Horizon scan failed: could not fetch page")
        return HorizonScanResult(dates_discovered=set(), new_dates=set(), removed_dates=set())

    # Extract all dates with showings
    dates_with_showings = extract_performance_days(html)
    logger.info(f"Horizon scan found {len(dates_with_showings)} dates with showings")

    # Get current dates in scrape_schedule
    known_dates = self.db.get_all_scheduled_dates()

    # Identify new dates
    new_dates = dates_with_showings - known_dates
    if new_dates:
        logger.info(f"Found {len(new_dates)} new dates: {sorted(new_dates)[:5]}...")
        for date in new_dates:
            self.db.add_to_scrape_schedule(
                date=date,
                status='unknown',
                first_seen=datetime.now(ZoneInfo("UTC")).isoformat()
            )

    # Identify removed dates (no longer in horizon)
    # Only check dates that were previously 'partial' or 'unknown'
    tracked_dates = self.db.get_dates_by_status(['partial', 'unknown'])
    removed_dates = tracked_dates - dates_with_showings

    if removed_dates:
        # Dates disappeared from horizon - mark as empty or investigate
        logger.warning(f"Dates removed from horizon: {removed_dates}")
        for date in removed_dates:
            # Double-check by direct fetch before marking empty
            self._verify_and_mark_removed(date)

    return HorizonScanResult(
        dates_discovered=dates_with_showings,
        new_dates=new_dates,
        removed_dates=removed_dates
    )
```

### Handling Removed Dates

```python
def _verify_and_mark_removed(self, date: str):
    """
    Verify date is truly empty before marking removed

    Sometimes dates briefly disappear from performanceDays during updates
    """
    logger.info(f"Verifying removed date: {date}")

    # Direct fetch to confirm
    html = self.fetcher.fetch(date)
    has_results = has_results(html)

    if not has_results:
        # Confirmed empty
        logger.info(f"Confirmed empty: {date}")
        self.db.update_scrape_schedule(
            date=date,
            status='empty',
            showing_count=0,
            last_checked=datetime.now(ZoneInfo("UTC")).isoformat()
        )
    else:
        # Still has showings, horizon scan was stale
        logger.warning(f"Date {date} still has showings, horizon was stale")
        # Continue normal scrape processing
```

---

## 2. Re-scrape Logic (Simplified)

### Simple Binary Filter

Since we run daily, we only need to filter out complete dates.

```python
def get_dates_to_scrape(self) -> List[str]:
    """
    Get prioritized list of dates to scrape today

    Priority tiers:
    1. New dates (status='unknown')
    2. Near-term partial dates (<= 14 days away)
    3. Unstable dates (changed recently)
    4. Far-future partial dates (check weekly)
    5. Empty dates (re-check weekly to catch late additions)
    """
    today = datetime.now(ZoneInfo("UTC")).date()
    dates_to_scrape = []

    # Priority 1: Unknown dates (newly discovered)
    unknown = self.db.get_dates_by_status(['unknown'])
    dates_to_scrape.extend(sorted(unknown))
    logger.info(f"Priority 1 (unknown): {len(unknown)} dates")

    # Priority 2: Near-term partial dates
    near_term_end = (today + timedelta(days=14)).isoformat()
    partial_near = self.db.get_partial_dates_in_range(
        start=today.isoformat(),
        end=near_term_end
    )
    dates_to_scrape.extend(sorted(partial_near))
    logger.info(f"Priority 2 (near-term partial): {len(partial_near)} dates")

    # Priority 3: Recently changed dates (check daily for 3 days)
    recently_changed = self.db.get_recently_changed_dates(days=3)
    for date in recently_changed:
        if date not in dates_to_scrape:
            dates_to_scrape.append(date)
    logger.info(f"Priority 3 (recently changed): {len(recently_changed)} dates")

    # Priority 4: Far-future partial (check weekly)
    far_future_partial = self.db.get_partial_dates_after(near_term_end)
    for date in far_future_partial:
        if self._should_check_weekly(date):
            dates_to_scrape.append(date)
    logger.info(f"Priority 4 (far-future partial): {len(far_future_partial)} dates")

    # Priority 5: Empty dates (re-check weekly for late additions)
    empty_dates = self.db.get_dates_by_status(['empty'])
    for date in empty_dates:
        if self._should_check_weekly(date):
            dates_to_scrape.append(date)
    logger.info(f"Priority 5 (empty re-check): {len(empty_dates)} dates")

    # Remove duplicates, keep order
    seen = set()
    unique_dates = []
    for date in dates_to_scrape:
        if date not in seen:
            seen.add(date)
            unique_dates.append(date)

    logger.info(f"Total dates to scrape: {len(unique_dates)}")
    return unique_dates

def _should_check_weekly(self, date: str) -> bool:
    """Check if date is due for weekly re-check"""
    last_checked = self.db.get_last_checked(date)
    if not last_checked:
        return True

    last_checked_dt = datetime.fromisoformat(last_checked)
    now = datetime.now(ZoneInfo("UTC"))
    days_since_check = (now - last_checked_dt).days

    return days_since_check >= 7
```

### Database Queries

```python
# In db.py

def get_dates_by_status(self, statuses: List[str]) -> Set[str]:
    """Get all dates with given status(es)"""
    placeholders = ','.join('?' * len(statuses))
    cursor = self.conn.execute(
        f"SELECT date FROM scrape_schedule WHERE status IN ({placeholders})",
        statuses
    )
    return {row[0] for row in cursor.fetchall()}

def get_partial_dates_in_range(self, start: str, end: str) -> Set[str]:
    """Get partial dates within date range"""
    cursor = self.conn.execute(
        """SELECT date FROM scrape_schedule
           WHERE status = 'partial'
           AND date >= ?
           AND date <= ?""",
        (start, end)
    )
    return {row[0] for row in cursor.fetchall()}

def get_recently_changed_dates(self, days: int) -> Set[str]:
    """Get dates with changes in last N days"""
    cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(days=days)
    cutoff_str = cutoff.isoformat()

    cursor = self.conn.execute(
        """SELECT DISTINCT date FROM schedule_changes
           WHERE detected_at >= ?
           AND change_type IN ('added', 'removed', 'modified')""",
        (cutoff_str,)
    )
    return {row[0] for row in cursor.fetchall()}

def get_last_checked(self, date: str) -> Optional[str]:
    """Get last_checked timestamp for date"""
    cursor = self.conn.execute(
        "SELECT last_checked FROM scrape_schedule WHERE date = ?",
        (date,)
    )
    row = cursor.fetchone()
    return row[0] if row else None
```

---

## 3. Scraping a Single Date

### Complete Workflow

```python
def scrape_date(self, date: str) -> ScrapeDateResult:
    """
    Scrape single date with full change detection

    Steps:
    1. Fetch HTML for date
    2. Parse showings
    3. Get previous snapshot (if exists)
    4. Detect changes
    5. Record new snapshot
    6. Update listings table
    7. Fetch runtimes (if needed)
    8. Determine completion status
    9. Update scrape_schedule
    """
    logger.info(f"Scraping date: {date}")

    # 1. Fetch HTML
    html = self.fetcher.fetch(date)
    if not html:
        logger.error(f"Failed to fetch {date}")
        return ScrapeDateResult(
            date=date,
            showing_count=0,
            changes_detected=[],
            is_complete=False,
            status='error',
            error='fetch_failed'
        )

    # 2. Parse showings
    showings = parse_search_results(html)
    showing_count = len(showings)

    logger.info(f"Parsed {showing_count} showings for {date}")

    if showing_count == 0:
        # No showings found
        self.db.update_scrape_schedule(
            date=date,
            status='empty',
            showing_count=0,
            last_checked=datetime.now(ZoneInfo("UTC")).isoformat()
        )
        return ScrapeDateResult(
            date=date,
            showing_count=0,
            changes_detected=[],
            is_complete=True,
            status='empty'
        )

    # 3. Get previous snapshot
    previous_snapshot = self.db.get_latest_snapshot(date)

    # 4. Detect changes
    changes = []
    if previous_snapshot:
        changes = self._detect_changes(date, showings, previous_snapshot)
        logger.info(f"Detected {len(changes)} changes for {date}")
    else:
        # First time seeing this date with showings
        changes = [Change(
            date=date,
            change_type='first_seen',
            details=f"Date first seen with {showing_count} showings"
        )]

    # 5. Record new snapshot
    snapshot_hash = compute_snapshot_hash(showings)
    snapshot_id = self.db.record_snapshot(
        date=date,
        showing_count=showing_count,
        snapshot_hash=snapshot_hash,
        showings=showings
    )

    # 6. Update listings table
    self.db.upsert_showings(showings)

    # 7. Record changes
    if changes:
        for change in changes:
            self.db.record_change(change, snapshot_id)

    # 8. Fetch runtimes and determine completion
    is_complete = self._check_completion(date, showings)

    # 9. Update scrape_schedule
    status = 'complete' if is_complete else 'partial'
    self.db.update_scrape_schedule(
        date=date,
        status=status,
        showing_count=showing_count,
        is_complete=is_complete,
        last_scraped=datetime.now(ZoneInfo("UTC")).isoformat(),
        snapshot_hash=snapshot_hash
    )

    return ScrapeDateResult(
        date=date,
        showing_count=showing_count,
        changes_detected=changes,
        is_complete=is_complete,
        status=status
    )
```

---

## 4. Change Detection

### Compare Snapshots

```python
def _detect_changes(self, date: str, new_showings: List[Dict],
                    previous_snapshot: Dict) -> List[Change]:
    """
    Detect changes between current and previous snapshot

    Change types:
    - added: New showing appeared
    - removed: Showing disappeared
    - modified: Showing changed (time, format, availability)
    """
    changes = []

    # Get previous showings
    prev_showings = previous_snapshot['showings']

    # Create lookup dicts by showing ID
    prev_by_id = {s['id']: s for s in prev_showings}
    new_by_id = {s['id']: s for s in new_showings}

    # Detect additions
    added_ids = set(new_by_id.keys()) - set(prev_by_id.keys())
    for showing_id in added_ids:
        showing = new_by_id[showing_id]
        changes.append(Change(
            date=date,
            change_type='added',
            showing_time=showing['showing_time'],
            movie_title=showing['movie_title'],
            details=json.dumps({
                'showing_id': showing_id,
                'time': showing['showing_time'],
                'title': showing['movie_title'],
                'format': showing['format_keywords']
            })
        ))

    # Detect removals
    removed_ids = set(prev_by_id.keys()) - set(new_by_id.keys())
    for showing_id in removed_ids:
        showing = prev_by_id[showing_id]
        changes.append(Change(
            date=date,
            change_type='removed',
            showing_time=showing['showing_time'],
            movie_title=showing['movie_title'],
            details=json.dumps({
                'showing_id': showing_id,
                'time': showing['showing_time'],
                'title': showing['movie_title']
            })
        ))

    # Detect modifications (field-level changes)
    common_ids = set(prev_by_id.keys()) & set(new_by_id.keys())
    for showing_id in common_ids:
        prev = prev_by_id[showing_id]
        new = new_by_id[showing_id]

        field_changes = self._compare_showing_fields(prev, new)
        if field_changes:
            changes.append(Change(
                date=date,
                change_type='modified',
                showing_time=new['showing_time'],
                movie_title=new['movie_title'],
                details=json.dumps({
                    'showing_id': showing_id,
                    'time': new['showing_time'],
                    'title': new['movie_title'],
                    'changes': field_changes
                })
            ))

    return changes

def _compare_showing_fields(self, prev: Dict, new: Dict) -> Dict:
    """
    Compare all fields between two showings

    Returns: Dict of field changes (field_name -> {from, to})
    """
    fields_to_check = [
        'showing_time',
        'format_keywords',
        'availability_status',
        'availability_count',
        'rating'
    ]

    changes = {}
    for field in fields_to_check:
        prev_val = prev.get(field)
        new_val = new.get(field)

        if prev_val != new_val:
            changes[field] = {
                'from': prev_val,
                'to': new_val
            }

    return changes
```

---

## 5. Completion Detection

### Runtime-Based Modeling

```python
def _check_completion(self, date: str, showings: List[Dict]) -> bool:
    """
    Determine if day's schedule is complete using runtime model

    Algorithm (from completion-heuristic.md):
    1. Fetch runtime for each film
    2. Model schedule: slot_duration = 25min (ads) + runtime + 15min (changeover)
    3. Check gaps between showings
    4. If no gap >= 150 minutes, day is complete
    5. Check operating hours (10:00-23:00 typical)
    """
    if not showings:
        return True  # Empty day is "complete"

    # Get runtimes for all films
    runtimes = {}
    missing_runtimes = []

    for showing in showings:
        runtime_result = self.runtime_fetcher.get_runtime(
            movie_title=showing['movie_title'],
            detail_url_path=showing.get('detail_url_path'),
            db=self.db
        )

        if runtime_result:
            runtimes[showing['id']] = runtime_result.runtime_minutes
        else:
            missing_runtimes.append(showing['movie_title'])

    # If we're missing runtimes, can't model definitively
    if missing_runtimes:
        logger.warning(f"Missing runtimes for {date}: {missing_runtimes}")
        return False  # Assume incomplete until we have runtimes

    # Model the schedule
    OVERHEAD = 40  # 25min ads + 15min changeover
    MIN_SLOT = 150  # Minimum gap for additional showing

    # Sort showings by time
    showings_sorted = sorted(showings, key=lambda x: x['showing_time'])

    # Check gaps between consecutive showings
    for i in range(len(showings_sorted) - 1):
        current = showings_sorted[i]
        next_showing = showings_sorted[i + 1]

        runtime = runtimes[current['id']]

        # Parse times (UK local from showing_time field)
        current_time = datetime.strptime(current['showing_time'], '%H:%M').time()
        next_time = datetime.strptime(next_showing['showing_time'], '%H:%M').time()

        # Calculate end time of current showing
        current_datetime = datetime.combine(datetime.today(), current_time)
        end_datetime = current_datetime + timedelta(minutes=runtime + OVERHEAD)

        # Calculate gap to next showing
        next_datetime = datetime.combine(datetime.today(), next_time)
        gap_minutes = (next_datetime - end_datetime).total_seconds() / 60

        if gap_minutes >= MIN_SLOT:
            logger.info(f"Large gap detected on {date}: {gap_minutes}min after {current['showing_time']}")
            return False  # Room for another showing

    # Check operating hours
    first_time = datetime.strptime(showings_sorted[0]['showing_time'], '%H:%M').time()
    last_showing = showings_sorted[-1]
    last_time = datetime.strptime(last_showing['showing_time'], '%H:%M').time()

    # Cinema typically operates 10:00-23:00
    if first_time.hour >= 11:
        logger.info(f"Late start on {date}: {first_time}")
        return False  # Might add morning showing

    last_runtime = runtimes[last_showing['id']]
    last_end = datetime.combine(datetime.today(), last_time) + timedelta(minutes=last_runtime + OVERHEAD)

    if last_end.time().hour < 22:  # Ends before 22:00
        logger.info(f"Early finish on {date}: ends at {last_end.time()}")
        return False  # Might add evening showing

    # Day appears complete
    logger.info(f"Day {date} appears complete: {len(showings)} showings, no gaps >= {MIN_SLOT}min")
    return True
```

---

## 6. Batch Scraping

### Scrape All Pending Dates

```python
def scrape_all_pending(self) -> ScrapeRunSummary:
    """
    Execute daily scrape run

    Algorithm:
    1. Update horizon (discover new dates)
    2. Get prioritized list of dates to scrape
    3. Scrape each date (with error handling)
    4. Collect statistics
    5. Clean up old data
    """
    logger.info("=== Starting daily scrape run ===")
    start_time = datetime.now(ZoneInfo("UTC"))

    summary = ScrapeRunSummary(
        started_at=start_time.isoformat(),
        dates_scraped=0,
        new_dates_found=0,
        changes_detected=0,
        errors=[]
    )

    # 1. Horizon scan
    try:
        horizon_result = self.update_horizon()
        summary.new_dates_found = len(horizon_result.new_dates)
        logger.info(f"Horizon scan: {summary.new_dates_found} new dates")
    except Exception as e:
        logger.error(f"Horizon scan failed: {e}")
        summary.errors.append(f"horizon_scan: {e}")
        # Continue with scraping known dates

    # 2. Get dates to scrape
    dates_to_scrape = self.get_dates_to_scrape()
    logger.info(f"Found {len(dates_to_scrape)} dates to scrape")

    # 3. Scrape each date
    for date in dates_to_scrape:
        try:
            result = self.scrape_date(date)
            summary.dates_scraped += 1
            summary.changes_detected += len(result.changes_detected)

            # Rate limiting: 1 second between requests
            time.sleep(1)

        except Exception as e:
            logger.error(f"Failed to scrape {date}: {e}")
            summary.errors.append(f"{date}: {e}")
            continue

    # 4. Cleanup old data
    try:
        deleted_listings = self.db.delete_old_listings()
        deleted_snapshots = self.db.delete_old_snapshots()
        logger.info(f"Cleanup: {deleted_listings} old listings, {deleted_snapshots} old snapshots")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        summary.errors.append(f"cleanup: {e}")

    # 5. Summary
    end_time = datetime.now(ZoneInfo("UTC"))
    summary.completed_at = end_time.isoformat()
    summary.duration_seconds = (end_time - start_time).total_seconds()

    logger.info("=== Scrape run complete ===")
    logger.info(f"Dates scraped: {summary.dates_scraped}")
    logger.info(f"New dates: {summary.new_dates_found}")
    logger.info(f"Changes: {summary.changes_detected}")
    logger.info(f"Errors: {len(summary.errors)}")
    logger.info(f"Duration: {summary.duration_seconds:.1f}s")

    return summary
```

---

## 7. Data Classes

### Result Types

```python
from dataclasses import dataclass
from typing import List, Set, Optional

@dataclass
class HorizonScanResult:
    """Result of horizon scan operation"""
    dates_discovered: Set[str]
    new_dates: Set[str]
    removed_dates: Set[str]

@dataclass
class Change:
    """Detected schedule change"""
    date: str
    change_type: str  # 'first_seen', 'added', 'removed', 'modified'
    showing_time: Optional[str] = None
    movie_title: Optional[str] = None
    details: Optional[str] = None  # JSON string

@dataclass
class ScrapeDateResult:
    """Result of scraping a single date"""
    date: str
    showing_count: int
    changes_detected: List[Change]
    is_complete: bool
    status: str  # 'empty', 'partial', 'complete', 'error'
    error: Optional[str] = None

@dataclass
class ScrapeRunSummary:
    """Summary of full scrape run"""
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    dates_scraped: int = 0
    new_dates_found: int = 0
    changes_detected: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
```

---

## 8. Configuration

### Settings

```python
# src/dynamicalsystem/listing/config.py

class ScheduleManagerConfig:
    # Re-scrape intervals
    NEAR_TERM_DAYS = 14        # Check partial dates within 14 days daily
    WEEKLY_RECHECK_DAYS = 7    # Re-check far-future/empty dates weekly

    # Completion heuristic
    SLOT_OVERHEAD_MINUTES = 40  # Ads (25) + changeover (15)
    MIN_SLOT_GAP_MINUTES = 150  # Minimum gap for additional showing

    # Operating hours (UK local time)
    CINEMA_TYPICAL_OPEN = 10    # 10:00
    CINEMA_TYPICAL_CLOSE = 23   # 23:00
    LATE_START_HOUR = 11        # If first showing after 11:00, might add morning
    EARLY_END_HOUR = 22         # If last showing ends before 22:00, might add evening

    # Rate limiting
    INTER_SCRAPE_DELAY = 1.0    # Seconds between date scrapes

    # Retry
    MAX_RETRIES = 2
    RETRY_DELAY = 5             # Seconds
```

---

## 9. Testing Strategy

### Unit Tests

```python
def test_horizon_scan_new_dates(db, fetcher, mock_html):
    """Test horizon scan discovers new dates"""
    manager = ScheduleManager(db, fetcher, runtime_fetcher)

    # Mock HTML with performanceDays
    fetcher.fetch.return_value = mock_html_with_performance_days([
        '2025-10-26', '2025-10-27', '2025-10-28'
    ])

    result = manager.update_horizon()

    assert len(result.dates_discovered) == 3
    assert '2025-10-26' in result.dates_discovered

def test_get_dates_to_scrape_priority(db):
    """Test re-scrape prioritization"""
    manager = ScheduleManager(db, fetcher, runtime_fetcher)

    # Setup: add dates with different statuses
    db.add_to_scrape_schedule('2025-10-26', 'unknown')  # Priority 1
    db.add_to_scrape_schedule('2025-10-27', 'partial')   # Priority 2 (near-term)
    db.add_to_scrape_schedule('2025-11-15', 'partial')   # Priority 4 (far-future)

    dates = manager.get_dates_to_scrape()

    # Unknown should come first
    assert dates[0] == '2025-10-26'
    # Near-term partial should come before far-future
    assert dates.index('2025-10-27') < dates.index('2025-11-15')

def test_change_detection_added(db):
    """Test detecting added showing"""
    manager = ScheduleManager(db, fetcher, runtime_fetcher)

    # Previous snapshot: 2 showings
    prev_showings = [
        {'id': '1', 'showing_time': '10:00', 'movie_title': 'Film A'},
        {'id': '2', 'showing_time': '14:00', 'movie_title': 'Film B'}
    ]
    prev_snapshot = {'showings': prev_showings}

    # New: 3 showings (added one)
    new_showings = prev_showings + [
        {'id': '3', 'showing_time': '18:00', 'movie_title': 'Film C'}
    ]

    changes = manager._detect_changes('2025-10-26', new_showings, prev_snapshot)

    assert len(changes) == 1
    assert changes[0].change_type == 'added'
    assert changes[0].movie_title == 'Film C'

def test_change_detection_modified(db):
    """Test detecting field modification"""
    manager = ScheduleManager(db, fetcher, runtime_fetcher)

    prev_showings = [
        {'id': '1', 'showing_time': '10:00', 'movie_title': 'Film A',
         'availability_status': 'G', 'availability_count': 150}
    ]
    prev_snapshot = {'showings': prev_showings}

    # Availability changed
    new_showings = [
        {'id': '1', 'showing_time': '10:00', 'movie_title': 'Film A',
         'availability_status': 'L', 'availability_count': 38}
    ]

    changes = manager._detect_changes('2025-10-26', new_showings, prev_snapshot)

    assert len(changes) == 1
    assert changes[0].change_type == 'modified'

    details = json.loads(changes[0].details)
    assert details['changes']['availability_status']['from'] == 'G'
    assert details['changes']['availability_status']['to'] == 'L'

def test_completion_detection_complete(db, runtime_fetcher):
    """Test completion detection with no gaps"""
    manager = ScheduleManager(db, fetcher, runtime_fetcher)

    showings = [
        {'id': '1', 'showing_time': '10:45', 'movie_title': 'Film A'},
        {'id': '2', 'showing_time': '14:10', 'movie_title': 'Film B'},
        {'id': '3', 'showing_time': '17:00', 'movie_title': 'Film C'},
        {'id': '4', 'showing_time': '20:30', 'movie_title': 'Film D'}
    ]

    # Mock runtimes (from Oct 26 example)
    runtime_fetcher.get_runtime.side_effect = [
        RuntimeResult(150, 'BFI', 'confirmed', 'url'),
        RuntimeResult(119, 'BFI', 'confirmed', 'url'),
        RuntimeResult(162, 'BFI', 'confirmed', 'url'),
        RuntimeResult(100, 'BFI', 'confirmed', 'url')
    ]

    is_complete = manager._check_completion('2025-10-26', showings)

    assert is_complete is True

def test_completion_detection_has_gap(db, runtime_fetcher):
    """Test completion detection with large gap"""
    manager = ScheduleManager(db, fetcher, runtime_fetcher)

    showings = [
        {'id': '1', 'showing_time': '10:00', 'movie_title': 'Film A'},
        {'id': '2', 'showing_time': '17:00', 'movie_title': 'Film B'}  # 7 hour gap
    ]

    runtime_fetcher.get_runtime.side_effect = [
        RuntimeResult(90, 'BFI', 'confirmed', 'url'),
        RuntimeResult(90, 'BFI', 'confirmed', 'url')
    ]

    is_complete = manager._check_completion('2025-10-26', showings)

    assert is_complete is False  # Gap of 5+ hours allows more showings
```

### Integration Tests

```python
def test_scrape_date_full_workflow(db, fetcher, runtime_fetcher):
    """Test complete scrape_date workflow"""
    manager = ScheduleManager(db, fetcher, runtime_fetcher)

    # Mock BFI response
    fetcher.fetch.return_value = load_fixture('bfi_cloudscraper_2025-10-26.html')

    # Mock runtimes
    runtime_fetcher.get_runtime.return_value = RuntimeResult(150, 'BFI', 'confirmed', 'url')

    result = manager.scrape_date('2025-10-26')

    assert result.showing_count == 4
    assert result.status in ['partial', 'complete']

    # Verify database updated
    showings = db.get_showings_for_date('2025-10-26')
    assert len(showings) == 4

    # Verify snapshot recorded
    snapshot = db.get_latest_snapshot('2025-10-26')
    assert snapshot is not None
    assert snapshot['showing_count'] == 4

def test_scrape_all_pending(db, fetcher, runtime_fetcher):
    """Test full scrape run"""
    manager = ScheduleManager(db, fetcher, runtime_fetcher)

    # Setup: add dates to scrape
    db.add_to_scrape_schedule('2025-10-26', 'unknown')
    db.add_to_scrape_schedule('2025-10-27', 'partial')

    # Mock responses
    fetcher.fetch.side_effect = [
        load_fixture('bfi_cloudscraper_2025-10-26.html'),  # Horizon scan
        load_fixture('bfi_cloudscraper_2025-10-26.html'),  # Date 1
        load_fixture('bfi_no_results_2025-10-27.html')     # Date 2
    ]

    runtime_fetcher.get_runtime.return_value = RuntimeResult(120, 'BFI', 'confirmed', 'url')

    summary = manager.scrape_all_pending()

    assert summary.dates_scraped >= 2
    assert len(summary.errors) == 0
```

---

## 10. Error Handling

### Retry Logic

```python
def _fetch_with_retry(self, date: str, max_retries: int = 2) -> Optional[str]:
    """Fetch with exponential backoff retry"""
    for attempt in range(max_retries + 1):
        try:
            html = self.fetcher.fetch(date)
            if html:
                return html
        except Exception as e:
            if attempt < max_retries:
                delay = 5 * (2 ** attempt)  # 5s, 10s, 20s
                logger.warning(f"Fetch failed (attempt {attempt + 1}/{max_retries + 1}), retry in {delay}s: {e}")
                time.sleep(delay)
            else:
                logger.error(f"Fetch failed after {max_retries + 1} attempts: {e}")

    return None
```

### Graceful Degradation

```python
def scrape_date(self, date: str) -> ScrapeDateResult:
    """Never raise exceptions, always return result"""
    try:
        # ... scrape logic ...
    except requests.RequestException as e:
        logger.error(f"Network error scraping {date}: {e}")
        return ScrapeDateResult(
            date=date,
            showing_count=0,
            changes_detected=[],
            is_complete=False,
            status='error',
            error=f"network: {e}"
        )
    except Exception as e:
        logger.error(f"Unexpected error scraping {date}: {e}", exc_info=True)
        return ScrapeDateResult(
            date=date,
            showing_count=0,
            changes_detected=[],
            is_complete=False,
            status='error',
            error=f"unexpected: {e}"
        )
```

---

## 11. Performance Optimizations

### Snapshot Hash Quick Check

```python
def scrape_date(self, date: str) -> ScrapeDateResult:
    # ... fetch and parse ...

    # Quick check: has schedule changed?
    snapshot_hash = compute_snapshot_hash(showings)
    previous_hash = self.db.get_latest_snapshot_hash(date)

    if previous_hash and snapshot_hash == previous_hash:
        # No changes, update last_checked only
        logger.info(f"No changes detected for {date} (hash match)")
        self.db.update_last_checked(date)
        return ScrapeDateResult(
            date=date,
            showing_count=len(showings),
            changes_detected=[],
            is_complete=self.db.get_is_complete(date),
            status=self.db.get_status(date)
        )

    # Hash changed, proceed with full change detection
    # ...
```

### Batch Runtime Fetching

```python
def _fetch_runtimes_batch(self, showings: List[Dict]) -> Dict[str, int]:
    """Fetch runtimes for multiple showings efficiently"""
    # Group by movie title
    unique_titles = {s['movie_title']: s.get('detail_url_path') for s in showings}

    # Check cache first (single query)
    cached_runtimes = self.db.get_runtimes_batch(list(unique_titles.keys()))

    # Fetch missing runtimes
    runtimes = {}
    for title, detail_url in unique_titles.items():
        if title in cached_runtimes:
            runtimes[title] = cached_runtimes[title]
        else:
            result = self.runtime_fetcher.get_runtime(title, detail_url, self.db)
            if result:
                runtimes[title] = result.runtime_minutes

    return runtimes
```

---

## Next Steps

1. [ ] **Review**: Simon reviews design
2. [ ] **Implement**: Core ScheduleManager class
3. [ ] **Implement**: Horizon scanning
4. [ ] **Implement**: Re-scrape prioritization
5. [ ] **Implement**: Change detection
6. [ ] **Implement**: Completion detection
7. [ ] **Test**: Unit tests for each component
8. [ ] **Test**: Integration test for full workflow
9. [ ] **Document**: Update decision.md

---

## Success Criteria

Schedule manager is successful if:

- [ ] Horizon scan discovers all dates in single request
- [ ] Re-scrape priority correctly identifies dates needing attention
- [ ] Change detection catches all types (added/removed/modified)
- [ ] Completion detection accuracy >90% (validated over 2 weeks)
- [ ] Batch scrape completes in <5 minutes for typical load (~16 dates)
- [ ] Graceful error handling (never crashes)
- [ ] Database state always consistent

---

## Related Documents

- [Edge Cases and Strategy](../observe/edge-cases-and-strategy.md) - dates_to_query concept
- [Completion Heuristic](../observe/completion-heuristic.md) - Runtime-based modeling
- [Schedule Change Tracking](../observe/schedule-change-tracking.md) - Change detection design
- [SQLite Schema](./sqlite-schema-design.md) - scrape_schedule, snapshots, changes tables
- [Runtime Fetcher](./runtime-fetcher-design.md) - Runtime fetching integration
- [Parser Module](./parser-module-design.md) - parse_search_results, extract_performance_days
