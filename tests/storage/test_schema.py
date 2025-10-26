"""Tests for schema.py - database schema creation and migration."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from dynamicalsystem.listing.storage.schema import (
    SCHEMA_VERSION,
    get_schema_version,
    init_database,
    migrate_database,
)


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


def test_init_database_creates_tables(temp_db):
    """Test that init_database creates all tables."""
    init_database(temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
        ORDER BY name
    """)
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()

    expected_tables = [
        'listings',
        'movie_runtimes',
        'schedule_changes',
        'schedule_snapshots',
        'scrape_schedule',
        'schema_version',
    ]

    for table in expected_tables:
        assert table in tables, f"Table '{table}' not created"


def test_init_database_creates_indices(temp_db):
    """Test that init_database creates indices."""
    init_database(temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name LIKE 'idx_%'
        ORDER BY name
    """)
    indices = [row[0] for row in cursor.fetchall()]
    conn.close()

    # Check some key indices exist
    assert 'idx_listings_date' in indices
    assert 'idx_schedule_status' in indices
    assert 'idx_snapshots_date' in indices
    assert 'idx_changes_date' in indices


def test_init_database_creates_views(temp_db):
    """Test that init_database creates views."""
    init_database(temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='view'
        ORDER BY name
    """)
    views = [row[0] for row in cursor.fetchall()]
    conn.close()

    assert 'upcoming_showings' in views
    assert 'schedule_stability' in views


def test_init_database_sets_schema_version(temp_db):
    """Test that init_database records schema version."""
    init_database(temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("SELECT version FROM schema_version")
    version = cursor.fetchone()[0]
    conn.close()

    assert version == SCHEMA_VERSION


def test_init_database_idempotent(temp_db):
    """Test that calling init_database twice doesn't error."""
    init_database(temp_db)
    init_database(temp_db)  # Should not error

    version = get_schema_version(temp_db)
    assert version == SCHEMA_VERSION


def test_get_schema_version_returns_none_for_nonexistent_db(temp_db):
    """Test get_schema_version with non-existent database."""
    version = get_schema_version(temp_db)
    assert version is None


def test_get_schema_version_returns_current_version(temp_db):
    """Test get_schema_version returns correct version."""
    init_database(temp_db)
    version = get_schema_version(temp_db)
    assert version == SCHEMA_VERSION


def test_migrate_database_no_pending_migrations(temp_db):
    """Test migrate_database when no migrations pending."""
    init_database(temp_db)
    applied = migrate_database(temp_db)
    assert applied == 0


def test_listings_table_structure(temp_db):
    """Test listings table has correct columns."""
    init_database(temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("PRAGMA table_info(listings)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()

    required_columns = {
        'id', 'bfi_showing_id', 'movie_title', 'showing_date',
        'showing_time', 'showing_datetime_utc', 'format_keywords',
        'is_3d', 'is_70mm', 'is_laser', 'availability_status',
        'scraped_at'
    }

    assert required_columns.issubset(columns)


def test_listings_unique_constraint(temp_db):
    """Test listings table prevents duplicate showings."""
    init_database(temp_db)

    conn = sqlite3.connect(temp_db)

    # Insert first showing
    conn.execute("""
        INSERT INTO listings (
            bfi_showing_id, movie_title, showing_date,
            showing_time, showing_datetime_utc
        ) VALUES ('ABC123', 'Test Movie', '2025-10-26', '10:45', '2025-10-26T09:45:00+00:00')
    """)
    conn.commit()

    # Try to insert duplicate by bfi_showing_id
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO listings (
                bfi_showing_id, movie_title, showing_date,
                showing_time, showing_datetime_utc
            ) VALUES ('ABC123', 'Different Movie', '2025-10-27', '11:00', '2025-10-27T10:00:00+00:00')
        """)

    conn.close()


def test_movie_runtimes_check_constraint(temp_db):
    """Test movie_runtimes table validates runtime range."""
    init_database(temp_db)

    conn = sqlite3.connect(temp_db)

    # Valid runtime
    conn.execute("""
        INSERT INTO movie_runtimes (movie_title, runtime_minutes, source)
        VALUES ('Test Movie', 120, 'BFI')
    """)
    conn.commit()

    # Invalid runtime (too small)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO movie_runtimes (movie_title, runtime_minutes, source)
            VALUES ('Bad Movie', 0, 'BFI')
        """)

    # Invalid runtime (too large)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO movie_runtimes (movie_title, runtime_minutes, source)
            VALUES ('Long Movie', 600, 'BFI')
        """)

    conn.close()


def test_scrape_schedule_table_structure(temp_db):
    """Test scrape_schedule table has correct columns."""
    init_database(temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("PRAGMA table_info(scrape_schedule)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()

    required_columns = {
        'date', 'status', 'showing_count', 'is_complete',
        'first_seen', 'last_scraped', 'last_checked', 'snapshot_hash'
    }

    assert required_columns.issubset(columns)


def test_schedule_snapshots_unique_constraint(temp_db):
    """Test schedule_snapshots prevents duplicate date+time."""
    init_database(temp_db)

    conn = sqlite3.connect(temp_db)
    timestamp = '2025-10-26T10:00:00+00:00'

    # Insert first snapshot
    conn.execute("""
        INSERT INTO schedule_snapshots (
            date, snapshot_hash, showing_count, scraped_at
        ) VALUES ('2025-10-26', 'abc123', 4, ?)
    """, (timestamp,))
    conn.commit()

    # Try to insert duplicate date+time
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO schedule_snapshots (
                date, snapshot_hash, showing_count, scraped_at
            ) VALUES ('2025-10-26', 'def456', 5, ?)
        """, (timestamp,))

    conn.close()


def test_schedule_changes_foreign_keys(temp_db):
    """Test schedule_changes foreign key references."""
    init_database(temp_db)

    conn = sqlite3.connect(temp_db)
    conn.execute("PRAGMA foreign_keys = ON")

    # Create snapshots
    cursor = conn.execute("""
        INSERT INTO schedule_snapshots (
            date, snapshot_hash, showing_count, scraped_at
        ) VALUES ('2025-10-26', 'abc123', 3, '2025-10-25T10:00:00+00:00')
    """)
    snap1_id = cursor.lastrowid

    cursor = conn.execute("""
        INSERT INTO schedule_snapshots (
            date, snapshot_hash, showing_count, scraped_at
        ) VALUES ('2025-10-26', 'def456', 4, '2025-10-25T11:00:00+00:00')
    """)
    snap2_id = cursor.lastrowid

    # Insert change with valid foreign keys
    conn.execute("""
        INSERT INTO schedule_changes (
            date, change_type, detected_at,
            previous_snapshot_id, new_snapshot_id
        ) VALUES ('2025-10-26', 'added', '2025-10-25T11:00:00+00:00', ?, ?)
    """, (snap1_id, snap2_id))
    conn.commit()

    # Verify it was inserted
    cursor = conn.execute("SELECT COUNT(*) FROM schedule_changes")
    assert cursor.fetchone()[0] == 1

    conn.close()
