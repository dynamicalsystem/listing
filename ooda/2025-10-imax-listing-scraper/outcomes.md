# BFI IMAX Listing Scraper - Outcomes

**Start Date**: 2025-10-24
**Status**: [...] OBSERVE Phase In Progress

This document defines the measurable outcomes for this deliverable.

## Outcome 1: Scrape BFI IMAX Schedule

### Outcome

Operators can extract structured movie listing data from the BFI IMAX website.

### Test

```bash
# Run scraper for a specific date
./scrape.sh 2025-10-25

# Expected output: JSON/CSV file containing:
# - Movie title: "Blue Whales: Return of the Giants (3D)"
# - Movie detail link: https://whatson.bfi.org.uk/imax/Online/...
# - Showing date: 2025-10-25
# - Booking link: https://whatson.bfi.org.uk/imax/Online/...

# Verify data extracted
cat data/listings-2025-10-25.json
# Expected: Valid JSON with array of movie records
```

### Success Criteria

- [ ] Scraper successfully retrieves BFI IMAX schedule page
- [ ] Extracts all movie titles on the page
- [ ] Captures movie detail links
- [ ] Captures booking links
- [ ] Records showing date
- [ ] Outputs structured data (JSON or similar)
- [ ] Handles missing/optional fields gracefully
- [ ] Returns clear error messages on failure

## Outcome 2: Handle Sparse Calendar Backfill

### Outcome

System can discover and fill in listings as they appear in the sparse, non-contiguous calendar.

### Test

```bash
# Initial scrape
./scrape.sh --date-range 2025-10-25 2025-11-25

# Verify sparse data captured
cat data/listings-*.json | jq '.[] | .date' | sort | uniq
# Expected: Dates with listings (may have gaps)

# Re-run days later to capture newly added listings
./scrape.sh --date-range 2025-10-25 2025-11-25

# Verify new listings added
diff data/listings-2025-10-25.json data/listings-2025-10-25.json.backup
# Expected: New entries if BFI added listings
```

### Success Criteria

- [ ] Scraper can query multiple dates in a range
- [ ] Handles dates with no listings (empty result)
- [ ] Merges new listings with existing data
- [ ] Doesn't duplicate existing records
- [ ] Can be run repeatedly without corruption
- [ ] Identifies which dates have been checked
- [ ] Logs dates where new listings were found

## Outcome 3: Daily Maintenance

### Outcome

System automatically maintains current listings by removing old entries and adding new ones.

### Test

```bash
# Setup: Create listings for yesterday and today
echo '[{"movie": "Test", "date": "2025-10-23"}]' > data/listings-2025-10-23.json
echo '[{"movie": "Test", "date": "2025-10-24"}]' > data/listings-2025-10-24.json

# Run daily maintenance
./daily-maintenance.sh

# Verify yesterday's data removed
ls data/listings-2025-10-23.json
# Expected: File does not exist

# Verify today's data preserved
ls data/listings-2025-10-24.json
# Expected: File exists

# Verify new listings added
cat data/listings-2025-10-25.json
# Expected: Today's newly scraped listings
```

### Success Criteria

- [ ] Deletes listings older than yesterday
- [ ] Preserves today's and future listings
- [ ] Scrapes new listings for configurable date range
- [ ] Can run via cron/scheduled task
- [ ] Logs actions taken (deleted X files, added Y listings)
- [ ] Fails safely (doesn't delete everything on error)
- [ ] Can be run manually for testing

## Outcome 4: Web Presentation

### Outcome

Users can view all current IMAX listings in a web browser.

### Test

```bash
# Start web server
./serve.sh

# Open browser to localhost:PORT
# Expected page contents:
# - List of all movies with showings
# - For each movie:
#   - Movie title
#   - Link to movie details (clickable)
#   - Showing dates
#   - Link to book tickets (clickable)
# - Sorted by date (earliest first)
# - Clear indication of 3D vs 2D vs 70mm etc.

# Manual verification:
# 1. Click movie detail link -> opens BFI page
# 2. Click booking link -> opens BFI booking page
# 3. Multiple showings of same movie grouped sensibly
# 4. Page is readable and usable
```

### Success Criteria

- [ ] Web server serves HTML page
- [ ] Page displays all current listings
- [ ] Movie titles rendered correctly
- [ ] Links are clickable and functional
- [ ] Dates formatted clearly (YYYY-MM-DD or human-readable)
- [ ] Page updates when data changes
- [ ] Handles empty listing set gracefully
- [ ] Works on mobile browsers
- [ ] Page loads quickly (< 2 seconds)

## Outcome 5: End-to-End Workflow

### Outcome

Complete workflow from scraping to presentation operates reliably over time.

### Test

```bash
# Day 1: Initial setup
./scrape.sh --date-range 2025-10-25 2025-12-31
./serve.sh &

# Verify webpage shows listings
curl http://localhost:PORT | grep "Blue Whales"

# Day 2: Daily maintenance runs
./daily-maintenance.sh

# Verify old data removed
ls data/listings-2025-10-24.json
# Expected: Does not exist (if 2025-10-24 is now in past)

# Verify new data added
curl http://localhost:PORT | grep -c "movie"
# Expected: Count of current movies

# Day 30: System still running
curl http://localhost:PORT
# Expected: Shows current listings, no stale data
```

### Success Criteria

- [ ] Initial scrape populates database
- [ ] Web server shows data immediately
- [ ] Daily maintenance runs without intervention
- [ ] Old data automatically removed
- [ ] New data automatically added
- [ ] System recovers from BFI website downtime
- [ ] Logs provide audit trail
- [ ] No manual intervention needed for 30+ days
