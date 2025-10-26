"""Tests for runtime fetcher module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
import responses

from dynamicalsystem.listing.scraper.runtime import RuntimeFetcher, RuntimeResult
from dynamicalsystem.listing.storage.db import Database
from dynamicalsystem.listing.storage.schema import init_database


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def db():
    """Create temporary test database."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    init_database(db_path)
    database = Database(db_path)

    yield database

    # Cleanup
    Path(db_path).unlink()


@pytest.fixture
def fetcher(db):
    """Create RuntimeFetcher instance."""
    return RuntimeFetcher(db)


@pytest.fixture
def fixtures_dir():
    """Get fixtures directory path."""
    return Path(__file__).parent / 'fixtures'


def load_fixture(filename):
    """Load HTML fixture file."""
    fixtures_dir = Path(__file__).parent / 'fixtures'
    return (fixtures_dir / filename).read_text()


# -------------------------------------------------------------------------
# Cache Tests
# -------------------------------------------------------------------------

def test_get_runtime_cache_hit(fetcher, db):
    """Test cache hit returns immediately."""
    # Pre-populate cache
    db.cache_runtime('Interstellar', 169, 'Wikipedia')

    # Should return cached value without any HTTP requests
    runtime = fetcher.get_runtime('Interstellar')

    assert runtime == 169


def test_get_runtime_cache_miss_triggers_fetch(fetcher):
    """Test cache miss triggers fetch attempts."""
    with patch.object(fetcher, '_fetch_from_wikipedia', return_value=RuntimeResult(150, 'Wikipedia')):
        runtime = fetcher.get_runtime('Frankenstein')

        assert runtime == 150


# -------------------------------------------------------------------------
# Wikipedia Extraction Tests
# -------------------------------------------------------------------------

def test_extract_runtime_from_wikipedia_minutes(fetcher):
    """Test extracting runtime in minutes format."""
    html = load_fixture('wikipedia_interstellar.html')

    runtime = fetcher._extract_runtime_from_wikipedia_html(html)

    assert runtime == 169


def test_extract_runtime_from_wikipedia_hours(fetcher):
    """Test extracting runtime in hours format."""
    html = load_fixture('wikipedia_oppenheimer.html')

    runtime = fetcher._extract_runtime_from_wikipedia_html(html)

    assert runtime == 180  # 3 hours = 180 minutes


def test_extract_runtime_from_wikipedia_not_found(fetcher):
    """Test extracting runtime from page without runtime info."""
    html = "<html><body><p>No runtime here</p></body></html>"

    runtime = fetcher._extract_runtime_from_wikipedia_html(html)

    assert runtime is None


# -------------------------------------------------------------------------
# Title Normalization Tests
# -------------------------------------------------------------------------

def test_normalize_title_basic(fetcher):
    """Test basic title normalization."""
    normalized = fetcher._normalize_title('Interstellar')

    assert normalized == 'Interstellar'


def test_normalize_title_removes_imax_suffix(fetcher):
    """Test removing IMAX format suffix."""
    normalized = fetcher._normalize_title('Nosferatu - The IMAX 2D Experience')

    assert normalized == 'Nosferatu'


def test_normalize_title_removes_3d_suffix(fetcher):
    """Test removing 3D format suffix."""
    normalized = fetcher._normalize_title('Avatar - 3D IMAX')

    assert normalized == 'Avatar'


def test_normalize_title_removes_qanda(fetcher):
    """Test removing Q&A suffix."""
    normalized = fetcher._normalize_title('Frankenstein + Q&A')

    assert normalized == 'Frankenstein'


def test_normalize_title_spaces_to_underscores(fetcher):
    """Test spaces converted to underscores."""
    normalized = fetcher._normalize_title('The Dark Knight')

    assert normalized == 'The_Dark_Knight'


def test_normalize_title_removes_special_chars(fetcher):
    """Test removing special characters."""
    normalized = fetcher._normalize_title('Film: Special Edition!')

    assert normalized == 'Film_Special_Edition'


# -------------------------------------------------------------------------
# Integration Tests
# -------------------------------------------------------------------------

@responses.activate
def test_get_runtime_wikipedia_success_caches_result(fetcher, db):
    """Test successful Wikipedia fetch caches result."""
    html = load_fixture('wikipedia_interstellar.html')

    responses.add(
        responses.GET,
        'https://en.wikipedia.org/wiki/Interstellar_(film)',
        body=html,
        status=200
    )

    # First call should fetch and cache
    runtime = fetcher.get_runtime('Interstellar')
    assert runtime == 169

    # Verify it's cached
    cached = db.get_runtime('Interstellar')
    assert cached == 169


@responses.activate
def test_get_runtime_tries_multiple_wikipedia_urls(fetcher):
    """Test trying multiple Wikipedia URL patterns."""
    # First URL returns 404
    responses.add(
        responses.GET,
        'https://en.wikipedia.org/wiki/Nosferatu_(film)',
        status=404
    )

    # Second URL succeeds
    html = load_fixture('wikipedia_interstellar.html')
    responses.add(
        responses.GET,
        'https://en.wikipedia.org/wiki/Nosferatu',
        body=html,
        status=200
    )

    runtime = fetcher.get_runtime('Nosferatu')

    assert runtime == 169


def test_get_runtime_returns_none_when_not_found(fetcher):
    """Test returns None when runtime not found anywhere."""
    with patch.object(fetcher, '_fetch_from_wikipedia', return_value=None):
        runtime = fetcher.get_runtime('Unknown Film')

        assert runtime is None


# -------------------------------------------------------------------------
# Rate Limiting Tests
# -------------------------------------------------------------------------

def test_rate_limit_wikipedia(fetcher):
    """Test Wikipedia rate limiting enforces delay."""
    import time

    fetcher._last_wikipedia_request = time.time()
    fetcher._wikipedia_delay = 0.1  # Short delay for test

    start = time.time()
    fetcher._rate_limit_wikipedia()
    elapsed = time.time() - start

    assert elapsed >= 0.1  # Should have slept


def test_rate_limit_wikipedia_no_delay_when_enough_time_passed(fetcher):
    """Test no delay when enough time has passed."""
    import time

    fetcher._last_wikipedia_request = time.time() - 2.0  # 2 seconds ago
    fetcher._wikipedia_delay = 1.0

    start = time.time()
    fetcher._rate_limit_wikipedia()
    elapsed = time.time() - start

    assert elapsed < 0.01  # Should not have slept
