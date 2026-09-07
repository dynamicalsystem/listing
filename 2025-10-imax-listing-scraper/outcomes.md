# BFI IMAX Listing Scraper - Outcomes

**Start Date**: 2025-10-24
**Status**: [x] Resolved at closure, 2026-09-07

This document defines the measurable outcomes for this deliverable.

**Closure note (2026-09-07)**: The test commands below were written before the
DECIDE phase and describe the original file-based design (`scrape.sh`, JSON
files per date). The system as built is a SQLite database
(`dynamicalsystem.listing.storage`) maintained by
`python -m dynamicalsystem.listing.maintenance.daily` and served by a FastAPI
app (`dynamicalsystem.listing.webserver.main`). Criteria were validated against
the real interfaces; the literal shell commands are superseded. Validation
evidence: live maintenance run on 2026-09-07 (33 dates discovered and scraped,
102 listings, 0 errors, exit code 0) into a scratch database, then all web
endpoints exercised against it. Two integration bugs found and fixed during
validation (cleanup call signatures, horizon scan no-results fallback) - see
the loop README Action section.

## Outcome 1: Scrape BFI IMAX Schedule

### Outcome

Operators can extract structured movie listing data from the BFI IMAX website.

### Test

Superseded: validated via a live run of
`python -m dynamicalsystem.listing.maintenance.daily --db-path <db>` followed
by inspection of the `listings` table and the `/` page.

### Success Criteria

- [/] Scraper successfully retrieves BFI IMAX schedule page (cloudscraper, live 2026-09-07)
- [/] Extracts all movie titles on the page
- [/] Captures movie detail links
- [/] Captures booking links
- [/] Records showing date
- [/] Outputs structured data (SQLite `listings` table; supersedes JSON files)
- [/] Handles missing/optional fields gracefully (parser unit tests)
- [/] Returns clear error messages on failure (logged errors + three-tier exit codes)

## Outcome 2: Handle Sparse Calendar Backfill

### Outcome

System can discover and fill in listings as they appear in the sparse, non-contiguous calendar.

### Test

Superseded: horizon scan via performanceDays replaces date-range polling.
Validated live (33 sparse dates discovered spanning 2026-09-07 to 2026-12-20)
plus schedule-manager integration tests.

### Success Criteria

- [/] Scraper can query multiple dates in a range (horizon scan + per-date scrape)
- [/] Handles dates with no listings (no-results page handling, unit tested)
- [/] Merges new listings with existing data (INSERT OR IGNORE semantics)
- [/] Doesn't duplicate existing records (unique bfi_showing_id, unit tested)
- [/] Can be run repeatedly without corruption (snapshot/change tests)
- [/] Identifies which dates have been checked (`scrape_schedule` table)
- [/] Logs dates where new listings were found (change detection log lines)

## Outcome 3: Daily Maintenance

### Outcome

System automatically maintains current listings by removing old entries and adding new ones.

### Test

Superseded: validated via live run of
`python -m dynamicalsystem.listing.maintenance.daily` (exit 0) and
`--dry-run`, plus 20 unit tests in `tests/test_daily.py`.

### Success Criteria

- [/] Deletes listings older than yesterday (`delete_old_listings(today)`; bug found and fixed at closure)
- [/] Preserves today's and future listings (unit tested)
- [/] Scrapes new listings for configurable date range (horizon-driven)
- [/] Can run via cron/scheduled task (CLI entry point, env-var config, exit codes)
- [/] Logs actions taken (run summary: dates scraped, changes, errors)
- [/] Fails safely (empty horizon scan no longer cascades into removals; fixed at closure)
- [/] Can be run manually for testing (`--dry-run`, `--verbose`, `--db-path`)

## Outcome 4: Web Presentation

### Outcome

Users can view all current IMAX listings in a web browser.

### Test

Superseded: validated by running
`uvicorn dynamicalsystem.listing.webserver.main:app` against the live-scraped
database and exercising `/`, `/health`, `/rss/current`, `/rss/daily`.

### Success Criteria

- [/] Web server serves HTML page (200, `<title>BFI IMAX Listings</title>`)
- [/] Page displays all current listings (102 listings rendered)
- [/] Movie titles rendered correctly
- [/] Links are clickable and functional (103 detail/booking links on page)
- [/] Dates formatted clearly
- [/] Page updates when data changes (queries database per request)
- [/] Handles empty listing set gracefully (template empty state)
- [/] Works on mobile browsers (responsive CSS; manual check at ACT-05)
- [/] Page loads quickly (< 2 seconds; measured 23ms locally)

## Outcome 5: End-to-End Workflow

### Outcome

Complete workflow from scraping to presentation operates reliably over time.

### Test

Single-cycle end-to-end validated live 2026-09-07: empty database ->
maintenance run -> populated database -> web page and feeds serving current
listings. Multi-day durability criteria below require a production deployment,
which does not exist yet.

### Success Criteria

- [/] Initial scrape populates database (33 dates, 102 listings)
- [/] Web server shows data immediately
- [/] Daily maintenance runs without intervention (exit 0, healthcheck ping hook)
- [/] Old data automatically removed (cleanup step verified; nothing old to delete on first run)
- [/] New data automatically added
- [/] System recovers from BFI website downtime (per-date error isolation; horizon fallback)
- [/] Logs provide audit trail (structured log file + run summary)
- [ ] No manual intervention needed for 30+ days - ABANDONED at closure: the
      system is not deployed, so a 30-day soak test cannot run. Deployment
      (Docker + cron + hosting) is follow-up work outside this loop's scope.
