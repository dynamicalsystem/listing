# Schedule Change Tracking

**Date**: 2025-10-25
**Status**: [x] Design complete
**Purpose**: Learn BFI's scheduling patterns through observation

## Problem Statement

**Unknown**: How often do schedules change after initial posting?

**Questions**:
- Do they add showings to existing days?
- Do they remove showings?
- At what point does a day become "stable"?
- How far in advance are schedules finalized?

**Solution**: Track every schedule change and analyze patterns over time.

---

## Database Schema

### Schedule Snapshots

```sql
CREATE TABLE schedule_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    scraped_at TIMESTAMP NOT NULL,
    showing_count INTEGER NOT NULL,
    is_complete BOOLEAN,  -- From runtime-based heuristic
    snapshot_hash TEXT,   -- Hash of showing details for change detection
    UNIQUE(date, scraped_at)
);

CREATE INDEX idx_snapshots_date ON schedule_snapshots(date);
CREATE INDEX idx_snapshots_scraped_at ON schedule_snapshots(scraped_at);
```

### Schedule Changes

```sql
CREATE TABLE schedule_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    change_type TEXT NOT NULL,  -- 'added', 'removed', 'modified', 'first_seen'
    showing_time TIME,
    movie_title TEXT,
    details TEXT,  -- JSON with change details
    previous_count INTEGER,
    new_count INTEGER
);

CREATE INDEX idx_changes_date ON schedule_changes(date);
CREATE INDEX idx_changes_type ON schedule_changes(change_type);
```

### Schedule Stability

```sql
CREATE TABLE schedule_stability (
    date DATE PRIMARY KEY,
    first_seen TIMESTAMP NOT NULL,
    last_changed TIMESTAMP NOT NULL,
    change_count INTEGER DEFAULT 0,
    days_until_stable INTEGER,  -- NULL if still changing
    final_showing_count INTEGER,
    became_stable_at TIMESTAMP
);
```

---

## Change Detection Algorithm

```python
def detect_changes(date: str, new_showings: List[Dict], previous_snapshot: Dict):
    """
    Compare new scrape to previous snapshot and record changes

    Args:
        date: Date being scraped
        new_showings: Current showings from scrape
        previous_snapshot: Last recorded snapshot for this date

    Returns:
        List of changes detected
    """
    changes = []

    if not previous_snapshot:
        # First time seeing this date
        changes.append({
            'type': 'first_seen',
            'count': len(new_showings),
            'details': f'Date first appeared with {len(new_showings)} showings'
        })
        return changes

    # Convert to sets for comparison
    prev_showings = set((s['time'], s['title']) for s in previous_snapshot['showings'])
    curr_showings = set((s['time'], s['title']) for s in new_showings)

    # Detect additions
    added = curr_showings - prev_showings
    for time, title in added:
        changes.append({
            'type': 'added',
            'time': time,
            'title': title,
            'details': f'Added showing: {title} at {time}'
        })

    # Detect removals
    removed = prev_showings - curr_showings
    for time, title in removed:
        changes.append({
            'type': 'removed',
            'time': time,
            'title': title,
            'details': f'Removed showing: {title} at {time}'
        })

    # Detect count changes without specific showing changes
    # (e.g., same movies but different times)
    if not added and not removed and len(new_showings) != len(prev_showings):
        changes.append({
            'type': 'modified',
            'details': f'Showing count changed from {len(prev_showings)} to {len(new_showings)}'
        })

    return changes
```

---

## Snapshot Hashing

**Purpose**: Quick change detection without comparing full showing lists

```python
import hashlib
import json

def compute_snapshot_hash(showings: List[Dict]) -> str:
    """
    Create hash of showings for change detection

    Hash includes: time, title, format
    Excludes: availability, prices (these change frequently)
    """
    # Normalize showings
    normalized = sorted([
        {
            'time': s['time'],
            'title': s['title'],
            'format': s.get('format', '')
        }
        for s in showings
    ], key=lambda x: x['time'])

    # Create hash
    snapshot_str = json.dumps(normalized, sort_keys=True)
    return hashlib.sha256(snapshot_str.encode()).hexdigest()[:16]
```

**Usage**:
```python
new_hash = compute_snapshot_hash(showings)
if new_hash != previous_hash:
    # Schedule changed, detect specific changes
    changes = detect_changes(date, showings, previous_snapshot)
else:
    # No changes, skip detailed comparison
    pass
```

---

## Learning Patterns Over Time

### Query: How often do schedules change?

```sql
-- Days with changes after initial posting
SELECT
    date,
    change_count,
    JULIANDAY(last_changed) - JULIANDAY(first_seen) as days_until_stable
FROM schedule_stability
WHERE change_count > 0
ORDER BY first_seen DESC;
```

### Query: When do changes typically happen?

```sql
-- Change frequency by day of week
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
    COUNT(DISTINCT date) as days_affected
FROM schedule_changes
WHERE change_type IN ('added', 'removed', 'modified')
GROUP BY strftime('%w', detected_at)
ORDER BY CAST(strftime('%w', detected_at) AS INTEGER);
```

### Query: How far in advance are schedules posted?

```sql
-- Days between first appearance and showing date
SELECT
    AVG(JULIANDAY(date) - JULIANDAY(first_seen)) as avg_lead_time,
    MIN(JULIANDAY(date) - JULIANDAY(first_seen)) as min_lead_time,
    MAX(JULIANDAY(date) - JULIANDAY(first_seen)) as max_lead_time
FROM schedule_stability
WHERE first_seen IS NOT NULL;
```

---

## Stability Detection

### Definition: When is a day "stable"?

**Heuristic**: No changes for 7 consecutive days

**Conditions**:
1. Date is ≤7 days away AND no changes in last 3 days → **likely stable**
2. Date has passed → **definitely stable**
3. Schedule is "complete" (from runtime heuristic) AND no changes for 3 days → **likely stable**

**Implementation**:
```python
def check_stability(date: str, last_changed: datetime, is_complete: bool) -> bool:
    """
    Determine if a date's schedule is stable

    Returns: True if schedule is unlikely to change further
    """
    days_since_change = (datetime.now() - last_changed).days
    days_until_showing = (datetime.strptime(date, '%Y-%m-%d').date() - datetime.now().date()).days

    # Date in the past
    if days_until_showing < 0:
        return True

    # Close to showing date and hasn't changed recently
    if days_until_showing <= 7 and days_since_change >= 3:
        return True

    # Schedule is complete and stable for 3 days
    if is_complete and days_since_change >= 3:
        return True

    # Far future, needs more observation
    return False
```

---

## Re-scrape Strategy with Change Tracking

### Priority Levels

**Priority 1: Unstable Dates** (scrape daily)
```python
last_changed < 3 days ago AND date <= today + 14 days
```
- Schedule changed recently
- Near-term horizon
- High chance of further changes

**Priority 2: Partial Complete Dates** (scrape every 3 days)
```python
is_complete == False AND days_since_change >= 3 AND date <= today + 30 days
```
- Gaps in schedule (runtime model shows room for more)
- Hasn't changed recently but incomplete
- Moderate chance of updates

**Priority 3: New Dates** (scrape daily)
```python
first_seen >= today - 1 day
```
- Recently appeared in horizon scan
- Need to monitor for early changes

**Priority 4: Stable Dates** (scrape weekly)
```python
is_stable == True AND date > today
```
- Low priority monitoring for rare changes

**No Re-scrape**:
```python
date < today OR (is_stable AND change_count == 0 AND days_since_first_seen > 30)
```

---

## Learning Dashboard Queries

### 1. Schedule Update Frequency

```sql
-- Average time between schedule updates
WITH changes_by_date AS (
    SELECT
        date,
        COUNT(*) as updates,
        MIN(detected_at) as first_update,
        MAX(detected_at) as last_update
    FROM schedule_changes
    WHERE change_type != 'first_seen'
    GROUP BY date
    HAVING COUNT(*) > 1
)
SELECT
    AVG((JULIANDAY(last_update) - JULIANDAY(first_update)) / (updates - 1)) as avg_days_between_updates
FROM changes_by_date;
```

### 2. Most Volatile Dates

```sql
-- Dates with most changes
SELECT
    date,
    change_count,
    first_seen,
    last_changed,
    final_showing_count,
    JULIANDAY(last_changed) - JULIANDAY(first_seen) as days_active
FROM schedule_stability
WHERE change_count >= 3
ORDER BY change_count DESC
LIMIT 20;
```

### 3. Change Type Distribution

```sql
-- What kinds of changes happen most?
SELECT
    change_type,
    COUNT(*) as occurrences,
    COUNT(DISTINCT date) as dates_affected
FROM schedule_changes
GROUP BY change_type
ORDER BY occurrences DESC;
```

---

## Expected Learnings

### Week 1-2: Discovery

**Goal**: Observe initial patterns

**Metrics**:
- How many dates change after first posting?
- What's the typical lead time (first_seen → showing_date)?
- Do weekends have different patterns than weekdays?

**Hypothesis to Test**:
- Most changes happen Monday-Wednesday (weekly schedule updates?)
- Schedules stabilize 7 days before showing
- Partial days (<3 showings) are more likely to change

### Week 3-4: Pattern Recognition

**Goal**: Identify scheduling behavior

**Metrics**:
- Average days between first posting and stability
- Percentage of dates that never change after initial posting
- Correlation between "complete" status and stability

**Hypothesis to Test**:
- "Complete" days (runtime model) rarely change
- Far-future dates (30+ days) get updated weekly
- Near-term dates (<7 days) are stable

### Month 2+: Optimization

**Goal**: Refine re-scrape strategy

**Metrics**:
- Prediction accuracy (stable vs unstable)
- Wasted scrapes (dates that didn't change)
- Missed changes (dates we didn't scrape that changed)

**Actions**:
- Adjust re-scrape frequency based on learned patterns
- Tune stability thresholds
- Identify special cases (holidays, premieres)

---

## Monitoring Reports

### Daily Change Report

```python
def generate_daily_change_report(date: datetime.date):
    """
    Generate report of schedule changes detected today

    Output:
        - New dates appeared
        - Dates with showings added
        - Dates with showings removed
        - Dates that became stable
    """
    report = {
        'date': date,
        'new_dates': get_dates_first_seen(date),
        'additions': get_changes(date, type='added'),
        'removals': get_changes(date, type='removed'),
        'newly_stable': get_newly_stable_dates(date)
    }
    return report
```

**Example Output**:
```
Daily Change Report - 2025-10-26
==================================

New Dates:
  - 2026-07-20 (3 showings)

Additions:
  - 2025-11-05: Added "Movie X" at 18:00
  - 2025-11-12: Added "Movie Y" at 14:30

Removals:
  - None

Newly Stable:
  - 2025-10-28 (5 showings, stable after 3 days)
  - 2025-10-29 (4 showings, stable after 2 days)

Summary:
  Total dates tracked: 23
  Unstable: 5
  Stable: 18
```

---

## Implementation Files

### `src/dynamicalsystem/listing/scraper/change_tracker.py`

```python
class ChangeTracker:
    """Track and analyze schedule changes over time"""

    def record_snapshot(self, date: str, showings: List[Dict]):
        """Record current state of a date's schedule"""

    def detect_changes(self, date: str, showings: List[Dict]) -> List[Dict]:
        """Compare to previous snapshot and return changes"""

    def mark_stable(self, date: str):
        """Mark a date as stable (unlikely to change)"""

    def get_unstable_dates(self) -> List[str]:
        """Get dates that need frequent re-scraping"""

    def get_learning_stats(self) -> Dict:
        """Get statistics for learning BFI patterns"""
```

---

## Test Case: Nov 12, 2025

**Current State** (2025-10-25):
- 1 showing: j-Hope at 20:45
- Runtime: 90 min
- Schedule model: Incomplete (large gaps)

**Tracking Plan**:
1. Record snapshot today
2. Re-scrape daily for next 7 days
3. Detect any additions/changes
4. Measure time to stability

**Expected Outcomes**:
- **If no changes**: Day is stable at 1 showing (special event)
- **If showings added**: Learn typical update frequency
- **If changes then stabilizes**: Learn stability pattern

**Data Collection**:
```
2025-10-25: 1 showing (first_seen)
2025-10-26: ? (re-scrape)
2025-10-27: ? (re-scrape)
...
2025-11-01: ? (re-scrape)
```

---

## Next Steps

1. **Implement** change tracking tables in SQLite
2. **Add** snapshot recording to scraper
3. **Test** with Nov 12 monitoring
4. **Create** weekly learning report
5. **Refine** re-scrape strategy based on learnings

---

## Success Metrics

### Short-term (Week 1-4)

- [ ] Track 100+ schedule snapshots
- [ ] Detect 10+ schedule changes
- [ ] Identify basic update patterns (day of week)
- [ ] Measure stability lead time (days before showing)

### Long-term (Month 2-3)

- [ ] Predict stability with 80%+ accuracy
- [ ] Reduce wasted scrapes by 50%
- [ ] Catch 95%+ of schedule changes
- [ ] Identify scheduling frequency patterns

---

## Conclusion

**Change tracking enables learning** from BFI's actual behavior rather than assumptions.

**Benefits**:
- Refine re-scrape strategy over time
- Detect anomalies (unusual update patterns)
- Optimize request load
- Build confidence in completion heuristic

**Philosophy**: Start with conservative re-scrape strategy, learn from observed changes, optimize based on data.
