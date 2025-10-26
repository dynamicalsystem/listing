# Daily Maintenance Workflow Design

**Date**: 2025-10-26
**Status**: [x] Approved
**File**: `src/dynamicalsystem/listing/maintenance/daily.py`
**Purpose**: Orchestrate daily scraping run and data cleanup

---

## Purpose

Run daily maintenance to:
1. Scrape BFI IMAX schedule (horizon scan + selective re-scrape)
2. Update database (listings, snapshots, changes)
3. Clean up old data (past showings, old snapshots)
4. Log results for monitoring
5. Exit with appropriate status code

**Invocation**: Via cron inside Docker container at 02:00 UTC daily

---

## Architecture

### Simple Orchestration

The daily maintenance script is a **thin wrapper** around ScheduleManager:

```
daily.py
  ↓
ScheduleManager.scrape_all_pending()
  ↓
Database cleanup
  ↓
Logging & status
```

**Rationale**: Keep logic in ScheduleManager (testable, reusable). Daily script just handles invocation context.

---

## Implementation

### Main Script

```python
#!/usr/bin/env python3
"""
Daily maintenance script for BFI IMAX listing scraper

Usage:
    python -m dynamicalsystem.listing.maintenance.daily [--dry-run] [--verbose]

Exit codes:
    0: Success
    1: Partial failure (some dates failed)
    2: Critical failure (horizon scan failed, database error)
"""

import sys
import logging
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from dynamicalsystem.listing.scraper.fetch import BFIFetcher
from dynamicalsystem.listing.scraper.runtime import RuntimeFetcher
from dynamicalsystem.listing.scraper.schedule import ScheduleManager
from dynamicalsystem.listing.storage.db import Database
from dynamicalsystem.listing.config import Config


def setup_logging(verbose: bool = False):
    """Configure logging for daily maintenance"""
    level = logging.DEBUG if verbose else logging.INFO

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)

    # File handler (rotated daily)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        Config.LOG_FILE,
        when='midnight',
        interval=1,
        backupCount=30,  # Keep 30 days
        utc=True
    )
    file_handler.setLevel(logging.DEBUG)

    # Format
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )
    console.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)


def main():
    """Main entry point for daily maintenance"""
    parser = argparse.ArgumentParser(description='BFI IMAX daily maintenance')
    parser.add_argument('--dry-run', action='store_true',
                       help='Simulate run without making changes')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable debug logging')
    parser.add_argument('--db-path', default=Config.DB_PATH,
                       help='Path to SQLite database')
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("BFI IMAX Daily Maintenance Starting")
    logger.info(f"Time: {datetime.now(ZoneInfo('UTC')).isoformat()}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)

    exit_code = 0

    try:
        # Initialize components
        db = Database(args.db_path)
        fetcher = BFIFetcher()
        runtime_fetcher = RuntimeFetcher()
        manager = ScheduleManager(db, fetcher, runtime_fetcher)

        # Validate database
        if not db.validate_schema():
            logger.error("Database schema validation failed")
            return 2

        # Run scrape
        if args.dry_run:
            logger.info("DRY RUN: Would execute scrape_all_pending()")
            summary = simulate_scrape_run(manager)
        else:
            summary = manager.scrape_all_pending()

        # Log summary
        log_summary(summary)

        # Determine exit code
        if summary.errors:
            if len(summary.errors) >= summary.dates_scraped / 2:
                # More than half failed - critical
                exit_code = 2
                logger.error("Critical: More than 50% of scrapes failed")
            else:
                # Some failed - partial
                exit_code = 1
                logger.warning("Partial failure: Some scrapes failed")
        else:
            exit_code = 0
            logger.info("Success: All scrapes completed")

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        exit_code = 130

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        exit_code = 2

    finally:
        if 'db' in locals():
            db.close()

        logger.info("=" * 60)
        logger.info(f"Daily Maintenance Complete (exit code: {exit_code})")
        logger.info("=" * 60)

    return exit_code


def log_summary(summary):
    """Log scrape run summary in structured format"""
    logger = logging.getLogger(__name__)

    logger.info("")
    logger.info("Scrape Run Summary")
    logger.info("-" * 60)
    logger.info(f"Started:          {summary.started_at}")
    logger.info(f"Completed:        {summary.completed_at}")
    logger.info(f"Duration:         {summary.duration_seconds:.1f}s")
    logger.info(f"Dates scraped:    {summary.dates_scraped}")
    logger.info(f"New dates found:  {summary.new_dates_found}")
    logger.info(f"Changes detected: {summary.changes_detected}")
    logger.info(f"Errors:           {len(summary.errors)}")

    if summary.errors:
        logger.warning("")
        logger.warning("Errors encountered:")
        for error in summary.errors:
            logger.warning(f"  - {error}")

    logger.info("-" * 60)
    logger.info("")


def simulate_scrape_run(manager):
    """Simulate scrape run for dry-run mode"""
    logger = logging.getLogger(__name__)

    # Get what would be scraped
    dates = manager.get_dates_to_scrape()

    logger.info(f"Would scrape {len(dates)} dates:")
    for date in dates[:10]:  # Show first 10
        status = manager.db.get_status(date)
        logger.info(f"  - {date} (status: {status})")

    if len(dates) > 10:
        logger.info(f"  ... and {len(dates) - 10} more")

    # Return mock summary
    from dynamicalsystem.listing.scraper.schedule import ScrapeRunSummary
    return ScrapeRunSummary(
        started_at=datetime.now(ZoneInfo('UTC')).isoformat(),
        completed_at=datetime.now(ZoneInfo('UTC')).isoformat(),
        duration_seconds=0,
        dates_scraped=len(dates),
        new_dates_found=0,
        changes_detected=0,
        errors=[]
    )


if __name__ == '__main__':
    sys.exit(main())
```

---

## Cron Configuration

### Docker Container Setup

**Dockerfile additions**:
```dockerfile
FROM python:3.11-slim

# Install cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# Copy application
COPY . /app
WORKDIR /app

# Install Python dependencies
RUN pip install -e .

# Setup cron job
COPY docker/crontab /etc/cron.d/listing-maintenance
RUN chmod 0644 /etc/cron.d/listing-maintenance && \
    crontab /etc/cron.d/listing-maintenance

# Create log directory
RUN mkdir -p /var/log/listing && \
    touch /var/log/listing/daily.log && \
    chmod 666 /var/log/listing/daily.log

# Startup script
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
```

**docker/crontab**:
```cron
# BFI IMAX Daily Maintenance
# Runs at 02:00 UTC (03:00 BST / 02:00 GMT)
0 2 * * * cd /app && /usr/local/bin/python -m dynamicalsystem.listing.maintenance.daily >> /var/log/listing/cron.log 2>&1
```

**docker/entrypoint.sh**:
```bash
#!/bin/bash
set -e

# Start cron in background
cron

# Start Go web server in foreground
exec /app/webserver
```

---

## Configuration

### Settings

```python
# src/dynamicalsystem/listing/config.py

import os

class Config:
    # Database
    DB_PATH = os.getenv('LISTING_DB_PATH', '/data/listing.db')

    # Logging
    LOG_FILE = os.getenv('LISTING_LOG_FILE', '/var/log/listing/daily.log')
    LOG_LEVEL = os.getenv('LISTING_LOG_LEVEL', 'INFO')

    # Maintenance schedule
    MAINTENANCE_HOUR = int(os.getenv('LISTING_MAINTENANCE_HOUR', '2'))  # 02:00 UTC

    # Alert thresholds
    MAX_ERROR_RATE = float(os.getenv('LISTING_MAX_ERROR_RATE', '0.5'))  # 50%

    # External services
    TMDB_API_KEY = os.getenv('TMDB_API_KEY', None)
```

---

## Monitoring & Alerting

### Health Endpoint Integration

The Go web server provides a health endpoint that checks:
- Last successful scrape timestamp
- Error rate from last run
- Database connectivity

```go
// In Go web server (future design)

type HealthInfo struct {
    Status           string    `json:"status"`            // "healthy", "degraded", "unhealthy"
    LastScrape       time.Time `json:"last_scrape"`
    LastScrapeStatus string    `json:"last_scrape_status"` // "success", "partial", "failed"
    ListingsCount    int       `json:"listings_count"`
    ErrorCount       int       `json:"error_count"`
    OldestListing    string    `json:"oldest_listing"`
    NewestListing    string    `json:"newest_listing"`
}

func GetHealthInfo(db *sql.DB) (HealthInfo, error) {
    // Query database for health indicators
    // Read last scrape from scrape_schedule
    // Count current listings
    // etc.
}
```

### External Monitoring

**Example: Healthchecks.io integration**:
```python
import requests

def ping_healthcheck(success: bool):
    """Ping healthchecks.io after scrape run"""
    url = Config.HEALTHCHECK_URL
    if not url:
        return

    if success:
        requests.get(url, timeout=10)
    else:
        requests.get(f"{url}/fail", timeout=10)
```

**Usage in main()**:
```python
def main():
    # ... run scrape ...

    success = exit_code == 0
    ping_healthcheck(success)

    return exit_code
```

---

## Manual Invocation

### Command-Line Usage

```bash
# Normal run
python -m dynamicalsystem.listing.maintenance.daily

# Dry run (no changes)
python -m dynamicalsystem.listing.maintenance.daily --dry-run

# Verbose logging
python -m dynamicalsystem.listing.maintenance.daily --verbose

# Custom database
python -m dynamicalsystem.listing.maintenance.daily --db-path /tmp/test.db
```

### Docker Exec

```bash
# Run manually inside container
docker exec listing-scraper python -m dynamicalsystem.listing.maintenance.daily --verbose

# Dry run
docker exec listing-scraper python -m dynamicalsystem.listing.maintenance.daily --dry-run

# Check logs
docker exec listing-scraper tail -f /var/log/listing/daily.log
```

---

## Error Handling

### Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Continue normal operation |
| 1 | Partial failure | Alert but continue |
| 2 | Critical failure | Alert immediately, investigate |
| 130 | Interrupted (SIGINT) | Normal shutdown |

### Retry Strategy

**Automatic retry via cron**:
- If exit code != 0, cron continues (doesn't stop on failure)
- Next scheduled run (tomorrow 02:00) will retry
- Persistent failures detected via health endpoint

**Manual retry**:
```bash
# If today's run failed, manually re-run
docker exec listing-scraper python -m dynamicalsystem.listing.maintenance.daily
```

---

## Logging

### Log Levels

```python
# DEBUG: Detailed flow
logger.debug(f"Fetching date: {date}")

# INFO: Important events
logger.info("Starting daily maintenance")
logger.info(f"Scraped {count} dates")

# WARNING: Recoverable issues
logger.warning(f"Fetch retry #{attempt}: {date}")
logger.warning("Partial failure: 3 of 15 dates failed")

# ERROR: Unrecoverable issues
logger.error(f"Failed to fetch {date}: {error}")
logger.error("Database connection lost", exc_info=True)
```

### Log Rotation

```python
# TimedRotatingFileHandler configuration
handler = logging.handlers.TimedRotatingFileHandler(
    '/var/log/listing/daily.log',
    when='midnight',    # Rotate at midnight UTC
    interval=1,         # Every 1 day
    backupCount=30,     # Keep 30 days
    utc=True           # Use UTC
)
```

**Result**: Logs rotated daily, 30-day retention
- `daily.log` (today)
- `daily.log.2025-10-25` (yesterday)
- `daily.log.2025-10-24` (2 days ago)
- ...

---

## Testing

### Unit Tests

```python
def test_main_success(mock_manager, capsys):
    """Test successful run"""
    mock_manager.scrape_all_pending.return_value = ScrapeRunSummary(
        started_at='2025-10-26T02:00:00+00:00',
        completed_at='2025-10-26T02:05:00+00:00',
        duration_seconds=300,
        dates_scraped=15,
        new_dates_found=2,
        changes_detected=5,
        errors=[]
    )

    exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Success" in output
    assert "15" in output  # dates scraped

def test_main_partial_failure(mock_manager):
    """Test partial failure (some errors)"""
    mock_manager.scrape_all_pending.return_value = ScrapeRunSummary(
        started_at='2025-10-26T02:00:00+00:00',
        completed_at='2025-10-26T02:05:00+00:00',
        duration_seconds=300,
        dates_scraped=15,
        new_dates_found=2,
        changes_detected=5,
        errors=['2025-10-26: fetch_failed', '2025-10-27: network_error']
    )

    exit_code = main()

    assert exit_code == 1  # Partial failure

def test_main_critical_failure(mock_manager):
    """Test critical failure (>50% errors)"""
    mock_manager.scrape_all_pending.return_value = ScrapeRunSummary(
        started_at='2025-10-26T02:00:00+00:00',
        completed_at='2025-10-26T02:05:00+00:00',
        duration_seconds=300,
        dates_scraped=10,
        new_dates_found=0,
        changes_detected=0,
        errors=['error'] * 6  # 6 out of 10 failed
    )

    exit_code = main()

    assert exit_code == 2  # Critical failure

def test_dry_run_mode(mock_manager, capsys):
    """Test dry-run doesn't make changes"""
    exit_code = main(['--dry-run'])

    assert exit_code == 0
    assert not mock_manager.scrape_all_pending.called
    output = capsys.readouterr().out
    assert "DRY RUN" in output
```

### Integration Tests

```python
def test_full_daily_run_integration(temp_db):
    """Test complete daily run against real database"""
    # Setup test database
    db = Database(temp_db)
    db.init_schema()

    # Add some dates to scrape_schedule
    db.add_to_scrape_schedule('2025-10-26', 'unknown')
    db.add_to_scrape_schedule('2025-10-27', 'partial')

    # Mock BFI responses
    with patch('dynamicalsystem.listing.scraper.fetch.BFIFetcher') as mock_fetcher:
        mock_fetcher.return_value.fetch.side_effect = [
            load_fixture('horizon_scan.html'),
            load_fixture('oct26_showings.html'),
            load_fixture('oct27_no_results.html')
        ]

        # Run maintenance
        exit_code = main(['--db-path', temp_db])

        assert exit_code == 0

        # Verify database updated
        showings = db.get_all_listings()
        assert len(showings) > 0

        # Verify snapshots recorded
        snapshots = db.get_all_snapshots()
        assert len(snapshots) >= 2
```

---

## Deployment

### Docker Compose

```yaml
version: '3.8'

services:
  listing-scraper:
    build: .
    container_name: listing-scraper
    restart: unless-stopped

    environment:
      - LISTING_DB_PATH=/data/listing.db
      - LISTING_LOG_FILE=/var/log/listing/daily.log
      - LISTING_LOG_LEVEL=INFO
      - TMDB_API_KEY=${TMDB_API_KEY}
      - HEALTHCHECK_URL=${HEALTHCHECK_URL}
      - TZ=UTC

    volumes:
      - ./data:/data              # Database persistence
      - ./logs:/var/log/listing   # Log persistence

    ports:
      - "8080:8080"  # Web server

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 5m
      timeout: 10s
      retries: 3
      start_period: 30s
```

### Environment Variables

```bash
# .env file
LISTING_DB_PATH=/data/listing.db
LISTING_LOG_FILE=/var/log/listing/daily.log
LISTING_LOG_LEVEL=INFO
TMDB_API_KEY=your_api_key_here
HEALTHCHECK_URL=https://hc-ping.com/your-uuid
```

---

## Operational Procedures

### Initial Deployment

```bash
# 1. Build container
docker-compose build

# 2. Initialize database
docker-compose run --rm listing-scraper python -m dynamicalsystem.listing.storage.db init

# 3. Test dry-run
docker-compose run --rm listing-scraper python -m dynamicalsystem.listing.maintenance.daily --dry-run

# 4. First real run (verbose)
docker-compose run --rm listing-scraper python -m dynamicalsystem.listing.maintenance.daily --verbose

# 5. Start container (cron + web server)
docker-compose up -d

# 6. Verify cron is running
docker exec listing-scraper crontab -l
```

### Monitoring

```bash
# Check recent logs
docker exec listing-scraper tail -100 /var/log/listing/daily.log

# Check health endpoint
curl http://localhost:8080/health | jq

# Check database stats
docker exec listing-scraper sqlite3 /data/listing.db "SELECT status, COUNT(*) FROM scrape_schedule GROUP BY status"
```

### Troubleshooting

```bash
# If scrape failed, check logs
docker exec listing-scraper grep ERROR /var/log/listing/daily.log

# Check database integrity
docker exec listing-scraper sqlite3 /data/listing.db "PRAGMA integrity_check"

# Manual re-run with verbose output
docker exec listing-scraper python -m dynamicalsystem.listing.maintenance.daily --verbose

# Check cron execution
docker exec listing-scraper grep cron /var/log/syslog
```

---

## Future Enhancements

### 1. Notification System

```python
def send_alert(summary: ScrapeRunSummary):
    """Send alert on failure (email, Slack, etc.)"""
    if len(summary.errors) > 0:
        subject = f"BFI IMAX Scraper: {len(summary.errors)} errors"
        body = format_error_report(summary)
        send_email(Config.ALERT_EMAIL, subject, body)
```

### 2. Metrics Export

```python
def export_metrics(summary: ScrapeRunSummary):
    """Export metrics to Prometheus/CloudWatch"""
    metrics = {
        'scrape_duration_seconds': summary.duration_seconds,
        'dates_scraped_total': summary.dates_scraped,
        'changes_detected_total': summary.changes_detected,
        'errors_total': len(summary.errors)
    }
    # Push to metrics service
```

### 3. Concurrent Scraping

```python
# Use ThreadPoolExecutor for parallel date scraping
def scrape_all_pending_concurrent(self, max_workers: int = 3):
    """Scrape multiple dates concurrently"""
    dates = self.get_dates_to_scrape()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(self.scrape_date, date): date for date in dates}
        # ...
```

---

## Success Criteria

Daily maintenance is successful if:

- [ ] Runs automatically at 02:00 UTC daily
- [ ] Completes in <10 minutes for typical load
- [ ] Logs all activities (info + errors)
- [ ] Exit code reflects success/failure accurately
- [ ] Database always in consistent state (even on crashes)
- [ ] Can be run manually for testing/recovery
- [ ] Health endpoint reflects scrape status
- [ ] Survives container restarts

---

## Next Steps

1. [ ] **Review**: Simon reviews design
2. [ ] **Implement**: Main script (`daily.py`)
3. [ ] **Implement**: Logging setup
4. [ ] **Implement**: Docker configuration
5. [ ] **Test**: Manual invocation
6. [ ] **Test**: Dry-run mode
7. [ ] **Test**: Integration with ScheduleManager
8. [ ] **Document**: Update decision.md

---

## Related Documents

- [Schedule Manager](./schedule-manager-design.md) - Core scraping logic
- [SQLite Schema](./sqlite-schema-design.md) - Database structure
- [Outcomes](../outcomes.md) - Outcome 3: Daily Maintenance requirements
- [Decision](../decision.md) - Deployment decisions (Docker + cron)
