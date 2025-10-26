#!/usr/bin/env python3
"""Daily maintenance script for BFI IMAX listing scraper.

Usage:
    python -m dynamicalsystem.listing.maintenance.daily [--dry-run] [--verbose]

Exit codes:
    0: Success
    1: Partial failure (some dates failed)
    2: Critical failure (horizon scan failed, database error)
"""

import sys
import logging
import logging.handlers
import argparse
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from typing import List

from dynamicalsystem.listing.scraper.fetch import BFIFetcher
from dynamicalsystem.listing.scraper.runtime import RuntimeFetcher
from dynamicalsystem.listing.scraper.schedule import ScheduleManager
from dynamicalsystem.listing.scraper.changes import ChangeDetector
from dynamicalsystem.listing.scraper.completion import CompletionChecker
from dynamicalsystem.listing.storage.db import Database
from dynamicalsystem.listing.config import Config


@dataclass
class ScrapeRunSummary:
    """Summary of a daily scrape run."""
    started_at: str
    completed_at: str = ""
    duration_seconds: float = 0.0
    dates_scraped: int = 0
    new_dates_found: int = 0
    changes_detected: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def setup_logging(verbose: bool = False, log_file: str = None):
    """Configure logging for daily maintenance.

    Args:
        verbose: Enable debug logging
        log_file: Path to log file (None = no file logging)
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)

    # Format
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )
    console.setFormatter(formatter)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)

    # File handler (if log file specified)
    if log_file:
        try:
            # Ensure log directory exists
            import os
            os.makedirs(os.path.dirname(log_file), exist_ok=True)

            file_handler = logging.handlers.TimedRotatingFileHandler(
                log_file,
                when='midnight',
                interval=1,
                backupCount=30,  # Keep 30 days
                utc=True
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except (OSError, PermissionError) as e:
            logging.warning(f"Could not setup file logging: {e}")


def log_summary(summary: ScrapeRunSummary):
    """Log scrape run summary in structured format.

    Args:
        summary: Summary of the scrape run
    """
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


def ping_healthcheck(success: bool):
    """Ping healthchecks.io after scrape run.

    Args:
        success: True if scrape succeeded, False otherwise
    """
    url = Config.HEALTHCHECK_URL
    if not url:
        return

    try:
        import requests
        if success:
            requests.get(url, timeout=10)
        else:
            requests.get(f"{url}/fail", timeout=10)
    except Exception as e:
        logging.warning(f"Failed to ping healthcheck: {e}")


def run_daily_maintenance(dry_run: bool = False) -> ScrapeRunSummary:
    """Execute daily scrape run.

    Args:
        dry_run: If True, simulate run without making changes

    Returns:
        Summary of the scrape run
    """
    logger = logging.getLogger(__name__)
    start_time = datetime.now(ZoneInfo("UTC"))

    summary = ScrapeRunSummary(
        started_at=start_time.isoformat(),
        dates_scraped=0,
        new_dates_found=0,
        changes_detected=0,
        errors=[]
    )

    # Initialize components
    db = Database(Config.DB_PATH)
    fetcher = BFIFetcher()
    runtime_fetcher = RuntimeFetcher(db=db)
    change_detector = ChangeDetector(db=db)
    completion_checker = CompletionChecker(runtime_fetcher=runtime_fetcher)
    manager = ScheduleManager(
        db=db,
        fetcher=fetcher,
        runtime_fetcher=runtime_fetcher,
        change_detector=change_detector,
        completion_checker=completion_checker
    )

    try:
        # 1. Horizon scan
        logger.info("Starting horizon scan...")
        horizon_result = manager.update_horizon()
        summary.new_dates_found = len(horizon_result.new_dates)
        logger.info(f"Horizon scan complete: {summary.new_dates_found} new dates discovered")

        if horizon_result.new_dates:
            logger.info(f"New dates: {sorted(list(horizon_result.new_dates))[:5]}...")

    except Exception as e:
        logger.error(f"Horizon scan failed: {e}", exc_info=True)
        summary.errors.append(f"horizon_scan: {e}")
        # Continue with scraping known dates

    # 2. Get dates to scrape
    dates_to_scrape = manager.get_dates_to_scrape()
    logger.info(f"Found {len(dates_to_scrape)} dates to scrape")

    if dry_run:
        logger.info("DRY RUN: Would scrape the following dates:")
        for date in dates_to_scrape[:10]:
            status = db.get_schedule_status(date)
            logger.info(f"  - {date} (status: {status})")
        if len(dates_to_scrape) > 10:
            logger.info(f"  ... and {len(dates_to_scrape) - 10} more")
        summary.dates_scraped = len(dates_to_scrape)
        return summary

    # 3. Scrape each date
    for date in dates_to_scrape:
        try:
            logger.info(f"Scraping date: {date}")
            result = manager.scrape_date(date)
            summary.dates_scraped += 1
            summary.changes_detected += len(result.changes_detected)

            logger.info(f"  {date}: {result.showing_count} showings, "
                       f"{len(result.changes_detected)} changes, "
                       f"status={result.status}")

            # Rate limiting: 1 second between requests
            time.sleep(1)

        except Exception as e:
            logger.error(f"Failed to scrape {date}: {e}", exc_info=True)
            summary.errors.append(f"{date}: {e}")
            continue

    # 4. Cleanup old data
    try:
        logger.info("Cleaning up old data...")
        deleted_listings = db.delete_old_listings()
        deleted_snapshots = db.delete_old_snapshots()
        logger.info(f"Cleanup complete: {deleted_listings} old listings, "
                   f"{deleted_snapshots} old snapshots deleted")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        summary.errors.append(f"cleanup: {e}")

    # 5. Finalize summary
    end_time = datetime.now(ZoneInfo("UTC"))
    summary.completed_at = end_time.isoformat()
    summary.duration_seconds = (end_time - start_time).total_seconds()

    return summary


def main(argv=None):
    """Main entry point for daily maintenance.

    Args:
        argv: Command-line arguments (None = sys.argv)

    Returns:
        Exit code (0=success, 1=partial failure, 2=critical failure)
    """
    parser = argparse.ArgumentParser(description='BFI IMAX daily maintenance')
    parser.add_argument('--dry-run', action='store_true',
                       help='Simulate run without making changes')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable debug logging')
    parser.add_argument('--db-path', default=Config.DB_PATH,
                       help='Path to SQLite database')
    parser.add_argument('--log-file', default=Config.LOG_FILE,
                       help='Path to log file (omit for console only)')
    args = parser.parse_args(argv)

    # Update config from args
    if args.db_path:
        Config.DB_PATH = args.db_path

    setup_logging(args.verbose, args.log_file if not args.dry_run else None)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("BFI IMAX Daily Maintenance Starting")
    logger.info(f"Time: {datetime.now(ZoneInfo('UTC')).isoformat()}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Database: {Config.DB_PATH}")
    logger.info("=" * 60)

    exit_code = 0

    try:
        # Validate configuration
        if not Config.validate():
            logger.error("Configuration validation failed")
            return 2

        # Run maintenance
        summary = run_daily_maintenance(dry_run=args.dry_run)

        # Log summary
        log_summary(summary)

        # Determine exit code
        if summary.errors:
            error_rate = len(summary.errors) / max(summary.dates_scraped, 1)
            if error_rate >= Config.MAX_ERROR_RATE:
                # More than 50% failed - critical
                exit_code = 2
                logger.error(f"Critical: {error_rate:.0%} of scrapes failed")
            else:
                # Some failed - partial
                exit_code = 1
                logger.warning(f"Partial failure: {len(summary.errors)} errors")
        else:
            exit_code = 0
            logger.info("Success: All scrapes completed")

        # Ping healthcheck
        if not args.dry_run:
            ping_healthcheck(exit_code == 0)

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        exit_code = 130

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        exit_code = 2
        if not args.dry_run:
            ping_healthcheck(False)

    finally:
        logger.info("=" * 60)
        logger.info(f"Daily Maintenance Complete (exit code: {exit_code})")
        logger.info("=" * 60)

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
