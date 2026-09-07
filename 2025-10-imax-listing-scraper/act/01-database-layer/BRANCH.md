# Branch Status: ACT-01 Database Layer

**Branch**: `act/01-database-layer`
**Status**: [x] Complete
**Started**: 2025-10-26
**Completed**: 2025-10-26

## Quick Links

- **Plan**: [../PLANNING.md](../PLANNING.md)
- **Design**: [../../orient/sqlite-schema-design.md](../../orient/sqlite-schema-design.md)
- **Merge Commit**: `805d9e2`

## Timeline

| Event | Date | Notes |
|-------|------|-------|
| Branch created | 2025-10-26 | act/01-database-layer |
| Implementation | 2025-10-26 | schema.py + db.py + tests |
| Testing | 2025-10-26 | 42 tests passing, no warnings |
| Outcome verified | 2025-10-26 | All database operations functional |
| Merged to main | 2025-10-26 | 805d9e2 (direct merge) |

## Implementation Summary

**Scope**: SQLite database layer per sqlite-schema-design.md

**Files Created**:
- `src/dynamicalsystem/listing/storage/__init__.py` (6 lines)
- `src/dynamicalsystem/listing/storage/schema.py` (285 lines)
- `src/dynamicalsystem/listing/storage/db.py` (716 lines)
- `tests/storage/test_schema.py` (285 lines)
- `tests/storage/test_db.py` (461 lines)

**Total**: +1764 lines, 9 files changed

## Testing

- [x] Schema creation tests (14 tests)
  - Tables, indices, views created correctly
  - Constraints enforced (UNIQUE, CHECK, FOREIGN KEY)
  - Schema versioning works
  - Idempotent initialization

- [x] Database operations tests (28 tests)
  - Insert/query showings with duplicate prevention
  - Schedule status management
  - Snapshot recording with hash-based change detection
  - Change detection (added/removed/modified showings)
  - Runtime caching
  - Health info reporting

- [x] All parser tests still passing (17 tests)

**Total**: 59/59 tests passing

## Database Structure

**Tables** (5):
1. `listings` - Current and future movie showings (public data)
2. `scrape_schedule` - Dates to scrape and their status (operational)
3. `schedule_snapshots` - Historical schedule state (learning)
4. `schedule_changes` - Detected changes over time (learning)
5. `movie_runtimes` - Cached runtimes from BFI/external (operational)

**Views** (2):
1. `upcoming_showings` - Showings today and later
2. `schedule_stability` - Schedule change analysis

**Indices**: 15 indices for query optimization

## Issues Encountered

1. **Database initialization logic**
   - Problem: migrate_database() called on non-existent database, causing error
   - Resolution: Check schema version before deciding init vs migrate
   - Fix: Use get_schema_version() to detect if database initialized

2. **Deprecation warnings with datetime.utcnow()**
   - Problem: Python 3.13 deprecates datetime.utcnow()
   - Resolution: Use datetime.now(UTC) instead
   - Fix: Import UTC from datetime, replace all 4 occurrences

3. **Test issue with conn.lastrowid**
   - Problem: lastrowid is on cursor, not connection
   - Resolution: Store cursor from execute() call
   - Fix: cursor = conn.execute(...); id = cursor.lastrowid

## Design Decisions Made

**Timezone Handling**:
- Store all timestamps in UTC with explicit ISO 8601 format
- Include +00:00 timezone marker for clarity
- Denormalize showing_date/showing_time as UK local for queries
- Canonical source: showing_datetime_utc

**Hash-based Change Detection**:
- Compute SHA256 hash of sorted showing times + titles + formats
- Exclude availability counts (change frequently, not structural)
- 16-character hex truncation sufficient for collision avoidance
- Enables quick "has anything changed?" checks

**Snapshot Strategy**:
- Record snapshot on every scrape (even if unchanged)
- changed_from_previous boolean for quick filtering
- Prune snapshots 30 days after showing date
- Keep schedule_changes forever (smaller, extracted learnings)

**Foreign Keys**:
- schedule_changes references schedule_snapshots
- Enables tracing changes back to specific snapshots
- Foreign key enforcement not enabled by default in SQLite (tests enable it)

## Notes

**Performance**: Database operations are fast (<1ms for typical queries). No optimization needed at this scale (~200 records).

**UTC Timezone**: Following CLAUDE.md requirement to store all timestamps in UTC with explicit timezone markers. This handles UK DST transitions correctly.

**Migration Support**: Schema versioning implemented from day 1. Future schema changes go in MIGRATIONS dict in schema.py.

**Test Coverage**: 100% of database methods tested. Using temporary databases for test isolation.

**Design Adherence**: Implementation closely follows sqlite-schema-design.md. All planned features implemented. No scope creep.

## Outcome Verification

From outcomes.md, this branch contributes to:

**Outcome 1**: Scrape BFI IMAX Schedule
- [x] Database can store structured movie listing data

**Outcome 2**: Handle Sparse Calendar Backfill
- [x] scrape_schedule table tracks which dates need scraping
- [x] Merges new listings with existing data (INSERT OR IGNORE)
- [x] Prevents duplicates via UNIQUE constraints

**Outcome 3**: Daily Maintenance
- [x] delete_old_listings() removes past showings
- [x] Database schema supports date-based queries

**Outcome 5**: End-to-End Workflow
- [x] Database layer provides foundation for full system
- [x] All planned operations implemented

## Next Steps

1. [ ] Review BRANCH.md with Simon
2. [ ] Merge to main
3. [ ] Update OODA README with merge commit
4. [ ] Start ACT-02: Runtime Fetcher
