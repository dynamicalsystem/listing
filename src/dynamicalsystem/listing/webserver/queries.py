"""Database queries for web server."""

import sqlite3
from typing import List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .models import Showing, HealthInfo


def get_upcoming_showings(db_path: str) -> List[Showing]:
    """Get all upcoming showings from database.

    Args:
        db_path: Path to SQLite database

    Returns:
        List of upcoming showings ordered by date and time
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.execute("""
            SELECT
                bfi_showing_id,
                showing_date,
                showing_time,
                showing_datetime_utc,
                movie_title,
                format_keywords,
                rating,
                detail_url_path,
                availability_status,
                availability_count,
                is_3d,
                is_70mm,
                is_laser,
                has_subtitles,
                scraped_at
            FROM listings
            WHERE showing_date >= date('now')
            ORDER BY showing_date, showing_time
        """)

        rows = cursor.fetchall()
        return [Showing(**dict(row)) for row in rows]
    finally:
        conn.close()


def get_recent_changes(db_path: str, hours: int = 24) -> List[Showing]:
    """Get showings added or updated in last N hours.

    Args:
        db_path: Path to SQLite database
        hours: Number of hours to look back

    Returns:
        List of recently changed showings
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Calculate cutoff time
        cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()

        cursor = conn.execute("""
            SELECT
                bfi_showing_id,
                showing_date,
                showing_time,
                showing_datetime_utc,
                movie_title,
                format_keywords,
                rating,
                detail_url_path,
                availability_status,
                availability_count,
                is_3d,
                is_70mm,
                is_laser,
                has_subtitles,
                scraped_at
            FROM listings
            WHERE scraped_at >= ?
            AND showing_date >= date('now')
            ORDER BY scraped_at DESC
        """, (cutoff_str,))

        rows = cursor.fetchall()
        return [Showing(**dict(row)) for row in rows]
    finally:
        conn.close()


def get_health_info(db_path: str) -> HealthInfo:
    """Get health check information.

    Args:
        db_path: Path to SQLite database

    Returns:
        Health information
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Get listing count
        cursor = conn.execute("""
            SELECT COUNT(*) as count
            FROM listings
            WHERE showing_date >= date('now')
        """)
        listings_count = cursor.fetchone()[0]

        # Get date range
        cursor = conn.execute("""
            SELECT
                MIN(showing_date) as oldest,
                MAX(showing_date) as newest
            FROM listings
            WHERE showing_date >= date('now')
        """)
        row = cursor.fetchone()
        oldest_listing = row[0]
        newest_listing = row[1]

        # Get last scrape info
        cursor = conn.execute("""
            SELECT
                MAX(last_scraped) as last_scrape,
                status
            FROM scrape_schedule
            WHERE last_scraped IS NOT NULL
            ORDER BY last_scraped DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        last_scrape = row[0] if row and row[0] else None
        last_scrape_status = row[1] if row and row[1] else None

        # Determine overall status
        if listings_count == 0:
            status = "unhealthy"
        elif last_scrape_status == "error":
            status = "degraded"
        else:
            status = "healthy"

        last_sweep, last_full_sweep, sweeps_14d = _sweep_info(conn)

        return HealthInfo(
            status=status,
            last_scrape=last_scrape,
            last_scrape_status=last_scrape_status,
            listings_count=listings_count,
            oldest_listing=oldest_listing,
            newest_listing=newest_listing,
            last_sweep=last_sweep,
            last_full_sweep=last_full_sweep,
            sweeps_14d=sweeps_14d,
        )
    finally:
        conn.close()


_SWEEP_ROW = """
    SELECT started_at, completed_at, exit_code, COALESCE(outcome, 'full') AS outcome,
           dates_attempted, dates_scraped, error_count, requests, challenges, last_cf_ray
    FROM sweep_runs
"""


def _sweep_info(conn: sqlite3.Connection):
    """Last run, last full sweep and 14-day aggregate from sweep_runs.

    Returns (None, None, None) if the table or the outcome column does not
    exist yet: the webserver reads the database directly and may start before
    any sweep has applied the v2/v3 migrations.
    """
    try:
        row = conn.execute(_SWEEP_ROW + " ORDER BY started_at DESC LIMIT 1").fetchone()
        last_sweep = dict(row) if row else None

        row = conn.execute(
            _SWEEP_ROW + " WHERE COALESCE(outcome, 'full') = 'full' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        last_full_sweep = dict(row) if row else None

        row = conn.execute("""
            SELECT
                COUNT(*) AS sweeps,
                COALESCE(SUM(CASE WHEN COALESCE(outcome, 'full') = 'full' THEN 1 ELSE 0 END), 0) AS full_sweeps,
                COALESCE(SUM(CASE WHEN COALESCE(outcome, 'full') = 'full' AND exit_code IS NOT NULL AND exit_code != 0 THEN 1 ELSE 0 END), 0) AS failed_sweeps,
                COALESCE(SUM(CASE WHEN challenges > 0 THEN 1 ELSE 0 END), 0) AS challenged_sweeps,
                COALESCE(SUM(challenges), 0) AS challenges,
                COALESCE(SUM(requests), 0) AS requests
            FROM sweep_runs
            WHERE started_at >= datetime('now', '-14 days')
        """).fetchone()
        sweeps_14d = dict(row) if row else None
        return last_sweep, last_full_sweep, sweeps_14d
    except sqlite3.OperationalError:
        return None, None, None
