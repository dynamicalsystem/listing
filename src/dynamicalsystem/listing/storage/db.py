"""Database access layer for BFI IMAX listing scraper.

Provides high-level interface for:
- Inserting and querying showings
- Managing scrape schedule state
- Recording snapshots and detecting changes
- Caching movie runtimes
"""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .schema import init_database, migrate_database


class Database:
    """Database access layer for listing scraper.

    Provides methods for all database operations. Handles connection management,
    transactions, and error handling.

    Example:
        db = Database("listing.db")
        db.insert_showings([{
            'bfi_showing_id': '123',
            'movie_title': 'Frankenstein',
            'showing_date': '2025-10-26',
            ...
        }])
    """

    def __init__(self, db_path: str = "listing.db"):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file

        Creates database and schema if not exists.
        """
        self.db_path = db_path

        # Initialize schema if needed
        from .schema import get_schema_version
        if get_schema_version(db_path) is None:
            # Database doesn't exist or has no schema
            init_database(db_path)
        else:
            # Apply pending migrations
            migrate_database(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection.

        Returns:
            SQLite connection with row factory set
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------------------
    # Listings Operations
    # -------------------------------------------------------------------------

    def insert_showings(self, showings: List[Dict]) -> int:
        """Insert showings, ignore duplicates.

        Args:
            showings: List of showing dictionaries with required fields:
                - bfi_showing_id
                - movie_title
                - showing_date
                - showing_time
                - showing_datetime_utc

        Returns:
            Number of showings actually inserted (ignoring duplicates)
        """
        if not showings:
            return 0

        conn = self._get_connection()
        inserted = 0

        try:
            for showing in showings:
                try:
                    conn.execute("""
                        INSERT INTO listings (
                            bfi_showing_id, bfi_performance_id,
                            movie_title, movie_slug, rating,
                            showing_date, showing_time, showing_datetime_utc, showing_datetime_display,
                            format_keywords, is_3d, is_70mm, is_laser, has_subtitles,
                            detail_url_path, detail_url_full,
                            availability_status, availability_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        showing.get('bfi_showing_id'),
                        showing.get('bfi_performance_id'),
                        showing.get('movie_title'),
                        showing.get('movie_slug'),
                        showing.get('rating'),
                        showing.get('showing_date'),
                        showing.get('showing_time'),
                        showing.get('showing_datetime_utc'),
                        showing.get('showing_datetime_display'),
                        showing.get('format_keywords'),
                        showing.get('is_3d', False),
                        showing.get('is_70mm', False),
                        showing.get('is_laser', False),
                        showing.get('has_subtitles', False),
                        showing.get('detail_url_path'),
                        showing.get('detail_url_full'),
                        showing.get('availability_status'),
                        showing.get('availability_count'),
                    ))
                    inserted += 1
                except sqlite3.IntegrityError:
                    # Duplicate - skip
                    pass

            conn.commit()
            return inserted
        finally:
            conn.close()

    def get_upcoming_showings(self, limit: Optional[int] = None) -> List[Dict]:
        """Get all upcoming showings (today and future).

        Args:
            limit: Maximum number of results (None = all)

        Returns:
            List of showing dictionaries
        """
        conn = self._get_connection()
        try:
            query = """
                SELECT * FROM upcoming_showings
            """
            if limit:
                query += f" LIMIT {limit}"

            cursor = conn.execute(query)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_showings_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Get showings in date range.

        Args:
            start_date: Start date (inclusive) in YYYY-MM-DD format
            end_date: End date (inclusive) in YYYY-MM-DD format

        Returns:
            List of showing dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                SELECT * FROM listings
                WHERE showing_date BETWEEN ? AND ?
                ORDER BY showing_date, showing_time
            """, (start_date, end_date))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_recent_showings(self, hours: int = 24) -> List[Dict]:
        """Get showings added in last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            List of showing dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                SELECT * FROM listings
                WHERE scraped_at >= datetime('now', ? || ' hours')
                ORDER BY scraped_at DESC
            """, (f'-{hours}',))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete_old_listings(self, before_date: str) -> int:
        """Delete listings older than date.

        Args:
            before_date: Delete showings before this date (YYYY-MM-DD)

        Returns:
            Number of listings deleted
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                DELETE FROM listings
                WHERE showing_date < ?
            """, (before_date,))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Scrape Schedule Operations
    # -------------------------------------------------------------------------

    def get_dates_to_scrape(self) -> List[str]:
        """Get dates that need scraping today.

        Returns dates that are:
        - Partial or unknown in next 14 days
        - Partial beyond 14 days but not checked in 7+ days
        - Empty but not checked in 7+ days

        Returns:
            List of dates in YYYY-MM-DD format
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                SELECT date
                FROM scrape_schedule
                WHERE
                    -- Partial or unknown dates in next 14 days
                    (status IN ('partial', 'unknown')
                     AND date BETWEEN date('now') AND date('now', '+14 days'))
                    OR
                    -- Weekly check on far-future partial dates
                    (status = 'partial'
                     AND date > date('now', '+14 days')
                     AND julianday('now') - julianday(last_checked) >= 7)
                    OR
                    -- Re-check empty dates weekly
                    (status = 'empty'
                     AND date >= date('now')
                     AND julianday('now') - julianday(last_checked) >= 7)
                ORDER BY date
            """)
            return [row['date'] for row in cursor.fetchall()]
        finally:
            conn.close()

    def update_schedule_status(
        self,
        date: str,
        status: str,
        showing_count: int,
        is_complete: bool,
        snapshot_hash: Optional[str] = None,
        notes: Optional[str] = None
    ) -> None:
        """Update scrape_schedule for a date.

        Args:
            date: Date in YYYY-MM-DD format
            status: 'empty', 'partial', 'complete', 'unknown'
            showing_count: Number of showings found
            is_complete: Whether schedule is complete
            snapshot_hash: Hash of current schedule state
            notes: Optional notes about this update
        """
        conn = self._get_connection()
        now_utc = datetime.now(UTC).isoformat()

        try:
            # Check if date exists
            cursor = conn.execute(
                "SELECT first_seen FROM scrape_schedule WHERE date = ?",
                (date,)
            )
            row = cursor.fetchone()

            if row:
                # Update existing
                conn.execute("""
                    UPDATE scrape_schedule
                    SET status = ?,
                        showing_count = ?,
                        is_complete = ?,
                        last_scraped = ?,
                        last_checked = ?,
                        snapshot_hash = ?,
                        notes = ?
                    WHERE date = ?
                """, (status, showing_count, is_complete, now_utc, now_utc,
                      snapshot_hash, notes, date))
            else:
                # Insert new
                conn.execute("""
                    INSERT INTO scrape_schedule (
                        date, status, showing_count, is_complete,
                        first_seen, last_scraped, last_checked,
                        snapshot_hash, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (date, status, showing_count, is_complete,
                      now_utc, now_utc, now_utc, snapshot_hash, notes))

            conn.commit()
        finally:
            conn.close()

    def get_schedule_status(self, date: str) -> Optional[Dict]:
        """Get scrape schedule status for a date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Schedule status dictionary or None if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM scrape_schedule WHERE date = ?",
                (date,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Snapshot Operations
    # -------------------------------------------------------------------------

    def record_snapshot(
        self,
        date: str,
        showings: List[Dict],
        is_complete: bool = False
    ) -> int:
        """Record schedule snapshot.

        Args:
            date: Date in YYYY-MM-DD format
            showings: List of showings for this date
            is_complete: Whether schedule is complete

        Returns:
            Snapshot ID
        """
        conn = self._get_connection()
        now_utc = datetime.now(UTC).isoformat()

        try:
            # Compute snapshot hash
            snapshot_hash = self._compute_snapshot_hash(showings)
            showing_count = len(showings)

            # Check if changed from previous
            cursor = conn.execute("""
                SELECT snapshot_hash FROM schedule_snapshots
                WHERE date = ?
                ORDER BY scraped_at DESC
                LIMIT 1
            """, (date,))
            prev_row = cursor.fetchone()
            changed = (not prev_row) or (prev_row['snapshot_hash'] != snapshot_hash)

            # Insert snapshot
            cursor = conn.execute("""
                INSERT INTO schedule_snapshots (
                    date, snapshot_hash, showing_count, is_complete,
                    scraped_at, changed_from_previous
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (date, snapshot_hash, showing_count, is_complete,
                  now_utc, changed))

            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_latest_snapshot(self, date: str) -> Optional[Dict]:
        """Get most recent snapshot for a date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Snapshot dictionary or None
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                SELECT * FROM schedule_snapshots
                WHERE date = ?
                ORDER BY scraped_at DESC
                LIMIT 1
            """, (date,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def prune_old_snapshots(self, days: int = 30) -> int:
        """Prune snapshots older than N days past showing date.

        Args:
            days: Keep snapshots for this many days after showing date

        Returns:
            Number of snapshots deleted
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                DELETE FROM schedule_snapshots
                WHERE date < date('now', ?)
            """, (f'-{days} days',))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def _compute_snapshot_hash(self, showings: List[Dict]) -> str:
        """Compute hash of schedule state.

        Hash includes showing times, titles, and formats.
        Excludes availability counts (change frequently).

        Args:
            showings: List of showing dictionaries

        Returns:
            16-character hex hash
        """
        normalized = sorted([
            {
                'time': s.get('showing_time', ''),
                'title': s.get('movie_title', ''),
                'format': s.get('format_keywords', '')
            }
            for s in showings
        ], key=lambda x: x['time'])

        data = json.dumps(normalized, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    # -------------------------------------------------------------------------
    # Change Detection Operations
    # -------------------------------------------------------------------------

    def detect_and_record_changes(
        self,
        date: str,
        new_snapshot_id: int,
        prev_snapshot_id: Optional[int] = None
    ) -> List[Dict]:
        """Detect and record changes between snapshots.

        Compares showings and records added, removed, or modified showings.

        Args:
            date: Date in YYYY-MM-DD format
            new_snapshot_id: New snapshot ID
            prev_snapshot_id: Previous snapshot ID (None = find automatically)

        Returns:
            List of change dictionaries
        """
        conn = self._get_connection()
        now_utc = datetime.now(UTC).isoformat()

        try:
            # Find previous snapshot if not provided
            if prev_snapshot_id is None:
                cursor = conn.execute("""
                    SELECT snapshot_id FROM schedule_snapshots
                    WHERE date = ? AND snapshot_id < ?
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (date, new_snapshot_id))
                row = cursor.fetchone()
                if not row:
                    # First snapshot - record as "first_seen"
                    cursor = conn.execute("""
                        SELECT showing_count FROM schedule_snapshots
                        WHERE snapshot_id = ?
                    """, (new_snapshot_id,))
                    count_row = cursor.fetchone()
                    if count_row and count_row['showing_count'] > 0:
                        conn.execute("""
                            INSERT INTO schedule_changes (
                                date, change_type, previous_count, new_count,
                                detected_at, new_snapshot_id
                            ) VALUES (?, 'first_seen', 0, ?, ?, ?)
                        """, (date, count_row['showing_count'], now_utc, new_snapshot_id))
                        conn.commit()
                    return []
                prev_snapshot_id = row['snapshot_id']

            # Get showings for both snapshots
            cursor = conn.execute("""
                SELECT scraped_at FROM schedule_snapshots WHERE snapshot_id = ?
            """, (prev_snapshot_id,))
            prev_time = cursor.fetchone()['scraped_at']

            cursor = conn.execute("""
                SELECT scraped_at FROM schedule_snapshots WHERE snapshot_id = ?
            """, (new_snapshot_id,))
            new_time = cursor.fetchone()['scraped_at']

            # Get showings at each time
            cursor = conn.execute("""
                SELECT showing_time, movie_title, format_keywords
                FROM listings
                WHERE showing_date = ? AND scraped_at <= ?
            """, (date, prev_time))
            prev_showings = {
                (row['showing_time'], row['movie_title']): row
                for row in cursor.fetchall()
            }

            cursor = conn.execute("""
                SELECT showing_time, movie_title, format_keywords
                FROM listings
                WHERE showing_date = ? AND scraped_at <= ?
            """, (date, new_time))
            new_showings = {
                (row['showing_time'], row['movie_title']): row
                for row in cursor.fetchall()
            }

            # Detect changes
            changes = []
            prev_keys = set(prev_showings.keys())
            new_keys = set(new_showings.keys())

            # Added showings
            for key in new_keys - prev_keys:
                showing = new_showings[key]
                conn.execute("""
                    INSERT INTO schedule_changes (
                        date, change_type, showing_time, movie_title,
                        previous_count, new_count, detected_at,
                        previous_snapshot_id, new_snapshot_id
                    ) VALUES (?, 'added', ?, ?, ?, ?, ?, ?, ?)
                """, (date, showing['showing_time'], showing['movie_title'],
                      len(prev_showings), len(new_showings), now_utc,
                      prev_snapshot_id, new_snapshot_id))
                changes.append({
                    'type': 'added',
                    'time': showing['showing_time'],
                    'title': showing['movie_title']
                })

            # Removed showings
            for key in prev_keys - new_keys:
                showing = prev_showings[key]
                conn.execute("""
                    INSERT INTO schedule_changes (
                        date, change_type, showing_time, movie_title,
                        previous_count, new_count, detected_at,
                        previous_snapshot_id, new_snapshot_id
                    ) VALUES (?, 'removed', ?, ?, ?, ?, ?, ?, ?)
                """, (date, showing['showing_time'], showing['movie_title'],
                      len(prev_showings), len(new_showings), now_utc,
                      prev_snapshot_id, new_snapshot_id))
                changes.append({
                    'type': 'removed',
                    'time': showing['showing_time'],
                    'title': showing['movie_title']
                })

            # Modified showings (same time+title, different format)
            for key in prev_keys & new_keys:
                prev = prev_showings[key]
                new = new_showings[key]
                if prev['format_keywords'] != new['format_keywords']:
                    details = json.dumps({
                        'from': prev['format_keywords'],
                        'to': new['format_keywords']
                    })
                    conn.execute("""
                        INSERT INTO schedule_changes (
                            date, change_type, showing_time, movie_title,
                            details, detected_at,
                            previous_snapshot_id, new_snapshot_id
                        ) VALUES (?, 'modified', ?, ?, ?, ?, ?, ?)
                    """, (date, new['showing_time'], new['movie_title'],
                          details, now_utc, prev_snapshot_id, new_snapshot_id))
                    changes.append({
                        'type': 'modified',
                        'time': new['showing_time'],
                        'title': new['movie_title'],
                        'details': details
                    })

            conn.commit()
            return changes
        finally:
            conn.close()

    def get_changes_for_date(self, date: str) -> List[Dict]:
        """Get all changes for a date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            List of change dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                SELECT * FROM schedule_changes
                WHERE date = ?
                ORDER BY detected_at
            """, (date,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Runtime Cache Operations
    # -------------------------------------------------------------------------

    def get_runtime(self, movie_title: str) -> Optional[Dict]:
        """Get cached runtime for movie.

        Args:
            movie_title: Movie title

        Returns:
            Runtime dictionary or None
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                SELECT * FROM movie_runtimes WHERE movie_title = ?
            """, (movie_title,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def cache_runtime(
        self,
        movie_title: str,
        runtime_minutes: int,
        source: str,
        source_url: Optional[str] = None,
        confidence: str = 'confirmed'
    ) -> None:
        """Cache runtime from external source.

        Args:
            movie_title: Movie title
            runtime_minutes: Runtime in minutes
            source: 'BFI', 'Wikipedia', 'IMDb', 'TMDb'
            source_url: URL where runtime was found
            confidence: 'confirmed', 'estimated', 'uncertain'
        """
        conn = self._get_connection()
        now_utc = datetime.now(UTC).isoformat()

        try:
            conn.execute("""
                INSERT OR REPLACE INTO movie_runtimes (
                    movie_title, runtime_minutes, source, source_url,
                    confidence, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (movie_title, runtime_minutes, source, source_url,
                  confidence, now_utc))
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Health & Stats Operations
    # -------------------------------------------------------------------------

    def get_health_info(self) -> Dict:
        """Get database health information.

        Returns:
            Dictionary with counts and timestamps
        """
        conn = self._get_connection()
        try:
            info = {}

            # Listing counts
            cursor = conn.execute("SELECT COUNT(*) as count FROM listings")
            info['listings_count'] = cursor.fetchone()['count']

            cursor = conn.execute("""
                SELECT MIN(showing_date) as oldest, MAX(showing_date) as newest
                FROM listings
            """)
            row = cursor.fetchone()
            info['oldest_listing'] = row['oldest']
            info['newest_listing'] = row['newest']

            # Last scrape
            cursor = conn.execute("""
                SELECT MAX(last_scraped) as last_scrape FROM scrape_schedule
            """)
            row = cursor.fetchone()
            info['last_scrape'] = row['last_scrape']

            return info
        finally:
            conn.close()
