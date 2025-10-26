"""Schedule completion detection using runtime-based gap modeling.

Determines if a date's schedule is complete by modeling time slots with
film runtimes and checking for gaps that could fit additional showings.

Design: Pure function of (showings + runtimes), no external state.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from dynamicalsystem.listing.scraper.runtime import RuntimeFetcher


logger = logging.getLogger(__name__)


class CompletionConfig:
    """Configuration for completion detection."""

    # Slot overhead: ads (25min) + changeover (15min)
    SLOT_OVERHEAD_MINUTES = 40

    # Minimum gap that could fit another showing
    # (shortest film ~90min + overhead = 130min, use 150min for safety)
    MIN_SLOT_GAP_MINUTES = 150

    # Operating hours (UK local time)
    CINEMA_TYPICAL_OPEN = 10   # 10:00
    CINEMA_TYPICAL_CLOSE = 23  # 23:00
    LATE_START_HOUR = 11       # If first showing after 11:00, might add morning
    EARLY_END_HOUR = 22        # If last showing ends before 22:00, might add evening


class CompletionChecker:
    """Determines if a date's schedule is complete.

    Uses runtime-based gap modeling to detect if there's room for
    additional showings in the schedule.

    Algorithm:
    1. Get runtime for each film
    2. Model time slots (runtime + ads + changeover)
    3. Check for gaps >= 150min between showings
    4. Consider operating hours (10:00-23:00 typical)

    Example:
        checker = CompletionChecker(runtime_fetcher, config)
        is_complete = checker.is_complete('2025-10-26', showings)
    """

    def __init__(
        self,
        runtime_fetcher: RuntimeFetcher,
        config: CompletionConfig = None
    ):
        """Initialize completion checker.

        Args:
            runtime_fetcher: RuntimeFetcher instance for getting film runtimes
            config: CompletionConfig with thresholds (uses defaults if None)
        """
        self.runtime_fetcher = runtime_fetcher
        self.config = config or CompletionConfig()

    def is_complete(self, date: str, showings: List[Dict]) -> bool:
        """Check if schedule is complete using runtime-based modeling.

        Args:
            date: Date to check (YYYY-MM-DD)
            showings: List of showing dictionaries

        Returns:
            True if complete, False if partial
        """
        if not showings:
            # Empty day is "complete" (no showings = nothing to add)
            logger.debug(f"Date {date} is empty, marking complete")
            return True

        # Get runtimes for all films
        runtimes = {}
        missing_runtimes = []

        for showing in showings:
            movie_title = showing.get('movie_title', '')
            runtime = self.runtime_fetcher.get_runtime(movie_title)

            if runtime:
                runtimes[showing['bfi_showing_id']] = runtime
            else:
                missing_runtimes.append(movie_title)

        # If we're missing runtimes, can't model definitively
        if missing_runtimes:
            logger.warning(
                f"Missing runtimes for {date}, cannot determine completion: "
                f"{missing_runtimes}"
            )
            return False  # Assume incomplete until we have runtimes

        # Model the schedule
        logger.debug(f"Modeling schedule for {date} with {len(showings)} showings")
        return self._check_schedule_gaps(date, showings, runtimes)

    def _check_schedule_gaps(
        self,
        date: str,
        showings: List[Dict],
        runtimes: Dict[str, int]
    ) -> bool:
        """Check for gaps in schedule that could fit another showing.

        Args:
            date: Date being checked
            showings: List of showings
            runtimes: Dict of showing_id -> runtime_minutes

        Returns:
            True if no gaps found (complete), False if gaps exist (partial)
        """
        # Sort showings by time
        showings_sorted = sorted(
            showings,
            key=lambda x: x.get('showing_time', '00:00')
        )

        # Check gaps between consecutive showings
        for i in range(len(showings_sorted) - 1):
            current = showings_sorted[i]
            next_showing = showings_sorted[i + 1]

            # Get runtime for current showing
            runtime = runtimes.get(current['bfi_showing_id'])
            if not runtime:
                # This shouldn't happen (we checked earlier), but be safe
                logger.warning(f"Missing runtime for {current['bfi_showing_id']}")
                return False

            # Parse times
            current_time_str = current.get('showing_time', '00:00')
            next_time_str = next_showing.get('showing_time', '00:00')

            try:
                current_time = datetime.strptime(current_time_str, '%H:%M').time()
                next_time = datetime.strptime(next_time_str, '%H:%M').time()
            except ValueError as e:
                logger.error(f"Failed to parse times: {current_time_str}, {next_time_str}: {e}")
                return False

            # Calculate end time of current showing
            current_dt = datetime.combine(datetime.today(), current_time)
            end_dt = current_dt + timedelta(
                minutes=runtime + self.config.SLOT_OVERHEAD_MINUTES
            )

            # Calculate gap to next showing
            next_dt = datetime.combine(datetime.today(), next_time)
            gap_minutes = (next_dt - end_dt).total_seconds() / 60

            if gap_minutes >= self.config.MIN_SLOT_GAP_MINUTES:
                logger.info(
                    f"Large gap detected on {date}: {gap_minutes:.0f}min "
                    f"after {current_time_str} ({current.get('movie_title')})"
                )
                return False  # Room for another showing

        # Check operating hours
        if not self._check_operating_hours(date, showings_sorted, runtimes):
            return False

        # Day appears complete
        logger.info(
            f"Day {date} appears complete: {len(showings)} showings, "
            f"no gaps >= {self.config.MIN_SLOT_GAP_MINUTES}min"
        )
        return True

    def _check_operating_hours(
        self,
        date: str,
        showings_sorted: List[Dict],
        runtimes: Dict[str, int]
    ) -> bool:
        """Check if schedule covers expected operating hours.

        Args:
            date: Date being checked
            showings_sorted: Showings sorted by time
            runtimes: Dict of showing_id -> runtime_minutes

        Returns:
            True if operating hours covered, False if gaps at start/end
        """
        # Check first showing time
        first_showing = showings_sorted[0]
        first_time_str = first_showing.get('showing_time', '00:00')

        try:
            first_time = datetime.strptime(first_time_str, '%H:%M').time()
        except ValueError:
            logger.error(f"Failed to parse first time: {first_time_str}")
            return False

        # Cinema typically operates 10:00-23:00
        # If first showing starts at 11:00 or later, might add morning showing
        if first_time.hour >= self.config.LATE_START_HOUR:
            logger.info(
                f"Late start on {date}: {first_time_str} "
                f"(>= {self.config.LATE_START_HOUR}:00)"
            )
            return False  # Might add morning showing

        # Check last showing end time
        last_showing = showings_sorted[-1]
        last_time_str = last_showing.get('showing_time', '00:00')
        last_runtime = runtimes.get(last_showing['bfi_showing_id'])

        if not last_runtime:
            logger.warning(f"Missing runtime for last showing: {last_showing['bfi_showing_id']}")
            return False

        try:
            last_time = datetime.strptime(last_time_str, '%H:%M').time()
        except ValueError:
            logger.error(f"Failed to parse last time: {last_time_str}")
            return False

        last_dt = datetime.combine(datetime.today(), last_time)
        last_end_dt = last_dt + timedelta(
            minutes=last_runtime + self.config.SLOT_OVERHEAD_MINUTES
        )

        # If last showing ends before 22:00, might add evening showing
        if last_end_dt.time().hour < self.config.EARLY_END_HOUR:
            logger.info(
                f"Early finish on {date}: ends at {last_end_dt.time()} "
                f"(< {self.config.EARLY_END_HOUR}:00)"
            )
            return False  # Might add evening showing

        # Operating hours appear covered
        return True
