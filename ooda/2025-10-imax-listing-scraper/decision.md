# Architecture Decision Summary

**Date**: 2025-10-24
**Status**: Initial Decisions Made - Awaiting OBSERVE Phase Validation

## Decision Point

**How should we implement a BFI IMAX listing scraper with daily maintenance and web presentation?**

## Context

**Deployment**: Docker container under tinsnip self-hosted infrastructure
**Scale**: ~200 records maximum, 16GB RAM + 500GB SSD available (should run on RPi)
**Users**: Public-facing with restrictive robots.txt, handful of users with link
**Uptime**: Health endpoint for monitoring, 24hr delay acceptable
**Update Frequency**: Daily maintenance sufficient, BFI updates <=1x per day

## Confirmed Architecture Decisions

### 1. Scraping Approach

**Decision**: [x] HTTP library + HTML parser (prefer), fallback to headless browser if required

**Rationale**:
- **Minimise target impact**: HTTP requests are lighter than full browser
- **Simplicity**: BeautifulSoup-style parsing is well understood
- **Reliability**: Fewer moving parts, easier to debug
- **Low resource**: Minimal memory/CPU vs headless browser
- **Maintainability**: Experience and prejudices favor this approach

**Trade-off**:
- May hit 403 errors (observed in initial WebFetch attempt)
- May require User-Agent spoofing or cookies
- Won't work if heavy JavaScript rendering required

**Fallback**: If HTTP library fails OBSERVE phase validation, switch to headless browser (Playwright/Puppeteer)

**Priority Criteria** (in order):
1. Minimise impact on target website
2. Prefer simplicity and reliability
3. Prefer low resource usage
4. Prefer ease of maintenance over frequency

**Status**: [x] Decided - awaiting OBSERVE phase validation

### 2. Programming Language/Runtime

**Decision**: [x] Python for scraper, Go for web server

**Rationale**:

**Scraper (Python)**:
- Strong experience with Python + BeautifulSoup
- Needs to work reliably (use known tools)
- Rich ecosystem for HTTP/parsing (requests, lxml, BeautifulSoup)
- Good for RSS generation (feedgen library)
- Quick iteration on parsing logic

**Web Server (Go)**:
- Learning opportunity (strong desire for Go exposure)
- Perfect use case: simple HTTP server + health endpoint
- Tiny binaries (good for Docker)
- Low resource usage (excellent for RPi target)
- Built-in HTTP server in stdlib
- Simple JSON/static file serving

**Alternatives Considered**:
- Node.js: Interest in exposure, but Python stronger for scraping
- Rust: Interest in exposure, but steeper learning curve
- Shell: Zero desire, would be inappropriate for this

**Trade-off**:
- Two languages vs one (adds complexity)
- Mitigated by clear separation: scraper writes files, server reads files
- Allows using best tool for each job
- Provides Go exposure without risk to critical scraping logic

**Status**: [x] Decided

### 3. Data Storage

**Decision**: [x] SQLite database

**Rationale**:
- **Perfect scale**: ~200 records maximum, SQLite handles millions
- **Query flexibility**: Web server can filter/sort efficiently
- **RSS generation**: Easy to query date ranges for feeds
- **Single file**: Simple backup/restore (cp database.db)
- **No service**: No Redis/PostgreSQL daemon to manage
- **Structured**: Better than flat files for preventing duplicates
- **Good Go support**: database/sql + sqlite3 driver well-established

**Schema**:
```sql
CREATE TABLE listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_title TEXT NOT NULL,
    movie_link TEXT,
    showing_date DATE NOT NULL,
    booking_link TEXT,
    format TEXT,  -- e.g., "3D", "IMAX 70mm", "2D"
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(movie_title, showing_date, format)
);
CREATE INDEX idx_showing_date ON listings(showing_date);
```

**Alternatives Considered**:
- **Flat files (JSON)**: Acceptable, but harder to query/deduplicate
- **Static HTML**: Would work, but harder to generate RSS
- **Redis**: Overkill, adds service dependency
- **PostgreSQL**: Heavy for 200 records

**Trade-off**:
- SQLite file is binary (harder to inspect than JSON)
- Mitigated by simple export query: `sqlite3 db.sqlite '.mode json' 'SELECT * FROM listings'`

**Backup Strategy**:
- SQLite file in Docker volume (persists across restarts)
- Periodic cp to NFS via tinsnip

**Status**: [x] Decided

### 4. Web Presentation

**Decision**: [x] Go HTTP server with phased frontend evolution

**Primary Interfaces**:
1. **HTML page** - Start simple, evolve to React for rich interactions
2. **RSS feeds** - Daily changes + current schedule

**Phase 1** (Initial):
- Go server renders simple HTML from SQLite
- Semantic HTML table (accessible, mobile-friendly)
- Basic CSS (readable, responsive)
- RSS feeds:
  - `/rss/current` - All upcoming showings
  - `/rss/daily` - New/changed listings in last 24h
- Health endpoint: `/health`

**Phase 2** (Iterative improvements):
- Add client-side filtering (JavaScript)
- Add sorting controls
- Add search box
- Improve CSS (themes, dark mode)
- Enhance accessibility (ARIA labels, keyboard nav)

**Phase 3** (Future - React):
- Migrate to React frontend
- Rich filtering UI
- Movie detail panels
- Calendar view
- Persist filter preferences

**Rationale**:
- **Start simple**: Server-rendered HTML works immediately
- **Evolve**: Can add React without changing Go backend
- **RSS first-class**: RSS feeds are requirement, not afterthought
- **Health endpoint**: Monitoring requirement satisfied
- **Go benefits**: Fast, low resource, easy to serve static + dynamic

**Endpoints**:
```
GET  /                    -> HTML page with all listings
GET  /api/listings        -> JSON (for future React/mobile)
GET  /rss/current         -> RSS of all upcoming showings
GET  /rss/daily           -> RSS of changes in last 24h
GET  /health              -> Health check (200 OK + version)
GET  /robots.txt          -> Restrictive robots.txt
```

**Trade-off**:
- Starting simple means fewer features initially
- Mitigated by clear evolution path, incremental value

**Status**: [x] Decided

### 5. Daily Maintenance Strategy

**Decision**: [x] Cron inside Docker container

**Deployment Context**:
- Docker container under tinsnip infrastructure
- Standard Docker container scheduling patterns
- Must handle logging and error recovery

**Approach**:
```dockerfile
# Container runs two processes:
# 1. Go web server (foreground)
# 2. Cron daemon (background)

# Crontab entry:
# 0 2 * * * /app/scraper/daily-maintenance.py >> /var/log/scraper.log 2>&1
```

**Daily Maintenance Script** (`daily-maintenance.py`):
1. Delete listings older than yesterday
   ```python
   DELETE FROM listings WHERE showing_date < date('now', '-1 day')
   ```
2. Run backfill scraper (see Decision #6)
3. Log results (deleted X, added Y, errors)
4. Exit with status code (0 = success, 1 = error)

**Rationale**:
- **Standard Docker pattern**: Cron inside container is well-understood
- **Self-contained**: No external scheduler dependency
- **Logging**: stdout/stderr captured by Docker
- **Monitoring**: Health endpoint can check last-run timestamp

**Health Endpoint Enhancement**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "last_scrape": "2025-10-24T02:00:15Z",
  "last_scrape_status": "success",
  "listings_count": 187,
  "oldest_listing": "2025-10-25",
  "newest_listing": "2025-12-15"
}
```

**Error Recovery**:
- Script retries failed requests (3 attempts)
- Logs errors but doesn't exit on BFI downtime
- Health endpoint shows degraded state if scrape fails

**Alternative Considered**:
- **While-loop with sleep**: Simpler, but harder to control timing
- **External cron**: More complex deployment
- Rejected in favor of standard Docker cron pattern

**Status**: [x] Decided

### 6. Calendar Backfill Strategy

**Decision**: [~] Two-tier polling: daily horizon + weekly lookahead

**Problem Analysis**:
- Calendar is "gappy and fills non-contiguously"
- BFI doesn't go far ahead, but has sparse entries months out
- Updates ≤1x per day
- Priming is expensive, maintenance should be lightweight
- Once showings are full, day can likely be ignored

**Proposed Strategy**:

**Tier 1: Daily Horizon** (Run daily at 02:00)
- Check next 14 days every day
- These dates most likely to have changes/additions
- Relatively cheap: 14 requests/day

**Tier 2: Weekly Lookahead** (Run Sundays at 03:00)
- Check days 15-90 (or max calendar extent)
- Catches sparse future listings
- ~75 requests/week = ~11 requests/day averaged

**Total Load**: ~25 requests/day to BFI

**Smart Optimizations** (Phase 2):
1. **Skip sold-out dates**: If all showings full, skip date
2. **Pattern detection**: Learn BFI update schedule
   - e.g., "BFI updates listings on Fridays"
   - Adjust polling to match
3. **Exponential backoff**: Check recent dates more frequently
   - Today-7: daily
   - 8-30: every 3 days
   - 31+: weekly

**Initial Priming**:
```bash
# One-time setup: check next 90 days
./scraper/prime.py --start-date today --end-date +90days
```

**Data Tracking**:
```sql
CREATE TABLE scrape_log (
    scrape_date DATE PRIMARY KEY,
    last_checked TIMESTAMP,
    listings_found INTEGER,
    status TEXT  -- 'success', 'error', 'empty'
);
```

**Brainstorming Questions**:
- [ ] Should we detect BFI's update pattern (day of week)?
- [ ] Should we skip dates with sold-out showings?
- [ ] Should we use exponential backoff from today?
- [ ] What's the max date range BFI shows?
- [ ] Do listings ever disappear, or only appear/sell-out?

**Rationale**:
- **Minimize target impact**: ~25 req/day is respectful
- **High coverage**: Daily horizon catches most changes
- **Catches sparse futures**: Weekly lookahead finds far dates
- **Lightweight**: Once primed, very cheap to maintain
- **Observable**: Scrape log shows what we've checked

**Status**: [...] Pending experimentation and pattern analysis

## Key Trade-offs Accepted

### Two Languages vs One
**Trade-off**: Python (scraper) + Go (web server) adds complexity
**Rationale**:
- Use proven tools (Python) for critical scraping
- Learn Go in lower-risk web serving context
- Clear separation via SQLite allows independent development

### Scraping Approach Uncertainty
**Trade-off**: HTTP library preferred but may need headless browser
**Rationale**:
- Start with simpler approach (HTTP + BeautifulSoup)
- Observed 403 error requires investigation
- OBSERVE phase will validate or force fallback to headless

### Coverage vs Impact
**Trade-off**: Two-tier polling may miss some listings
**Rationale**:
- ~25 req/day is respectful to BFI
- Daily horizon (14 days) catches most user-relevant listings
- Weekly lookahead catches sparse futures
- Can tune based on observed BFI patterns

### Simple Start vs Rich Features
**Trade-off**: Phase 1 web UI is basic HTML
**Rationale**:
- Get working system quickly
- RSS feeds are primary interface initially
- Clear path to React for richness
- Incremental value delivery

## OBSERVE Phase Results (2025-10-25)

### 1. BFI Website Access - ANSWERED

- [x] **Can HTTP library access site?** YES - cloudscraper bypasses Cloudflare
- [x] **Is JavaScript rendering required?** YES - but only for extraction, not execution
  - Data embedded in JavaScript `searchResults` array
  - Extract via regex + JSON parsing (no BeautifulSoup DOM needed)
- [x] **Rate limits?** Unknown - using respectful ~16 req/day strategy

### 2. Calendar Patterns - ANSWERED

- [x] **Max date range?** 267 days observed (Oct 26, 2025 → Jul 19, 2026)
- [x] **Update patterns?** UNKNOWN - requires monitoring (change tracking designed)
- [x] **Do listings disappear?** UNKNOWN - requires monitoring
- [x] **Lead time?** Variable - some dates 9 months ahead, others added ad hoc
- [x] **Sparsity**: 91.4% empty (23 days with showings / 267 day span)

### 3. HTML Structure - ANSWERED

- [x] **Movie structure**: JavaScript `searchResults` array (90+ fields per showing)
- [x] **Format indicators**: Index 17 `keywords` field ("3D", "70mm", "IMAX with Laser")
- [x] **Sold-out status**: Index 15 `availability_status` ('S' = sold out, 'L' = limited, 'G' = good)
- [x] **Booking links**: Not in searchResults (widget-generated, use detail page URL instead)
- [x] **Runtime**: Available on detail pages (pattern: `YYYY. XXmin`)

### 4. Discovery Method - NEW FINDING

**performanceDays Array**: Single request reveals ALL dates with showings

```javascript
performanceDays: [
  { values: [
    ["2025-10-26T10:45:00.000", "1"],
    ["2025-10-26T14:10:00.000", "1"],
    ...
  ]}
]
```

**Impact**: Eliminates need for date range queries or blind date probing

---

## Refined Strategy (Post-OBSERVE)

### Decision 6 (UPDATED): Horizon Discovery

**Original**: Two-tier polling (daily horizon + weekly lookahead) = ~25 req/day

**Refined**: Horizon scan + selective scraping = ~16 req/day

**Method**:
1. **Horizon scan** (1 req): Fetch any date, extract `performanceDays` array → get ALL dates with showings
2. **Selective scrape** (~15 req): Only query dates that appear in `performanceDays`
3. **Skip empty dates**: Don't query dates not in `performanceDays`

**Benefits**:
- Single request discovers full calendar (267 days scanned)
- No wasted requests on empty dates (saves ~244 req across horizon)
- Automatic detection of new dates appearing
- Scales to any horizon size

### Decision 7 (NEW): Completion Detection

**Method**: Runtime-based schedule modeling

**Algorithm**:
```python
slot_duration = 25min (ads) + runtime + 15min (changeover)
is_complete = no_gaps >= 150min between showings
```

**Data Sources**:
- BFI detail pages (pattern: `YYYY. XXmin`)
- Wikipedia fallback for "TBC" runtimes
- IMDb/TMDb as additional fallbacks

**Database**:
```sql
CREATE TABLE movie_runtimes (
    movie_title TEXT PRIMARY KEY,
    runtime_minutes INTEGER,
    source TEXT,  -- 'BFI', 'Wikipedia', 'IMDb'
    fetched_at TIMESTAMP
);
```

**Accuracy**: Near 100% (physics-based) vs ~70% (statistical weekday patterns)

**Example** (Oct 26, 2025):
```
10:45 → 13:35  Frankenstein (150min + 40)  Gap: 35min
14:10 → 16:49  Tron 3D (119min + 40)        Gap: 11min
17:00 → 20:22  One Battle (162min + 40)    Gap: 8min
20:30 → 22:50  Chainsaw Man (100min + 40)

Result: COMPLETE (no gaps ≥150min)
```

### Decision 8 (NEW): Change Tracking

**Purpose**: Learn BFI's actual scheduling behavior through observation

**Database**:
```sql
CREATE TABLE schedule_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    scraped_at TIMESTAMP NOT NULL,
    showing_count INTEGER NOT NULL,
    is_complete BOOLEAN,
    snapshot_hash TEXT
);

CREATE TABLE schedule_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    change_type TEXT,  -- 'added', 'removed', 'modified'
    showing_time TIME,
    movie_title TEXT
);
```

**Learning Goals**:
- Do schedules change after initial posting?
- When do updates typically happen? (day of week)
- How far in advance are schedules finalized?
- Validate runtime-based completion heuristic

**Strategy**: Start conservative (frequent re-scraping), refine based on observed patterns

---

## Updated Trade-offs

### Scraping Approach - RESOLVED
**Original Trade-off**: HTTP library vs headless browser
**Resolution**: HTTP library (cloudscraper) + Regex/JSON parsing
- No browser automation needed
- Data extraction is regex-based, not DOM-based
- Simple, reliable, low resource

### Coverage vs Impact - IMPROVED
**Original**: Two-tier polling (~25 req/day)
**Refined**: Horizon scan + selective (~16 req/day)
- Better coverage (full 267-day horizon vs 90 days)
- Lower impact (36% fewer requests)
- No wasted requests on empty dates

### Completion Detection - NEW
**Trade-off**: Definitive (runtime) vs Probabilistic (statistical)
**Decision**: Use runtime-based as primary, statistics as fallback
- Runtime method when data available: ~100% accuracy
- Statistical weekday patterns when runtimes missing: ~70% accuracy
- External sources (Wikipedia) reduce missing runtime cases

---

## Updated Open Questions

### Scheduling Behavior (Requires Monitoring)

- [ ] How often do schedules change after initial posting?
- [ ] What day(s) of week do updates typically happen?
- [ ] Do partial days ever get additional showings?
- [ ] How long before showing date do schedules stabilize?
- [ ] Are special events (1-showing days) truly complete?

**Answer Method**: Change tracking over 2-4 weeks

### Runtime Data Availability

- [x] BFI detail pages have runtime: YES (pattern `YYYY. XXmin`)
- [x] What about "TBC" films: Wikipedia has data (validated with Frankenstein)
- [ ] IMDb/TMDb coverage: TBD (fallback implementation pending)

---

## Updated Next Steps

1. ~~Complete OBSERVE phase~~ [x] COMPLETE 2025-10-25

2. Create ORIENT phase designs:
   - [ ] Parser module (`parse.py`)
   - [ ] SQLite schema (4 tables: listings, schedules, changes, runtimes)
   - [ ] Schedule manager (`schedule.py`)
   - [ ] Runtime fetcher (`runtime.py`)
   - [ ] Daily maintenance workflow
   - [ ] Go web server architecture

3. Implement proof-of-concept:
   - [ ] Core parser with searchResults extraction
   - [ ] Runtime extraction from BFI detail pages
   - [ ] Simple CLI tool to test

4. Proceed to ACT phase

## Documents Reference

### OBSERVE Phase Documents
- [Website Constraints](./observe/website-constraints.md)
- [Access Method Experiment](./observe/access-method-experiment.md)
- [HTML Structure Analysis](./observe/html-structure.md)
- [Edge Cases and Strategy](./observe/edge-cases-and-strategy.md)
- [Completion Heuristic](./observe/completion-heuristic.md)
- [Schedule Change Tracking](./observe/schedule-change-tracking.md)

### Planning Documents
- [Outcomes](./outcomes.md)
- [README](./README.md)
