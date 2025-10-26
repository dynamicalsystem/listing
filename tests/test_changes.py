"""Tests for ChangeDetector and snapshot comparison logic."""

import pytest
from dynamicalsystem.listing.scraper.changes import (
    Change,
    ChangeDetector,
    compute_snapshot_hash,
)
from dynamicalsystem.listing.storage.db import Database


@pytest.fixture
def db(tmp_path):
    """Create temporary database for testing."""
    db_path = str(tmp_path / "test.db")
    return Database(db_path)


@pytest.fixture
def detector(db):
    """Create ChangeDetector instance."""
    return ChangeDetector(db)


def test_compute_snapshot_hash_same_data():
    """Test that identical showings produce same hash."""
    showings1 = [
        {'showing_time': '10:00', 'movie_title': 'Film A', 'format_keywords': '3D'},
        {'showing_time': '14:00', 'movie_title': 'Film B', 'format_keywords': 'IMAX'},
    ]
    showings2 = [
        {'showing_time': '10:00', 'movie_title': 'Film A', 'format_keywords': '3D'},
        {'showing_time': '14:00', 'movie_title': 'Film B', 'format_keywords': 'IMAX'},
    ]

    assert compute_snapshot_hash(showings1) == compute_snapshot_hash(showings2)


def test_compute_snapshot_hash_ignores_order():
    """Test that hash is independent of showing order."""
    showings1 = [
        {'showing_time': '10:00', 'movie_title': 'Film A', 'format_keywords': '3D'},
        {'showing_time': '14:00', 'movie_title': 'Film B', 'format_keywords': 'IMAX'},
    ]
    showings2 = [
        {'showing_time': '14:00', 'movie_title': 'Film B', 'format_keywords': 'IMAX'},
        {'showing_time': '10:00', 'movie_title': 'Film A', 'format_keywords': '3D'},
    ]

    assert compute_snapshot_hash(showings1) == compute_snapshot_hash(showings2)


def test_compute_snapshot_hash_ignores_availability():
    """Test that hash ignores availability changes."""
    showings1 = [
        {
            'showing_time': '10:00',
            'movie_title': 'Film A',
            'format_keywords': '3D',
            'availability_count': 150,
            'availability_status': 'G'
        },
    ]
    showings2 = [
        {
            'showing_time': '10:00',
            'movie_title': 'Film A',
            'format_keywords': '3D',
            'availability_count': 38,
            'availability_status': 'L'
        },
    ]

    # Hash should be same (availability not included)
    assert compute_snapshot_hash(showings1) == compute_snapshot_hash(showings2)


def test_compute_snapshot_hash_detects_changes():
    """Test that hash changes when schedule changes."""
    showings1 = [
        {'showing_time': '10:00', 'movie_title': 'Film A', 'format_keywords': '3D'},
    ]
    showings2 = [
        {'showing_time': '10:00', 'movie_title': 'Film A', 'format_keywords': '3D'},
        {'showing_time': '14:00', 'movie_title': 'Film B', 'format_keywords': 'IMAX'},
    ]

    assert compute_snapshot_hash(showings1) != compute_snapshot_hash(showings2)


def test_detect_changes_first_seen(detector, db):
    """Test first snapshot returns 'first_seen' change."""
    showings = [
        {
            'bfi_showing_id': '1',
            'showing_time': '10:00',
            'movie_title': 'Film A',
            'format_keywords': '3D'
        },
    ]

    changes = detector.detect_changes('2025-10-26', showings)

    assert len(changes) == 1
    assert changes[0].change_type == 'first_seen'
    assert changes[0].date == '2025-10-26'


def test_detect_changes_no_change(detector, db):
    """Test no changes when snapshot matches previous."""
    showings = [
        {
            'bfi_showing_id': '1',
            'movie_title': 'Film A',
            'showing_date': '2025-10-26',
            'showing_time': '10:00',
            'showing_datetime_utc': '2025-10-26T09:00:00+00:00',
            'showing_datetime_display': 'Sat 26 Oct 10:00',
            'format_keywords': '3D',
            'movie_slug': 'film-a',
            'rating': 'PG',
            'is_3d': True,
            'is_70mm': False,
            'is_laser': False,
            'has_subtitles': False,
            'detail_url_path': 'detail.asp?id=1',
            'detail_url_full': 'https://bfi.org.uk/detail.asp?id=1',
            'availability_status': 'G',
            'availability_count': 150,
        },
    ]

    # Record initial snapshot
    db.upsert_showings(showings)
    db.record_snapshot('2025-10-26', showings)

    # Detect changes (none expected)
    changes = detector.detect_changes('2025-10-26', showings)

    assert len(changes) == 0


def test_detect_changes_showing_added(detector, db):
    """Test detection of added showing."""
    initial_showings = [
        {
            'bfi_showing_id': '1',
            'movie_title': 'Film A',
            'showing_date': '2025-10-26',
            'showing_time': '10:00',
            'showing_datetime_utc': '2025-10-26T09:00:00+00:00',
            'showing_datetime_display': 'Sat 26 Oct 10:00',
            'format_keywords': '3D',
            'movie_slug': 'film-a',
            'rating': 'PG',
            'is_3d': True,
            'is_70mm': False,
            'is_laser': False,
            'has_subtitles': False,
            'detail_url_path': 'detail.asp?id=1',
            'detail_url_full': 'https://bfi.org.uk/detail.asp?id=1',
            'availability_status': 'G',
            'availability_count': 150,
        },
    ]

    # Record initial snapshot
    db.upsert_showings(initial_showings)
    db.record_snapshot('2025-10-26', initial_showings)

    # New showings with additional showing
    new_showings = initial_showings + [
        {
            'bfi_showing_id': '2',
            'movie_title': 'Film B',
            'showing_date': '2025-10-26',
            'showing_time': '14:00',
            'showing_datetime_utc': '2025-10-26T13:00:00+00:00',
            'showing_datetime_display': 'Sat 26 Oct 14:00',
            'format_keywords': 'IMAX',
            'movie_slug': 'film-b',
            'rating': '12A',
            'is_3d': False,
            'is_70mm': False,
            'is_laser': True,
            'has_subtitles': False,
            'detail_url_path': 'detail.asp?id=2',
            'detail_url_full': 'https://bfi.org.uk/detail.asp?id=2',
            'availability_status': 'G',
            'availability_count': 200,
        },
    ]

    changes = detector.detect_changes('2025-10-26', new_showings)

    assert len(changes) == 1
    assert changes[0].change_type == 'added'
    assert changes[0].movie_title == 'Film B'
    assert changes[0].showing_time == '14:00'


def test_detect_changes_showing_removed(detector, db):
    """Test detection of removed showing."""
    initial_showings = [
        {
            'bfi_showing_id': '1',
            'movie_title': 'Film A',
            'showing_date': '2025-10-26',
            'showing_time': '10:00',
            'showing_datetime_utc': '2025-10-26T09:00:00+00:00',
            'showing_datetime_display': 'Sat 26 Oct 10:00',
            'format_keywords': '3D',
            'movie_slug': 'film-a',
            'rating': 'PG',
            'is_3d': True,
            'is_70mm': False,
            'is_laser': False,
            'has_subtitles': False,
            'detail_url_path': 'detail.asp?id=1',
            'detail_url_full': 'https://bfi.org.uk/detail.asp?id=1',
            'availability_status': 'G',
            'availability_count': 150,
        },
        {
            'bfi_showing_id': '2',
            'movie_title': 'Film B',
            'showing_date': '2025-10-26',
            'showing_time': '14:00',
            'showing_datetime_utc': '2025-10-26T13:00:00+00:00',
            'showing_datetime_display': 'Sat 26 Oct 14:00',
            'format_keywords': 'IMAX',
            'movie_slug': 'film-b',
            'rating': '12A',
            'is_3d': False,
            'is_70mm': False,
            'is_laser': True,
            'has_subtitles': False,
            'detail_url_path': 'detail.asp?id=2',
            'detail_url_full': 'https://bfi.org.uk/detail.asp?id=2',
            'availability_status': 'G',
            'availability_count': 200,
        },
    ]

    # Record initial snapshot
    db.upsert_showings(initial_showings)
    db.record_snapshot('2025-10-26', initial_showings)

    # Remove one showing
    new_showings = [initial_showings[0]]

    changes = detector.detect_changes('2025-10-26', new_showings)

    assert len(changes) == 1
    assert changes[0].change_type == 'removed'
    assert changes[0].movie_title == 'Film B'


def test_detect_changes_showing_modified(detector, db):
    """Test detection of modified showing."""
    initial_showings = [
        {
            'bfi_showing_id': '1',
            'movie_title': 'Film A',
            'showing_date': '2025-10-26',
            'showing_time': '10:00',
            'showing_datetime_utc': '2025-10-26T09:00:00+00:00',
            'showing_datetime_display': 'Sat 26 Oct 10:00',
            'format_keywords': '2D',
            'movie_slug': 'film-a',
            'rating': 'PG',
            'is_3d': False,
            'is_70mm': False,
            'is_laser': False,
            'has_subtitles': False,
            'detail_url_path': 'detail.asp?id=1',
            'detail_url_full': 'https://bfi.org.uk/detail.asp?id=1',
            'availability_status': 'G',
            'availability_count': 150,
        },
    ]

    # Record initial snapshot
    db.upsert_showings(initial_showings)
    db.record_snapshot('2025-10-26', initial_showings)

    # Modify showing (change format)
    modified_showings = [
        {
            **initial_showings[0],
            'format_keywords': '3D',  # Changed
        },
    ]

    changes = detector.detect_changes('2025-10-26', modified_showings)

    assert len(changes) == 1
    assert changes[0].change_type == 'modified'
    assert changes[0].movie_title == 'Film A'
