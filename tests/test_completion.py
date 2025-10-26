"""Tests for CompletionChecker and runtime-based gap modeling."""

import pytest
from dynamicalsystem.listing.scraper.completion import CompletionChecker, CompletionConfig
from dynamicalsystem.listing.scraper.runtime import RuntimeFetcher
from dynamicalsystem.listing.storage.db import Database


@pytest.fixture
def db(tmp_path):
    """Create temporary database for testing."""
    db_path = str(tmp_path / "test.db")
    return Database(db_path)


@pytest.fixture
def runtime_fetcher(db):
    """Create RuntimeFetcher instance."""
    return RuntimeFetcher(db)


@pytest.fixture
def checker(runtime_fetcher):
    """Create CompletionChecker instance."""
    config = CompletionConfig()
    return CompletionChecker(runtime_fetcher, config)


def test_is_complete_empty_day(checker):
    """Test that empty day is considered complete."""
    result = checker.is_complete('2025-10-26', [])
    assert result is True


def test_is_complete_missing_runtimes(checker, db):
    """Test that day is incomplete when runtimes unknown."""
    showings = [
        {
            'bfi_showing_id': '1',
            'movie_title': 'Unknown Film',
            'showing_time': '10:00',
        },
    ]

    result = checker.is_complete('2025-10-26', showings)
    assert result is False  # Can't determine completion without runtimes


def test_is_complete_no_gaps(checker, db):
    """Test complete day with no gaps between showings."""
    # Cache runtimes
    db.cache_runtime('Film A', 150, 'test')  # 2.5 hours
    db.cache_runtime('Film B', 119, 'test')  # ~2 hours
    db.cache_runtime('Film C', 162, 'test')  # 2.7 hours
    db.cache_runtime('Film D', 100, 'test')  # 1.7 hours

    showings = [
        {'bfi_showing_id': '1', 'movie_title': 'Film A', 'showing_time': '10:45'},
        {'bfi_showing_id': '2', 'movie_title': 'Film B', 'showing_time': '14:10'},
        {'bfi_showing_id': '3', 'movie_title': 'Film C', 'showing_time': '17:00'},
        {'bfi_showing_id': '4', 'movie_title': 'Film D', 'showing_time': '20:30'},
    ]

    result = checker.is_complete('2025-10-26', showings)
    assert result is True  # No gaps >= 150min


def test_is_complete_large_gap(checker, db):
    """Test incomplete day with large gap between showings."""
    # Cache runtimes
    db.cache_runtime('Film A', 90, 'test')
    db.cache_runtime('Film B', 90, 'test')

    showings = [
        {'bfi_showing_id': '1', 'movie_title': 'Film A', 'showing_time': '10:00'},
        {'bfi_showing_id': '2', 'movie_title': 'Film B', 'showing_time': '17:00'},  # 7-hour gap
    ]

    result = checker.is_complete('2025-10-26', showings)
    assert result is False  # Gap of ~5 hours allows more showings


def test_is_complete_late_start(checker, db):
    """Test incomplete day with late first showing."""
    # Cache runtime
    db.cache_runtime('Film A', 120, 'test')

    showings = [
        {'bfi_showing_id': '1', 'movie_title': 'Film A', 'showing_time': '12:00'},  # Starts at noon
    ]

    result = checker.is_complete('2025-10-26', showings)
    assert result is False  # Late start, could add morning showing


def test_is_complete_early_finish(checker, db):
    """Test incomplete day with early last showing."""
    # Cache runtime
    db.cache_runtime('Film A', 90, 'test')

    showings = [
        {'bfi_showing_id': '1', 'movie_title': 'Film A', 'showing_time': '10:00'},
        # Film A: 10:00-11:30 + 40min = ends 12:10
        # Last showing ends before 22:00 threshold
    ]

    result = checker.is_complete('2025-10-26', showings)
    assert result is False  # Early finish, could add evening showing


def test_is_complete_full_day_coverage(checker, db):
    """Test complete day with good operating hours coverage."""
    # Cache runtimes
    db.cache_runtime('Film A', 120, 'test')
    db.cache_runtime('Film B', 120, 'test')
    db.cache_runtime('Film C', 120, 'test')
    db.cache_runtime('Film D', 120, 'test')

    showings = [
        {'bfi_showing_id': '1', 'movie_title': 'Film A', 'showing_time': '10:00'},  # Starts 10:00
        {'bfi_showing_id': '2', 'movie_title': 'Film B', 'showing_time': '12:45'},
        {'bfi_showing_id': '3', 'movie_title': 'Film C', 'showing_time': '15:30'},
        {'bfi_showing_id': '4', 'movie_title': 'Film D', 'showing_time': '19:30'},  # Ends ~22:10
    ]

    result = checker.is_complete('2025-10-26', showings)
    assert result is True  # Good coverage, no large gaps, ends after 22:00


def test_gap_calculation(checker, db):
    """Test gap calculation between consecutive showings."""
    # Cache runtimes
    db.cache_runtime('Film A', 100, 'test')  # 100min + 40min overhead = 140min total
    db.cache_runtime('Film B', 100, 'test')
    db.cache_runtime('Film C', 100, 'test')
    db.cache_runtime('Film D', 100, 'test')
    db.cache_runtime('Film E', 100, 'test')

    showings = [
        {'bfi_showing_id': '1', 'movie_title': 'Film A', 'showing_time': '10:00'},
        # Film A: 10:00 + 140min = 12:20
        {'bfi_showing_id': '2', 'movie_title': 'Film B', 'showing_time': '12:30'},  # 10min gap
        # Film B: 12:30 + 140min = 14:50
        {'bfi_showing_id': '3', 'movie_title': 'Film C', 'showing_time': '15:00'},  # 10min gap
        # Film C: 15:00 + 140min = 17:20
        {'bfi_showing_id': '4', 'movie_title': 'Film D', 'showing_time': '17:30'},  # 10min gap
        # Film D: 17:30 + 140min = 19:50
        {'bfi_showing_id': '5', 'movie_title': 'Film E', 'showing_time': '20:00'},  # Ends 22:20
    ]

    result = checker.is_complete('2025-10-26', showings)
    assert result is True  # Small gaps between consecutive (<150min), ends after 22:00


def test_overhead_calculation(checker, db):
    """Test that overhead (ads + changeover) is correctly applied."""
    config = checker.config

    # Verify config values
    assert config.SLOT_OVERHEAD_MINUTES == 40
    assert config.MIN_SLOT_GAP_MINUTES == 150

    # Cache runtime
    db.cache_runtime('Short Film', 60, 'test')

    showings = [
        {'bfi_showing_id': '1', 'movie_title': 'Short Film', 'showing_time': '10:00'},
        # 60min runtime + 40min overhead = 100min total -> ends at 11:40
        {'bfi_showing_id': '2', 'movie_title': 'Short Film', 'showing_time': '11:50'},
        # Gap: 10min (< 150min threshold) -> ends at 13:30
        {'bfi_showing_id': '3', 'movie_title': 'Short Film', 'showing_time': '13:40'},
        # Gap: 10min (< 150min threshold) -> ends at 15:20
        {'bfi_showing_id': '4', 'movie_title': 'Short Film', 'showing_time': '15:30'},
        # Gap: 10min -> ends at 17:10
        {'bfi_showing_id': '5', 'movie_title': 'Short Film', 'showing_time': '17:20'},
        # Gap: 10min -> ends at 19:00
        {'bfi_showing_id': '6', 'movie_title': 'Short Film', 'showing_time': '19:10'},
        # Gap: 10min -> ends at 20:50
        {'bfi_showing_id': '7', 'movie_title': 'Short Film', 'showing_time': '21:00'},
        # Ends at 22:40 (after 22:00 threshold)
    ]

    result = checker.is_complete('2025-10-26', showings)
    assert result is True  # All gaps < 150min threshold, ends after 22:00


def test_multiple_gaps(checker, db):
    """Test day with multiple gaps, one large."""
    # Cache runtimes
    db.cache_runtime('Film A', 90, 'test')
    db.cache_runtime('Film B', 90, 'test')
    db.cache_runtime('Film C', 90, 'test')

    showings = [
        {'bfi_showing_id': '1', 'movie_title': 'Film A', 'showing_time': '10:00'},
        # Small gap
        {'bfi_showing_id': '2', 'movie_title': 'Film B', 'showing_time': '12:30'},
        # LARGE gap (should trigger incomplete)
        {'bfi_showing_id': '3', 'movie_title': 'Film C', 'showing_time': '20:00'},
    ]

    result = checker.is_complete('2025-10-26', showings)
    assert result is False  # One large gap is enough


def test_config_customization():
    """Test that custom config values are used."""
    custom_config = CompletionConfig()
    custom_config.MIN_SLOT_GAP_MINUTES = 200  # Custom threshold
    custom_config.LATE_START_HOUR = 12  # Custom start threshold

    db_path = ":memory:"
    db = Database(db_path)
    runtime_fetcher = RuntimeFetcher(db)
    checker = CompletionChecker(runtime_fetcher, custom_config)

    assert checker.config.MIN_SLOT_GAP_MINUTES == 200
    assert checker.config.LATE_START_HOUR == 12
