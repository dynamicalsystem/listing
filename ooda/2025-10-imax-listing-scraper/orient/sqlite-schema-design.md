# SQLite Schema Design

**Date**: 2025-10-26
**Status**: [x] Approved
**Database**: `listing.db`
**Purpose**: Store BFI IMAX listings, schedule state, and learning data

---

## Purpose

Define SQLite schema for:
1. Current and future movie showings
2. Schedule scraping state (dates_to_query)
3. Change tracking for pattern learning
4. Runtime cache (BFI + external sources)

---

## Design Principles

1. **Simple**: Normalized but not over-engineered
2. **Query-optimized**: Indices for common access patterns
3. **Learning-focused**: Support analytics queries for pattern detection
4. **Idempotent**: UNIQUE constraints prevent duplicates
5. **Timezone-explicit**: All timestamps stored in UTC with explicit +00:00 (per CLAUDE.md)

## Timezone Strategy

**Storage**: All timestamps stored in UTC with ISO 8601 format including timezone offset

**Format**: `2025-10-26T09:45:00+00:00`

**Conversion**:
- **Inbound** (scraping): BFI times are UK local (Europe/London) → convert to UTC for storage
- **Outbound** (display): UTC from database → convert to UK local for web display

**Denormalization for Queries**:
- `showing_date` and `showing_time` stored as UK local for convenient queries ("all showings on 2025-10-26")
- `showing_datetime_utc` is canonical source of truth
- Compute local date/time from UTC on insert, store both

**Rationale**:
- Handles DST transitions correctly (UK changes Mar/Oct)
- Standard practice for data at rest
- Enables international users (future: convert UTC → their timezone)
- Audit trail is unambiguous

---

## Schema Overview

Five core tables:

```
listings           -- Current and future showings (public data)
scrape_schedule    -- Which dates to scrape and when (operational)
schedule_snapshots -- Historical schedule state (learning)
schedule_changes   -- Detected changes over time (learning)
movie_runtimes     -- Cached runtimes from BFI/external (operational)
```

---

## Table 1: listings

**Purpose**: Store movie showings for web presentation and RSS

**Lifecycle**: Records deleted when showing_date < yesterday

```sql
CREATE TABLE listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- BFI identifiers
    bfi_showing_id TEXT NOT NULL,        -- From searchResults[0]
    bfi_performance_id TEXT,             -- From searchResults[42]

    -- Movie details
    movie_title TEXT NOT NULL,           -- "Frankenstein"
    movie_slug TEXT,                     -- "frank_26oct25" (BFI internal)
    rating TEXT,                         -- "15", "12A", "PG"

    -- Showing details (all times in UTC)
    showing_date DATE NOT NULL,          -- "2025-10-26" (date in UK local for queries)
    showing_time TIME NOT NULL,          -- "10:45" (time in UK local for queries)
    showing_datetime_utc TEXT NOT NULL,  -- "2025-10-26T09:45:00+00:00" (canonical UTC)
    showing_datetime_display TEXT,       -- "Sunday 26 October 2025 10:45" (UK local, for display)

    -- Format
    format_keywords TEXT,                -- "IMAX with Laser,3D"
    is_3d BOOLEAN DEFAULT 0,
    is_70mm BOOLEAN DEFAULT 0,
    is_laser BOOLEAN DEFAULT 0,
    has_subtitles BOOLEAN DEFAULT 0,

    -- Links
    detail_url_path TEXT,                -- Relative path to movie detail
    detail_url_full TEXT,                -- Full URL (computed)

    -- Availability
    availability_status TEXT,            -- 'L', 'G', 'S' (Limited/Good/Sold)
    availability_count INTEGER,          -- Seats remaining

    -- Metadata (UTC)
    scraped_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', 'utc')),

    -- Prevent duplicates
    UNIQUE(bfi_showing_id),
    UNIQUE(showing_date, showing_time, movie_title)
);

CREATE INDEX idx_listings_date ON listings(showing_date);
CREATE INDEX idx_listings_scraped_at ON listings(scraped_at);
CREATE INDEX idx_listings_movie ON listings(movie_title);
```

**Rationale**:
- `UNIQUE(showing_date, showing_time, movie_title)` prevents duplicate showings
- Boolean flags (`is_3d`, etc.) simplify queries vs parsing keywords each time
- `scraped_at` enables "new in last 24h" RSS feed
- Separate date/time fields support queries like "all showings on 2025-10-26"

**Sample Record**:
```sql
INSERT INTO listings (
    bfi_showing_id, movie_title,
    showing_date, showing_time, showing_datetime_utc, showing_datetime_display,
    format_keywords, is_laser,
    availability_status, availability_count,
    detail_url_path
) VALUES (
    '62F928E8-F582-4027-B3D9-8765A1A5605C',
    'Frankenstein',
    '2025-10-26',          -- UK local date for queries
    '10:45',               -- UK local time for queries
    '2025-10-26T09:45:00+00:00',  -- UTC (10:45 UK = 09:45 UTC in winter)
    'Sunday 26 October 2025 10:45',
    'IMAX with Laser',
    1,
    'L',
    38,
    'default.asp?doWork::WScontent::loadArticle=Load&...'
);
```

---

## Table 2: scrape_schedule

**Purpose**: Track which dates need scraping and their status

**Lifecycle**: Permanent (tracks all dates discovered)

```sql
CREATE TABLE scrape_schedule (
    date DATE PRIMARY KEY,

    -- Status
    status TEXT NOT NULL,                -- 'empty', 'partial', 'complete', 'unknown'
    showing_count INTEGER DEFAULT 0,
    is_complete BOOLEAN DEFAULT 0,       -- From runtime-based heuristic

    -- Timestamps (all UTC with explicit +00:00)
    first_seen TEXT,                     -- When date first appeared in horizon
    last_scraped TEXT,
    last_checked TEXT,                   -- Last time we looked (even if no change)

    -- State
    snapshot_hash TEXT,                  -- Quick change detection
    notes TEXT                           -- e.g., "added 3 showings"
);

CREATE INDEX idx_schedule_status ON scrape_schedule(status);
CREATE INDEX idx_schedule_last_scraped ON scrape_schedule(last_scraped);
CREATE INDEX idx_schedule_date_range ON scrape_schedule(date, status);
```

**Status Values**:
- `empty`: Verified no showings on this date
- `partial`: Has showings but may get more
- `complete`: Schedule is full (no gaps for more showings)
- `unknown`: Not yet checked

**Rationale**:
- Drives re-scrape logic: "which dates need checking today?"
- `snapshot_hash` enables quick "has schedule changed?" check
- Separate `last_scraped` vs `last_checked` tracks actual fetch vs decision not to fetch

**Sample Record**:
```sql
INSERT INTO scrape_schedule (
    date, status, showing_count, is_complete,
    first_seen, last_scraped, snapshot_hash
) VALUES (
    '2025-10-26',
    'complete',
    4,
    1,
    '2025-10-25T02:00:00+00:00',  -- UTC
    '2025-10-25T02:15:00+00:00',  -- UTC
    'a1b2c3d4e5f67890'
);
```

---

## Table 3: schedule_snapshots

**Purpose**: Historical record of schedule state for each date

**Lifecycle**: Permanent (for learning/analysis)

```sql
CREATE TABLE schedule_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- What
    date DATE NOT NULL,
    snapshot_hash TEXT NOT NULL,         -- Hash of showing details
    showing_count INTEGER NOT NULL,
    is_complete BOOLEAN,

    -- When (UTC with explicit +00:00)
    scraped_at TEXT NOT NULL,

    -- Change detection
    changed_from_previous BOOLEAN DEFAULT 0,

    UNIQUE(date, scraped_at)
);

CREATE INDEX idx_snapshots_date ON schedule_snapshots(date);
CREATE INDEX idx_snapshots_scraped_at ON schedule_snapshots(scraped_at);
CREATE INDEX idx_snapshots_hash ON schedule_snapshots(date, snapshot_hash);
```

**Rationale**:
- Every scrape creates a snapshot (even if no change)
- Enables "when did this date's schedule stabilize?"
- `snapshot_hash` enables quick comparison: "did anything change?"

**Snapshot Hash Algorithm**:
```python
# Hash includes: showing times + movie titles + formats
# Excludes: availability counts (change frequently)
def compute_snapshot_hash(showings):
    normalized = sorted([
        {'time': s['time'], 'title': s['title'], 'format': s['format']}
        for s in showings
    ], key=lambda x: x['time'])
    return hashlib.sha256(json.dumps(normalized).encode()).hexdigest()[:16]
```

---

## Table 4: schedule_changes

**Purpose**: Record specific changes detected between snapshots

**Lifecycle**: Permanent (for pattern analysis)

```sql
CREATE TABLE schedule_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- What changed
    date DATE NOT NULL,
    change_type TEXT NOT NULL,           -- 'first_seen', 'added', 'removed', 'modified'
    showing_time TIME,
    movie_title TEXT,

    -- Context
    previous_count INTEGER,
    new_count INTEGER,
    details TEXT,                        -- JSON with change details

    -- When (UTC with explicit +00:00)
    detected_at TEXT NOT NULL,

    -- Link to snapshots
    previous_snapshot_id INTEGER,
    new_snapshot_id INTEGER,

    FOREIGN KEY (previous_snapshot_id) REFERENCES schedule_snapshots(snapshot_id),
    FOREIGN KEY (new_snapshot_id) REFERENCES schedule_snapshots(snapshot_id)
);

CREATE INDEX idx_changes_date ON schedule_changes(date);
CREATE INDEX idx_changes_type ON schedule_changes(change_type);
CREATE INDEX idx_changes_detected_at ON schedule_changes(detected_at);
CREATE INDEX idx_changes_date_type ON schedule_changes(date, change_type);
```

**Change Types**:
- `first_seen`: Date appeared in horizon scan for first time
- `added`: Showing added to existing date
- `removed`: Showing removed from date
- `modified`: Showing changed (time/format/etc)

**Sample Change Record**:
```sql
INSERT INTO schedule_changes (
    date, change_type, showing_time, movie_title,
    previous_count, new_count, detected_at, details
) VALUES (
    '2025-11-12',
    'added',
    '14:30',
    'Movie X',
    1,
    2,
    '2025-10-27T02:00:00+00:00',  -- UTC
    '{"previous_showings": ["20:45 j-Hope"], "added": "14:30 Movie X"}'
);
```

---

## Table 5: movie_runtimes

**Purpose**: Cache film runtimes to avoid repeated external fetches

**Lifecycle**: Permanent (runtimes don't change)

**Updated**: 2025-10-26 (simplified confidence model)

```sql
CREATE TABLE movie_runtimes (
    movie_title TEXT PRIMARY KEY,

    -- Runtime (NULL = unknown, INTEGER = known)
    runtime_minutes INTEGER,

    -- Source (audit only)
    source TEXT,                         -- 'BFI' or 'Wikipedia'

    -- Metadata (UTC with explicit +00:00)
    fetched_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', 'utc')),

    -- Validation
    CHECK (runtime_minutes IS NULL OR (runtime_minutes > 0 AND runtime_minutes < 500))
);

CREATE INDEX idx_runtimes_source ON movie_runtimes(source);
```

**Rationale**:
- Prevents re-fetching runtime for same film
- `source` tracks where data came from (audit trail only)
- NULL runtime_minutes = unknown (retry next time)
- INTEGER runtime_minutes = known (use for completion detection)

**Design Simplification** (2025-10-26):
- Removed `confidence` field (NULL vs INTEGER is sufficient)
- Removed `source_url` field (adds complexity, not needed)
- Changed `runtime_minutes` to nullable (NULL = unknown)
- Removed `NOT NULL` constraint (allow NULL for unknown)
- Only cache successful finds (don't cache failures)

**Sample Record**:
```sql
INSERT INTO movie_runtimes (
    movie_title, runtime_minutes, source, fetched_at
) VALUES (
    'Frankenstein',
    150,
    'Wikipedia',
    '2025-10-25T12:30:00+00:00'  -- UTC
);
```

---

## Supporting Views

### View: upcoming_showings

**Purpose**: Simplify queries for "showings happening today or later"

```sql
CREATE VIEW upcoming_showings AS
SELECT
    l.*,
    r.runtime_minutes,
    r.source as runtime_source
FROM listings l
LEFT JOIN movie_runtimes r ON l.movie_title = r.movie_title
WHERE l.showing_date >= date('now')
ORDER BY l.showing_date, l.showing_time;
```

### View: schedule_stability

**Purpose**: Analyze when dates become stable

```sql
CREATE VIEW schedule_stability AS
SELECT
    date,
    MIN(scraped_at) as first_seen,
    MAX(scraped_at) as last_changed,
    COUNT(*) as snapshot_count,
    MAX(showing_count) as final_showing_count
FROM schedule_snapshots
GROUP BY date;
```

---

## Common Queries

### Daily Maintenance: Delete Old Data

```sql
-- Delete listings for past showings
DELETE FROM listings
WHERE showing_date < date('now', '-1 day');

-- Prune old snapshots (keep 30 days past showing)
DELETE FROM schedule_snapshots
WHERE date < date('now', '-30 days');
```

### Daily Maintenance: Dates to Scrape Today

```sql
SELECT date
FROM scrape_schedule
WHERE
    -- Partial or unknown dates in next 14 days
    (status IN ('partial', 'unknown') AND date BETWEEN date('now') AND date('now', '+14 days'))
    OR
    -- Weekly check on far-future dates
    (status = 'partial' AND date > date('now', '+14 days') AND julianday('now') - julianday(last_checked) >= 7)
    OR
    -- Re-check empty dates weekly
    (status = 'empty' AND date >= date('now') AND julianday('now') - julianday(last_checked) >= 7)
ORDER BY date;
```

### RSS Feed: Changes in Last 24h

```sql
SELECT * FROM listings
WHERE scraped_at >= datetime('now', '-24 hours')
ORDER BY scraped_at DESC;
```

### Web Display: All Upcoming Showings

```sql
SELECT
    showing_date,
    showing_time,
    movie_title,
    format_keywords,
    availability_status,
    detail_url_full
FROM upcoming_showings
ORDER BY showing_date, showing_time;
```

### Learning: Change Frequency by Day of Week

```sql
SELECT
    CASE CAST(strftime('%w', detected_at) AS INTEGER)
        WHEN 0 THEN 'Sun'
        WHEN 1 THEN 'Mon'
        WHEN 2 THEN 'Tue'
        WHEN 3 THEN 'Wed'
        WHEN 4 THEN 'Thu'
        WHEN 5 THEN 'Fri'
        WHEN 6 THEN 'Sat'
    END as day_of_week,
    COUNT(*) as change_count,
    COUNT(DISTINCT date) as dates_affected
FROM schedule_changes
WHERE change_type IN ('added', 'removed', 'modified')
GROUP BY strftime('%w', detected_at)
ORDER BY CAST(strftime('%w', detected_at) AS INTEGER);
```

### Learning: Average Time to Stability

```sql
SELECT
    AVG(julianday(last_changed) - julianday(first_seen)) as avg_days_to_stable,
    MIN(julianday(last_changed) - julianday(first_seen)) as min_days,
    MAX(julianday(last_changed) - julianday(first_seen)) as max_days
FROM schedule_stability
WHERE snapshot_count > 1;  -- Only dates that changed
```

---

## Migration Strategy

### Initial Schema Creation

```python
# src/dynamicalsystem/listing/storage/schema.py

SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- Version tracking
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_version (version) VALUES (1);

-- [Tables as defined above]
"""

def init_database(db_path: str):
    """Initialize database with schema"""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
```

### Future Migrations

```python
MIGRATIONS = {
    2: """
        -- Example: Add index for performance
        CREATE INDEX idx_listings_date_time ON listings(showing_date, showing_time);
    """,
    # Future versions...
}

def migrate_database(db_path: str):
    """Apply pending migrations"""
    conn = sqlite3.connect(db_path)
    current_version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]

    for version in sorted(MIGRATIONS.keys()):
        if version > current_version:
            conn.executescript(MIGRATIONS[version])
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            conn.commit()

    conn.close()
```

---

## Performance Considerations

### Database Size Estimates

**Assumptions**:
- 23 dates with showings at any time
- Average 4 showings per date
- 92 current listings maximum
- Snapshots: 1 per date per day = ~23 snapshots/day
- Runtimes: ~50 unique films over time

**Size Calculations**:
```
listings:           92 records × 500 bytes ≈ 46 KB
scrape_schedule:    267 records × 200 bytes ≈ 53 KB
schedule_snapshots: 23/day × 365 days × 150 bytes ≈ 1.2 MB/year
schedule_changes:   ~10/day × 365 days × 200 bytes ≈ 730 KB/year
movie_runtimes:     50 records × 200 bytes ≈ 10 KB

Total (year 1): ~2 MB
```

**Conclusion**: Database size is negligible, no cleanup needed beyond old listings.

### Index Strategy

Indices created for:
1. **Date range queries**: Web display, RSS feeds
2. **Status filtering**: Re-scrape decisions
3. **Change analysis**: Learning queries by date/type
4. **Foreign keys**: Maintain referential integrity

**Trade-off**: Indices add ~10% overhead on writes, but all writes are during daily scrape (low frequency). Read performance (web serving) is priority.

---

## Database Access Layer

### Python Interface (Scraper)

```python
# src/dynamicalsystem/listing/storage/db.py

class Database:
    def __init__(self, db_path: str = "listing.db"):
        self.db_path = db_path

    def insert_showings(self, showings: List[Dict]) -> int:
        """Insert showings, ignore duplicates"""

    def get_dates_to_scrape(self) -> List[str]:
        """Get dates that need scraping today"""

    def update_schedule_status(self, date: str, status: str, showing_count: int, is_complete: bool):
        """Update scrape_schedule for a date"""

    def record_snapshot(self, date: str, showings: List[Dict]) -> int:
        """Record schedule snapshot, return snapshot_id"""

    def detect_and_record_changes(self, date: str, new_snapshot_id: int, prev_snapshot_id: int):
        """Compare snapshots and record changes"""

    def get_runtime(self, movie_title: str) -> Optional[int]:
        """Get cached runtime"""

    def cache_runtime(self, movie_title: str, runtime: int, source: str, url: str = None):
        """Cache runtime from external source"""

    def delete_old_listings(self, before_date: str):
        """Delete listings older than date"""
```

### Go Interface (Web Server)

```go
// src/webserver/db/queries.go

type Showing struct {
    ShowingDate    string
    ShowingTime    string
    MovieTitle     string
    FormatKeywords string
    Rating         string
    DetailURL      string
    IsThreeD       bool
    Is70mm         bool
    AvailStatus    string
}

func GetUpcomingShowings(db *sql.DB) ([]Showing, error) {
    // Query upcoming_showings view
}

func GetRecentChanges(db *sql.DB, hours int) ([]Showing, error) {
    // Query for RSS feed
}

func GetHealthInfo(db *sql.DB) (HealthInfo, error) {
    // Count listings, last scrape time, date range
}
```

---

## Testing Strategy

### Unit Tests (Python)

```python
def test_insert_duplicate_showing():
    """UNIQUE constraint prevents duplicates"""
    db.insert_showings([showing1])
    db.insert_showings([showing1])  # Should not error

    count = db.execute("SELECT COUNT(*) FROM listings WHERE bfi_showing_id = ?",
                       (showing1['id'],)).fetchone()[0]
    assert count == 1

def test_date_range_query():
    """Verify index usage for date range"""
    showings = db.get_showings_between('2025-10-26', '2025-10-31')
    assert len(showings) == expected_count

def test_snapshot_change_detection():
    """Compare snapshots and detect changes"""
    snap1 = db.record_snapshot('2025-10-26', showings_v1)
    snap2 = db.record_snapshot('2025-10-26', showings_v2)
    changes = db.detect_and_record_changes('2025-10-26', snap2, snap1)
    assert len(changes) == 1
    assert changes[0]['change_type'] == 'added'
```

### Integration Tests

```python
def test_daily_maintenance_workflow():
    """Full workflow: scrape, detect changes, cleanup"""
    # Day 1: Initial scrape
    db.insert_showings(initial_showings)
    snap1 = db.record_snapshot('2025-10-26', initial_showings)

    # Day 2: Showings added
    db.insert_showings(updated_showings)
    snap2 = db.record_snapshot('2025-10-26', updated_showings)
    db.detect_and_record_changes('2025-10-26', snap2, snap1)

    # Day 3: Delete old
    db.delete_old_listings('2025-10-27')

    # Verify state
    assert db.get_listing_count() == expected
    assert db.get_change_count('2025-10-26') == 1
```

---

## Resolved Questions

### 1. Snapshot Retention

**Decision**: Prune old snapshots

**Retention Policy**:
- Keep snapshots while showing_date >= yesterday
- Once showing_date passes, keep snapshots for 30 days
- After 30 days past showing, delete snapshots
- Keep schedule_changes forever (they're smaller, extracted learnings)

**Rationale**: Snapshots are for detecting changes to upcoming schedules. Once showing has passed, no more changes can occur. schedule_changes table preserves the learnings.

**Pruning Query**:
```sql
DELETE FROM schedule_snapshots
WHERE date < date('now', '-30 days');
```

### 2. Change Granularity

**Decision**: Field-level changes, record everything

**Rationale**:
- Availability counts change frequently (interesting data)
- Times might change (rescheduling)
- Formats might change (3D added/removed)
- Don't optimize prematurely - capture everything
- Data volume is small

**Change Types**:
- `first_seen`: Date appeared in horizon scan
- `added`: New showing added
- `removed`: Showing removed
- `modified`: Existing showing changed (any field)

**Modified Change Details**:
```json
{
  "showing_id": "62F928E8-...",
  "time": "10:45",
  "title": "Frankenstein",
  "changes": {
    "availability_status": {"from": "G", "to": "L"},
    "availability_count": {"from": 150, "to": 38},
    "format_keywords": {"from": "IMAX with Laser", "to": "IMAX with Laser,3D"}
  }
}
```

**Implementation**: Compare all fields between snapshots, record any difference.

### 3. Timezone Handling

**Decision**: Store in UTC with explicit timezone

**Implementation**:
- BFI times are UK local time (Europe/London)
- **On scrape**: Parse as UK time, convert to UTC, store with 'UTC' timezone marker
- **On display**: Read UTC, convert to UK time for presentation
- **Timestamp fields**: Store as ISO 8601 with timezone: `2025-10-26T09:45:00+00:00`

**Schema Changes**:
```sql
-- All timestamp fields store UTC
showing_datetime TEXT,  -- '2025-10-26T09:45:00+00:00' (UTC)
scraped_at TEXT DEFAULT (datetime('now', 'utc') || '+00:00'),
```

**Python Conversion**:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

# Parse BFI time as UK local
bfi_time = "Sunday 26 October 2025 10:45"
uk_tz = ZoneInfo("Europe/London")
dt_uk = datetime.strptime(bfi_time, "%A %d %B %Y %H:%M").replace(tzinfo=uk_tz)

# Convert to UTC for storage
dt_utc = dt_uk.astimezone(ZoneInfo("UTC"))
stored = dt_utc.isoformat()  # '2025-10-26T09:45:00+00:00'
```

**Rationale**:
- Handles DST transitions correctly (Oct/Mar UK time changes)
- Standard practice for data at rest (per CLAUDE.md)
- Go server converts UTC → UK time for display
- RSS feeds use UTC (standard for feeds)

---

## Next Steps

1. [x] **Decisions**: Resolved open questions
   - Snapshot retention: Prune after 30 days past showing
   - Change granularity: Field-level, record everything
   - Timezone: UTC with explicit +00:00, denormalize UK local for queries
2. [ ] **Review**: Simon reviews complete schema design
3. [ ] **Implement**: Create `src/dynamicalsystem/listing/storage/schema.py`
4. [ ] **Implement**: Create `src/dynamicalsystem/listing/storage/db.py` (Python interface)
5. [ ] **Test**: Unit tests for database operations
6. [ ] **Integrate**: Connect parser → database
7. [ ] **Document**: Update decision.md with finalized schema

---

## Success Criteria

Schema is successful if:

- [ ] All outcomes.md requirements can be implemented
- [ ] Daily maintenance queries run in <100ms
- [ ] Change tracking queries support pattern learning
- [ ] Web server queries run in <50ms
- [ ] Database size stays under 10 MB/year
- [ ] No data corruption from concurrent access

---

## Related Documents

- [Parser Module Design](./parser-module-design.md) - Field structure
- [Edge Cases and Strategy](../observe/edge-cases-and-strategy.md) - scrape_schedule requirements
- [Schedule Change Tracking](../observe/schedule-change-tracking.md) - Snapshot/change tables
- [Completion Heuristic](../observe/completion-heuristic.md) - Runtime requirements
- [Decision](../decision.md) - Architecture decisions
