# ACT Phase Planning

**Date**: 2025-10-26
**Status**: [~] In Progress
**Purpose**: Define implementation strategy for BFI IMAX scraper

---

## Overview

The ACT phase implements the 6 ORIENT designs as working code with tests.

**ORIENT Designs to Implement**:
1. [x] Parser module - Already implemented (17 tests passing)
2. [ ] SQLite schema + database layer
3. [ ] Runtime fetcher
4. [ ] Schedule manager
5. [ ] Daily maintenance workflow
6. [ ] Go web server

**Current State**: Parser MVP exists, needs database integration

---

## Implementation Strategy

### Approach: Bottom-Up

Implement in dependency order (foundation → higher layers):

```
Layer 1 (Foundation):
  - Database schema + layer
  ↓
Layer 2 (Data acquisition):
  - Runtime fetcher
  ↓
Layer 3 (Orchestration):
  - Schedule manager
  ↓
Layer 4 (Automation):
  - Daily maintenance
  ↓
Layer 5 (Presentation):
  - Go web server
```

**Rationale**: Each layer depends on previous layers. Can't test schedule manager without database.

---

## Branch Strategy

Following workflow.md, each implementation task gets:
1. Own branch from main: `act/NN-task-name`
2. Own tracking doc: `act/NN-task-name/BRANCH.md`
3. Tests before merge
4. Direct merge to main (no PRs for solo project)

### Branch Naming

```
act/01-database-layer
act/02-runtime-fetcher
act/03-schedule-manager
act/04-daily-maintenance
act/05-go-webserver
```

---

## Implementation Breakdown

### ACT-01: Database Layer

**Branch**: `act/01-database-layer`
**Dependencies**: None (foundation)
**Estimate**: 1-2 days

**Tasks**:
- [ ] Implement schema.py (CREATE TABLE statements)
- [ ] Implement db.py (Database class with all methods)
- [ ] Migration support (schema versioning)
- [ ] Unit tests for database operations
- [ ] Integration tests with SQLite

**Success Criteria**:
- Schema creates successfully
- All CRUD operations work
- Tests cover all database methods
- Can insert/query showings
- Can manage scrape_schedule state

**Files to Create**:
```
src/dynamicalsystem/listing/storage/
  __init__.py
  schema.py          # Schema definitions
  db.py              # Database class
tests/
  test_schema.py     # Schema creation tests
  test_db.py         # Database operation tests
```

---

### ACT-02: Runtime Fetcher

**Branch**: `act/02-runtime-fetcher`
**Dependencies**: ACT-01 (needs database for caching)
**Estimate**: 2-3 days

**Tasks**:
- [ ] Implement runtime.py (RuntimeFetcher class)
- [ ] BFI detail page extraction
- [ ] Wikipedia fallback
- [ ] IMDb fallback (optional)
- [ ] Database caching integration
- [ ] Rate limiting
- [ ] Unit tests with mock responses
- [ ] Integration tests with live sites (manual)

**Success Criteria**:
- Extracts runtime from BFI detail pages
- Falls back to Wikipedia for TBC runtimes
- Caches results in database
- Rate limits external requests
- Never crashes (returns None on failure)

**Files to Create**:
```
src/dynamicalsystem/listing/scraper/
  runtime.py         # RuntimeFetcher class
tests/
  test_runtime.py    # Runtime extraction tests
  fixtures/
    bfi_detail_*.html      # Sample BFI pages
    wikipedia_*.html       # Sample Wikipedia pages
```

---

### ACT-03: Schedule Manager

**Branch**: `act/03-schedule-manager`
**Dependencies**: ACT-01, ACT-02 (needs db + runtime fetcher)
**Estimate**: 3-4 days

**Tasks**:
- [ ] Implement schedule.py (ScheduleManager class)
- [ ] Horizon scanning (extract_performance_days)
- [ ] Re-scrape prioritization (5 tiers)
- [ ] Change detection (field-level)
- [ ] Completion detection (runtime-based)
- [ ] Snapshot management
- [ ] Unit tests for each component
- [ ] Integration tests for full workflow

**Success Criteria**:
- Horizon scan discovers all dates
- Priority logic correctly orders dates
- Change detection catches add/remove/modify
- Completion detection >90% accurate
- Full scrape run completes successfully
- Database state always consistent

**Files to Create**:
```
src/dynamicalsystem/listing/scraper/
  schedule.py        # ScheduleManager class
tests/
  test_schedule.py   # Schedule manager tests
```

---

### ACT-04: Daily Maintenance

**Branch**: `act/04-daily-maintenance`
**Dependencies**: ACT-03 (orchestrates schedule manager)
**Estimate**: 1 day

**Tasks**:
- [ ] Implement daily.py (main script)
- [ ] Logging setup (console + file)
- [ ] Configuration loading
- [ ] Exit code handling
- [ ] Dry-run mode
- [ ] Health check integration
- [ ] Unit tests
- [ ] Integration test (full run)

**Success Criteria**:
- Runs successfully end-to-end
- Logs all activities
- Exit codes correct
- Dry-run mode works
- Can be invoked manually
- Handles errors gracefully

**Files to Create**:
```
src/dynamicalsystem/listing/maintenance/
  __init__.py
  daily.py           # Main maintenance script
src/dynamicalsystem/listing/
  config.py          # Configuration
tests/
  test_daily.py      # Maintenance script tests
```

---

### ACT-05: Go Web Server

**Branch**: `act/05-go-webserver`
**Dependencies**: ACT-01 (reads from database)
**Estimate**: 2-3 days

**Tasks**:
- [ ] Project structure (main.go, handlers/, etc.)
- [ ] Database connection (Go SQLite driver)
- [ ] HTTP handlers (listings, RSS, health)
- [ ] HTML templates
- [ ] CSS styling
- [ ] Static file serving
- [ ] Unit tests for handlers
- [ ] Integration tests
- [ ] Dockerfile

**Success Criteria**:
- HTML page displays listings
- RSS feeds work
- Health endpoint accurate
- Mobile responsive
- Tests pass
- Docker container builds
- Graceful shutdown works

**Files to Create**:
```
src/webserver/
  main.go
  go.mod
  handlers/
    listings.go
    rss.go
    health.go
    static.go
  db/
    db.go
    queries.go
  models/
    models.go
  templates/
    base.html
    listings.html
  static/
    css/style.css
  config/
    config.go
tests/
  handlers_test.go
  db_test.go
Dockerfile
```

---

## Testing Strategy

### Unit Tests

**Goal**: Test individual functions in isolation

**Approach**:
- Mock external dependencies (HTTP requests, database)
- Test edge cases (empty results, errors, invalid input)
- Fast execution (<1 second per test file)

**Coverage Target**: >80% for all modules

### Integration Tests

**Goal**: Test components working together

**Approach**:
- Use in-memory SQLite (`:memory:`)
- Use fixture HTML files (not live requests)
- Test full workflows (scrape → parse → database)

**Examples**:
- Scrape date → Parse → Insert to DB → Query back
- Schedule manager full run with mock fetcher

### End-to-End Tests

**Goal**: Validate complete system

**Approach**:
- Real SQLite database file
- Mock external HTTP requests
- Run full daily maintenance
- Verify database state

**Test Scenarios**:
1. Fresh database initialization
2. Daily scrape with no changes
3. Daily scrape with new showings
4. Daily scrape with changes to existing
5. Date becomes complete (runtime-based)

---

## Merge Criteria

Every branch must meet these criteria before merge:

- [ ] All tests pass (`pytest tests/`)
- [ ] Code follows Python style (no linting errors)
- [ ] New code has tests (unit + integration)
- [ ] Documentation updated (docstrings, README if needed)
- [ ] No TODO comments without GitHub issues
- [ ] Manual testing performed (where applicable)
- [ ] BRANCH.md updated with completion details

---

## Risk Management

### Risk 1: Database Schema Changes

**Risk**: Schema evolves during implementation, requires migrations

**Mitigation**:
- Implement schema versioning from ACT-01
- Write migration tests
- Document schema changes in BRANCH.md

### Risk 2: BFI Website Changes

**Risk**: BFI changes HTML structure, parser breaks

**Mitigation**:
- Use fixture HTML files for tests
- Don't test against live site in CI
- Validation in parser (fail early if structure unexpected)
- Alert on parse failures

### Risk 3: External API Rate Limits

**Risk**: Wikipedia/IMDb block requests during testing

**Mitigation**:
- Use fixtures for all automated tests
- Mark live tests as manual-only
- Implement rate limiting from start
- Cache aggressively

### Risk 4: Scope Creep

**Risk**: Adding features beyond ORIENT designs

**Mitigation**:
- Strict adherence to designs
- Document "future enhancements" separately
- Defer non-essential features to Phase 2

---

## Timeline Estimate

| Branch | Estimate | Cumulative |
|--------|----------|------------|
| ACT-01 | 1-2 days | 2 days |
| ACT-02 | 2-3 days | 5 days |
| ACT-03 | 3-4 days | 9 days |
| ACT-04 | 1 day    | 10 days |
| ACT-05 | 2-3 days | 13 days |
| **Total** | **~2 weeks** | |

**Note**: Estimates assume full-time work. Adjust based on availability.

---

## Definition of Done

ACT phase is complete when:

- [ ] All 5 implementation branches merged to main
- [ ] All outcomes.md tests pass
- [ ] End-to-end workflow works:
  1. Daily maintenance scrapes BFI
  2. Database populated with listings
  3. Web server displays listings
  4. RSS feeds work
- [ ] Docker container runs (cron + web server)
- [ ] Health endpoint reports accurately
- [ ] Documentation updated
- [ ] No critical bugs

---

## Next Steps

1. [ ] **Review**: Simon reviews ACT strategy
2. [ ] **Approve**: Mark strategy as approved
3. [ ] **Branch**: Create `act/01-database-layer` branch
4. [ ] **Implement**: Start ACT-01
5. [ ] **Test**: Write tests as you implement
6. [ ] **Merge**: Merge ACT-01 to main
7. [ ] **Repeat**: For ACT-02 through ACT-05

---

## Open Questions

### 1. Docker Compose Strategy

**Question**: Single container (Python + Go) or separate containers?

**Options**:
- **Single**: Simpler deployment, shared volume
- **Separate**: Cleaner separation, independent scaling

**Recommendation**: Start with single container, can split later.

### 2. Testing Against Live BFI

**Question**: How often should we test against live BFI site?

**Options**:
- Never in CI (only fixtures)
- Weekly manual check
- On-demand via manual test flag

**Recommendation**: Fixtures in CI, weekly manual validation.

### 3. Configuration Management

**Question**: Environment variables only, or config file support?

**Options**:
- Env vars only (12-factor app)
- Config file + env var overrides

**Recommendation**: Env vars only for simplicity.

---

## Related Documents

- [Outcomes](../outcomes.md) - Success criteria
- [Workflow](../workflow.md) - Branch strategy
- [ORIENT Designs](../orient/) - Implementation specs
- [Decision](../decision.md) - Architecture decisions
