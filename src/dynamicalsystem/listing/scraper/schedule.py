"""Schedule manager for orchestrating BFI IMAX listing scraping.

Manages the lifecycle of date scraping:
1. Discover dates with showings (horizon scan)
2. Track scrape state for each date (scrape_schedule table)
3. Decide which dates need re-scraping
4. Detect and record schedule changes
5. Determine when dates are "complete"

Design: Simplified from original 5-tier priority to binary filter
(all dates - complete dates), per design decision 2025-10-26.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import List, Optional, Set

from dynamicalsystem.listing.scraper.changes import Change, ChangeDetector, compute_snapshot_hash
from dynamicalsystem.listing.scraper.completion import CompletionChecker
from dynamicalsystem.listing.scraper.fetch import BFIFetcher
from dynamicalsystem.listing.scraper.parse import extract_performance_days, parse_search_results, has_results
from dynamicalsystem.listing.scraper.runtime import RuntimeFetcher
from dynamicalsystem.listing.storage.db import Database


logger = logging.getLogger(__name__)


@dataclass
class HorizonScanResult:
    """Result of horizon scan operation."""
    dates_discovered: Set[str]
    new_dates: Set[str]
    removed_dates: Set[str]


@dataclass
class ScrapeDateResult:
    """Result of scraping a single date."""
    date: str
    showing_count: int
    changes_detected: List[Change]
    is_complete: bool
    status: str  # 'empty', 'partial', 'complete', 'error'
    error: Optional[str] = None


class ScheduleManager:
    """Orchestrates scraping lifecycle.

    Delegates to ChangeDetector and CompletionChecker for specific tasks.

    Example:
        manager = ScheduleManager(db, fetcher, runtime_fetcher, change_detector, completion_checker)

        # Daily workflow
        manager.update_horizon()
        for date in manager.get_dates_to_scrape():
            result = manager.scrape_date(date)
            time.sleep(1)  # Rate limiting
    """

    def __init__(
        self,
        db: Database,
        fetcher: BFIFetcher,
        runtime_fetcher: RuntimeFetcher,
        change_detector: ChangeDetector,
        completion_checker: CompletionChecker
    ):
        """Initialize schedule manager.

        Args:
            db: Database instance
            fetcher: BFIFetcher for retrieving HTML pages
            runtime_fetcher: RuntimeFetcher for film runtimes
            change_detector: ChangeDetector for snapshot comparison
            completion_checker: CompletionChecker for gap analysis
        """
        self.db = db
        self.fetcher = fetcher
        self.runtime_fetcher = runtime_fetcher
        self.change_detector = change_detector
        self.completion_checker = completion_checker

    def _transform_parser_output(self, showings: List[dict]) -> List[dict]:
        """Transform parser output to database format.

        Adds missing database fields with defaults.

        Args:
            showings: List of showings from parser

        Returns:
            List of showings with database field names
        """
        transformed = []
        for showing in showings:
            # Add missing database fields with defaults
            showing.setdefault('showing_datetime_utc', showing.get('showing_datetime', ''))
            showing.setdefault('showing_datetime_display', showing.get('showing_datetime', ''))
            showing.setdefault('detail_url_full', '')
            showing.setdefault('is_3d', False)
            showing.setdefault('is_70mm', False)
            showing.setdefault('is_laser', False)
            showing.setdefault('has_subtitles', False)

            transformed.append(showing)

        return transformed

    def update_horizon(self) -> HorizonScanResult:
        """Scan horizon to discover all dates with showings.

        Uses performanceDays array to discover dates in single request.

        Returns:
            HorizonScanResult with discovered/new/removed dates
        """
        logger.info("Starting horizon scan")

        # Fetch today's page to get performanceDays. Late in the day (or when
        # today has no showings) BFI serves a no-results page without the
        # performanceDays array, so fall back to tomorrow's page.
        today = datetime.now(UTC).date()
        dates_with_showings = set()
        for offset in (0, 1):
            fetch_date = (today + timedelta(days=offset)).isoformat()
            html = self.fetcher.fetch(fetch_date)
            if not html:
                logger.error(f"Horizon scan: could not fetch page for {fetch_date}")
                continue
            dates_with_showings = extract_performance_days(html)
            if dates_with_showings:
                break
            logger.warning(f"No performanceDays on page for {fetch_date}")

        if not dates_with_showings:
            # A genuinely empty horizon is implausible; treat as a failed scan
            # rather than marking every tracked date as removed.
            logger.error("Horizon scan failed: no dates found; skipping removal checks")
            return HorizonScanResult(
                dates_discovered=set(),
                new_dates=set(),
                removed_dates=set()
            )

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
                    first_seen=datetime.now(UTC).isoformat()
                )

        # Identify removed dates (no longer in horizon)
        # Only check dates that were previously 'partial' or 'unknown'
        tracked_dates = self.db.get_dates_by_status(['partial', 'unknown'])
        removed_dates = tracked_dates - dates_with_showings

        if removed_dates:
            # Dates disappeared from horizon - verify and mark
            logger.warning(f"Dates removed from horizon: {sorted(removed_dates)}")
            for date in removed_dates:
                self._verify_and_mark_removed(date)

        return HorizonScanResult(
            dates_discovered=dates_with_showings,
            new_dates=new_dates,
            removed_dates=removed_dates
        )

    def _verify_and_mark_removed(self, date: str):
        """Verify date is truly empty before marking removed.

        Sometimes dates briefly disappear from performanceDays during updates.

        Args:
            date: Date to verify
        """
        logger.info(f"Verifying removed date: {date}")

        # Direct fetch to confirm
        html = self.fetcher.fetch(date)
        has_showings = has_results(html) if html else False

        if not has_showings:
            # Confirmed empty
            logger.info(f"Confirmed empty: {date}")
            self.db.update_scrape_schedule(
                date=date,
                status='empty',
                showing_count=0,
                last_checked=datetime.now(UTC).isoformat()
            )
        else:
            # Still has showings, horizon scan was stale
            logger.warning(f"Date {date} still has showings, horizon was stale")
            # Schedule will be scraped on next run

    def get_dates_to_scrape(self) -> List[str]:
        """Get list of dates to scrape today.

        Simple binary filter:
        1. Get all dates with showings (from horizon scan)
        2. Exclude dates marked 'complete'
        3. Scrape everything else

        Returns:
            List of dates (YYYY-MM-DD) to scrape, sorted
        """
        # Get all dates with showings from most recent horizon scan
        dates_with_showings = self.db.get_all_scheduled_dates()

        # Get dates marked complete
        complete_dates = self.db.get_dates_by_status(['complete'])

        # Dates to scrape = dates with showings - complete dates
        dates_to_scrape = sorted(dates_with_showings - complete_dates)

        logger.info(
            f"Dates to scrape: {len(dates_to_scrape)} "
            f"(total: {len(dates_with_showings)}, complete: {len(complete_dates)})"
        )

        return dates_to_scrape

    def scrape_date(self, date: str) -> ScrapeDateResult:
        """Scrape single date with full change detection.

        Steps:
        1. Fetch HTML for date
        2. Parse showings
        3. Detect changes (ChangeDetector)
        4. Record new snapshot
        5. Update listings table
        6. Determine completion status (CompletionChecker)
        7. Update scrape_schedule

        Args:
            date: Date to scrape (YYYY-MM-DD)

        Returns:
            ScrapeDateResult with status and changes
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

        # 2.5. Transform parser output to database format
        showings = self._transform_parser_output(showings)

        if showing_count == 0:
            # No showings found
            self.db.update_scrape_schedule(
                date=date,
                status='empty',
                showing_count=0,
                last_checked=datetime.now(UTC).isoformat()
            )
            return ScrapeDateResult(
                date=date,
                showing_count=0,
                changes_detected=[],
                is_complete=True,
                status='empty'
            )

        # 3. Detect changes (ChangeDetector fetches previous snapshot)
        changes = self.change_detector.detect_changes(date, showings)
        logger.info(f"Detected {len(changes)} changes for {date}")

        # 4. Record new snapshot (hash computed internally)
        snapshot_hash = compute_snapshot_hash(showings)
        snapshot_id = self.db.record_snapshot(
            date=date,
            showings=showings,
            is_complete=False  # Will be updated in step 8
        )

        # 5. Update listings table
        self.db.upsert_showings(showings)

        # 6. Record changes
        if changes:
            for change in changes:
                self.db.record_change(change, snapshot_id)

        # 7. Determine completion (CompletionChecker handles runtime fetching)
        is_complete = self.completion_checker.is_complete(date, showings)

        # 8. Update scrape_schedule
        status = 'complete' if is_complete else 'partial'
        self.db.update_scrape_schedule(
            date=date,
            status=status,
            showing_count=showing_count,
            is_complete=is_complete,
            last_scraped=datetime.now(UTC).isoformat(),
            snapshot_hash=snapshot_hash
        )

        return ScrapeDateResult(
            date=date,
            showing_count=showing_count,
            changes_detected=changes,
            is_complete=is_complete,
            status=status
        )
