"""SQLite schema definitions for BFI IMAX listing scraper.

Schema includes:
- listings: Current and future movie showings
- scrape_schedule: Dates to scrape and their status
- schedule_snapshots: Historical schedule state for learning
- schedule_changes: Detected changes over time
- movie_runtimes: Cached runtimes from BFI/external sources

All timestamps stored in UTC with explicit +00:00 timezone marker.
"""

import sqlite3
from pathlib import Path
from typing import Optional


SCHEMA_VERSION = 1


SCHEMA_SQL = """
-- Version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))
);

-- Table 1: Movie showings (public data)
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- BFI identifiers
    bfi_showing_id TEXT NOT NULL,
    bfi_performance_id TEXT,

    -- Movie details
    movie_title TEXT NOT NULL,
    movie_slug TEXT,
    rating TEXT,

    -- Showing details (times in UTC + denormalized UK local)
    showing_date DATE NOT NULL,
    showing_time TIME NOT NULL,
    showing_datetime_utc TEXT NOT NULL,
    showing_datetime_display TEXT,

    -- Format
    format_keywords TEXT,
    is_3d BOOLEAN DEFAULT 0,
    is_70mm BOOLEAN DEFAULT 0,
    is_laser BOOLEAN DEFAULT 0,
    has_subtitles BOOLEAN DEFAULT 0,

    -- Links
    detail_url_path TEXT,
    detail_url_full TEXT,

    -- Availability
    availability_status TEXT,
    availability_count INTEGER,

    -- Metadata (UTC)
    scraped_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')),

    -- Prevent duplicates
    UNIQUE(bfi_showing_id),
    UNIQUE(showing_date, showing_time, movie_title)
);

CREATE INDEX IF NOT EXISTS idx_listings_date ON listings(showing_date);
CREATE INDEX IF NOT EXISTS idx_listings_scraped_at ON listings(scraped_at);
CREATE INDEX IF NOT EXISTS idx_listings_movie ON listings(movie_title);

-- Table 2: Scrape schedule state (operational)
CREATE TABLE IF NOT EXISTS scrape_schedule (
    date DATE PRIMARY KEY,

    -- Status
    status TEXT NOT NULL,
    showing_count INTEGER DEFAULT 0,
    is_complete BOOLEAN DEFAULT 0,

    -- Timestamps (UTC)
    first_seen TEXT,
    last_scraped TEXT,
    last_checked TEXT,

    -- State
    snapshot_hash TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_schedule_status ON scrape_schedule(status);
CREATE INDEX IF NOT EXISTS idx_schedule_last_scraped ON scrape_schedule(last_scraped);
CREATE INDEX IF NOT EXISTS idx_schedule_date_range ON scrape_schedule(date, status);

-- Table 3: Schedule snapshots (learning)
CREATE TABLE IF NOT EXISTS schedule_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- What
    date DATE NOT NULL,
    snapshot_hash TEXT NOT NULL,
    showing_count INTEGER NOT NULL,
    is_complete BOOLEAN,

    -- When (UTC)
    scraped_at TEXT NOT NULL,

    -- Change detection
    changed_from_previous BOOLEAN DEFAULT 0,

    UNIQUE(date, scraped_at)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_date ON schedule_snapshots(date);
CREATE INDEX IF NOT EXISTS idx_snapshots_scraped_at ON schedule_snapshots(scraped_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_hash ON schedule_snapshots(date, snapshot_hash);

-- Table 4: Schedule changes (learning)
CREATE TABLE IF NOT EXISTS schedule_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- What changed
    date DATE NOT NULL,
    change_type TEXT NOT NULL,
    showing_time TIME,
    movie_title TEXT,

    -- Context
    previous_count INTEGER,
    new_count INTEGER,
    details TEXT,

    -- When (UTC)
    detected_at TEXT NOT NULL,

    -- Link to snapshots
    previous_snapshot_id INTEGER,
    new_snapshot_id INTEGER,

    FOREIGN KEY (previous_snapshot_id) REFERENCES schedule_snapshots(snapshot_id),
    FOREIGN KEY (new_snapshot_id) REFERENCES schedule_snapshots(snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_changes_date ON schedule_changes(date);
CREATE INDEX IF NOT EXISTS idx_changes_type ON schedule_changes(change_type);
CREATE INDEX IF NOT EXISTS idx_changes_detected_at ON schedule_changes(detected_at);
CREATE INDEX IF NOT EXISTS idx_changes_date_type ON schedule_changes(date, change_type);

-- Table 5: Movie runtimes cache (operational)
-- Updated 2025-10-26: Simplified - NULL=unknown, INTEGER=known
CREATE TABLE IF NOT EXISTS movie_runtimes (
    movie_title TEXT PRIMARY KEY,

    -- Runtime (NULL = unknown, INTEGER = known)
    runtime_minutes INTEGER,

    -- Source (audit only)
    source TEXT,

    -- Metadata (UTC)
    fetched_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')),

    -- Validation
    CHECK (runtime_minutes IS NULL OR (runtime_minutes > 0 AND runtime_minutes < 500))
);

CREATE INDEX IF NOT EXISTS idx_runtimes_source ON movie_runtimes(source);

-- View: Upcoming showings (today and later)
CREATE VIEW IF NOT EXISTS upcoming_showings AS
SELECT
    l.*,
    r.runtime_minutes,
    r.source as runtime_source
FROM listings l
LEFT JOIN movie_runtimes r ON l.movie_title = r.movie_title
WHERE l.showing_date >= date('now')
ORDER BY l.showing_date, l.showing_time;

-- View: Schedule stability analysis
CREATE VIEW IF NOT EXISTS schedule_stability AS
SELECT
    date,
    MIN(scraped_at) as first_seen,
    MAX(scraped_at) as last_changed,
    COUNT(*) as snapshot_count,
    MAX(showing_count) as final_showing_count
FROM schedule_snapshots
GROUP BY date;
"""


# Future migrations
MIGRATIONS = {
    # Version 2 migrations would go here
    # 2: "ALTER TABLE listings ADD COLUMN new_field TEXT;",
}


def init_database(db_path: str) -> None:
    """Initialize database with schema.

    Args:
        db_path: Path to SQLite database file

    Creates all tables, indices, and views. Safe to call on existing database
    (uses IF NOT EXISTS).
    """
    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)

        # Record schema version if not already present
        cursor = conn.execute("SELECT COUNT(*) FROM schema_version WHERE version = ?",
                            (SCHEMA_VERSION,))
        if cursor.fetchone()[0] == 0:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)",
                        (SCHEMA_VERSION,))

        conn.commit()
    finally:
        conn.close()


def migrate_database(db_path: str) -> int:
    """Apply pending migrations to database.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Number of migrations applied

    Raises:
        sqlite3.Error: If migration fails
    """
    conn = sqlite3.connect(db_path)
    migrations_applied = 0

    try:
        # Get current version
        cursor = conn.execute("SELECT MAX(version) FROM schema_version")
        result = cursor.fetchone()
        current_version = result[0] if result and result[0] else 0

        # Apply pending migrations
        for version in sorted(MIGRATIONS.keys()):
            if version > current_version:
                conn.executescript(MIGRATIONS[version])
                conn.execute("INSERT INTO schema_version (version) VALUES (?)",
                           (version,))
                conn.commit()
                migrations_applied += 1

        return migrations_applied
    finally:
        conn.close()


def get_schema_version(db_path: str) -> Optional[int]:
    """Get current schema version.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Current schema version, or None if database not initialized
    """
    try:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute("SELECT MAX(version) FROM schema_version")
            result = cursor.fetchone()
            return result[0] if result and result[0] else None
        finally:
            conn.close()
    except sqlite3.OperationalError:
        # Table doesn't exist
        return None
