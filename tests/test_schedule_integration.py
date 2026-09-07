"""Integration tests for ScheduleManager with full component stack.

Tests the complete workflow from horizon scanning through change detection
to completion status, with all dependencies wired together.
"""

import pytest
from unittest.mock import Mock, MagicMock
from dynamicalsystem.listing.scraper.schedule import ScheduleManager
from dynamicalsystem.listing.scraper.changes import ChangeDetector
from dynamicalsystem.listing.scraper.completion import CompletionChecker
from dynamicalsystem.listing.scraper.runtime import RuntimeFetcher
from dynamicalsystem.listing.scraper.fetch import BFIFetcher
from dynamicalsystem.listing.storage.db import Database


@pytest.fixture
def db(tmp_path):
    """Create temporary database."""
    db_path = str(tmp_path / "test.db")
    return Database(db_path)


@pytest.fixture
def mock_fetcher():
    """Create mock BFI fetcher."""
    return Mock(spec=BFIFetcher)


@pytest.fixture
def runtime_fetcher(db):
    """Create runtime fetcher."""
    return RuntimeFetcher(db)


@pytest.fixture
def change_detector(db):
    """Create change detector."""
    return ChangeDetector(db)


@pytest.fixture
def completion_checker(runtime_fetcher):
    """Create completion checker."""
    return CompletionChecker(runtime_fetcher)


@pytest.fixture
def manager(db, mock_fetcher, runtime_fetcher, change_detector, completion_checker):
    """Create fully-wired ScheduleManager."""
    return ScheduleManager(
        db=db,
        fetcher=mock_fetcher,
        runtime_fetcher=runtime_fetcher,
        change_detector=change_detector,
        completion_checker=completion_checker
    )


def create_html_with_performance_days(dates):
    """Create mock HTML with performanceDays array."""
    date_entries = ',\n'.join([
        f'["{date}T10:00:00.000", "1"]' for date in dates
    ])
    # Add padding to make HTML realistic size
    padding = '<!-- Padding ' + ('x' * 5000) + ' -->'
    return f'''
<!DOCTYPE html>
<html>
<head><title>BFI IMAX Listings</title></head>
<body>
{padding}
<script>
var performanceDays = [{{
    values: [
        {date_entries}
    ]
}}];
</script>
</body>
</html>
    '''


def create_html_with_showings(showings):
    """Create mock HTML with searchResults array."""
    if not showings:
        return '''
<!DOCTYPE html>
<html>
<head><title>No Results</title></head>
<body>
<div>No results found for this date</div>
''' + ('<!-- Padding ' + ('x' * 5000) + ' -->') + '''
</body>
</html>
        '''

    results = []
    for s in showings:
        # Create searchResults array entry (90+ fields, we use key indices)
        result = [''] * 50  # Initialize array
        result[0] = s['bfi_showing_id']
        result[1] = 'P'
        result[2] = 'IMAX'
        result[3] = 'category'
        result[4] = s.get('movie_slug', 'slug')
        result[5] = s['movie_title']
        result[6] = 'description'
        result[7] = s['showing_datetime_utc']
        result[8] = s['showing_time']
        result[9] = s['showing_date'].split('-')[2]  # day
        result[10] = str(int(s['showing_date'].split('-')[1]) - 1)  # month (0-indexed)
        result[11] = s['showing_date'].split('-')[0]  # year
        result[15] = s.get('availability_status', 'G')
        result[16] = s.get('availability_count', 100)
        result[17] = s.get('format_keywords', '')
        result[18] = s.get('detail_url_path', 'detail.asp')
        result[42] = s.get('bfi_performance_id', 'perf1')
        result[43] = s.get('rating', 'PG')

        # Convert to JSON array string
        json_result = '[' + ','.join([f'"{v}"' if isinstance(v, str) else str(v) for v in result]) + ']'
        results.append(json_result)

    results_str = ',\n'.join(results)

    # Also include performanceDays for horizon scanning
    dates = list(set([s['showing_date'] for s in showings]))
    perf_days = create_html_with_performance_days(dates)

    # Make HTML large enough to pass parser validation
    padding = '<!-- Padding ' + ('x' * 5000) + ' -->'

    return f'''
<!DOCTYPE html>
<html>
<head><title>BFI IMAX Listings</title></head>
<body>
{perf_days}
<div id="content">
{padding}
<script>
var filmData = {{
    searchResults: [
        {results_str}
    ]
}};
</script>
</div>
</body>
</html>
    '''


class TestHorizonScanning:
    """Test horizon scanning and date discovery."""

    def test_initial_horizon_scan(self, manager, mock_fetcher):
        """Test first-time horizon scan discovers dates."""
        # Mock HTML with 3 dates
        mock_fetcher.fetch.return_value = create_html_with_performance_days([
            '2025-10-26', '2025-10-28', '2025-11-01'
        ])

        result = manager.update_horizon()

        assert len(result.dates_discovered) == 3
        assert '2025-10-26' in result.dates_discovered
        assert '2025-10-28' in result.dates_discovered
        assert '2025-11-01' in result.dates_discovered
        assert len(result.new_dates) == 3  # All new
        assert len(result.removed_dates) == 0

    def test_horizon_scan_detects_new_dates(self, manager, mock_fetcher, db):
        """Test horizon scan detects newly added dates."""
        # Initial scan with 2 dates
        mock_fetcher.fetch.return_value = create_html_with_performance_days([
            '2025-10-26', '2025-10-28'
        ])
        manager.update_horizon()

        # Second scan with additional date
        mock_fetcher.fetch.return_value = create_html_with_performance_days([
            '2025-10-26', '2025-10-28', '2025-11-01'
        ])
        result = manager.update_horizon()

        assert len(result.new_dates) == 1
        assert '2025-11-01' in result.new_dates

    def test_horizon_scan_detects_removed_dates(self, manager, mock_fetcher, db):
        """Test horizon scan detects dates that disappeared."""
        # Initial scan with 3 dates
        mock_fetcher.fetch.return_value = create_html_with_performance_days([
            '2025-10-26', '2025-10-28', '2025-11-01'
        ])
        manager.update_horizon()

        # Mark one as partial (tracked)
        db.update_scrape_schedule(
            date='2025-11-01',
            status='partial',
            showing_count=1,
            is_complete=False
        )

        # Second scan with removed date
        mock_fetcher.fetch.return_value = create_html_with_performance_days([
            '2025-10-26', '2025-10-28'
        ])

        # Mock verification fetch returns no results
        def fetch_side_effect(date):
            if date == '2025-11-01':
                return '<div>No results</div>'
            return create_html_with_performance_days(['2025-10-26', '2025-10-28'])

        mock_fetcher.fetch.side_effect = fetch_side_effect

        result = manager.update_horizon()

        assert '2025-11-01' in result.removed_dates


class TestDateScraping:
    """Test scraping individual dates."""

    def test_scrape_date_first_time(self, manager, mock_fetcher, db):
        """Test scraping a date for the first time."""
        showings = [
            {
                'bfi_showing_id': '1',
                'movie_title': 'Test Film',
                'movie_slug': 'test-film',
                'rating': 'PG',
                'showing_date': '2025-10-26',
                'showing_time': '10:00',
                'showing_datetime_utc': '2025-10-26T09:00:00+00:00',
                'showing_datetime_display': 'Sat 26 Oct 10:00',
                'format_keywords': 'IMAX',
                'detail_url_path': 'detail.asp?id=1',
                'availability_status': 'G',
                'availability_count': 150,
            }
        ]

        mock_fetcher.fetch.return_value = create_html_with_showings(showings)

        result = manager.scrape_date('2025-10-26')

        assert result.date == '2025-10-26'
        assert result.showing_count == 1
        assert len(result.changes_detected) == 1
        assert result.changes_detected[0].change_type == 'first_seen'
        assert result.status in ['partial', 'complete']

    def test_scrape_date_with_changes(self, manager, mock_fetcher, db):
        """Test scraping detects changes from previous."""
        # Initial scrape
        initial_showings = [
            {
                'bfi_showing_id': '1',
                'movie_title': 'Film A',
                'movie_slug': 'film-a',
                'rating': 'PG',
                'showing_date': '2025-10-26',
                'showing_time': '10:00',
                'showing_datetime_utc': '2025-10-26T09:00:00+00:00',
                'showing_datetime_display': 'Sat 26 Oct 10:00',
                'format_keywords': 'IMAX',
                'detail_url_path': 'detail.asp?id=1',
                'availability_status': 'G',
                'availability_count': 150,
            }
        ]

        mock_fetcher.fetch.return_value = create_html_with_showings(initial_showings)
        manager.scrape_date('2025-10-26')

        # Second scrape with additional showing
        updated_showings = initial_showings + [
            {
                'bfi_showing_id': '2',
                'movie_title': 'Film B',
                'movie_slug': 'film-b',
                'rating': '12A',
                'showing_date': '2025-10-26',
                'showing_time': '14:00',
                'showing_datetime_utc': '2025-10-26T13:00:00+00:00',
                'showing_datetime_display': 'Sat 26 Oct 14:00',
                'format_keywords': '3D',
                'detail_url_path': 'detail.asp?id=2',
                'availability_status': 'G',
                'availability_count': 200,
            }
        ]

        mock_fetcher.fetch.return_value = create_html_with_showings(updated_showings)
        result = manager.scrape_date('2025-10-26')

        assert result.showing_count == 2
        assert len(result.changes_detected) == 1
        assert result.changes_detected[0].change_type == 'added'
        assert result.changes_detected[0].movie_title == 'Film B'

    def test_scrape_empty_date(self, manager, mock_fetcher, db):
        """Test scraping a date with no showings."""
        mock_fetcher.fetch.return_value = '<div>No results</div>'

        result = manager.scrape_date('2025-10-27')

        assert result.showing_count == 0
        assert result.status == 'empty'
        assert result.is_complete is True
        assert len(result.changes_detected) == 0


class TestCompletionDetection:
    """Test completion status detection with runtime data."""

    def test_complete_schedule_detected(self, manager, mock_fetcher, db):
        """Test that complete schedule is marked as complete."""
        # Cache runtimes first
        db.cache_runtime('Film A', 120, 'test')
        db.cache_runtime('Film B', 120, 'test')
        db.cache_runtime('Film C', 120, 'test')
        db.cache_runtime('Film D', 120, 'test')

        showings = [
            {
                'bfi_showing_id': '1',
                'movie_title': 'Film A',
                'movie_slug': 'film-a',
                'rating': 'PG',
                'showing_date': '2025-10-26',
                'showing_time': '10:00',
                'showing_datetime_utc': '2025-10-26T09:00:00+00:00',
                'showing_datetime_display': 'Sat 26 Oct 10:00',
                'format_keywords': 'IMAX',
                'detail_url_path': 'detail.asp?id=1',
                'availability_status': 'G',
                'availability_count': 150,
            },
            {
                'bfi_showing_id': '2',
                'movie_title': 'Film B',
                'movie_slug': 'film-b',
                'rating': 'PG',
                'showing_date': '2025-10-26',
                'showing_time': '12:45',
                'showing_datetime_utc': '2025-10-26T11:45:00+00:00',
                'showing_datetime_display': 'Sat 26 Oct 12:45',
                'format_keywords': 'IMAX',
                'detail_url_path': 'detail.asp?id=2',
                'availability_status': 'G',
                'availability_count': 150,
            },
            {
                'bfi_showing_id': '3',
                'movie_title': 'Film C',
                'movie_slug': 'film-c',
                'rating': 'PG',
                'showing_date': '2025-10-26',
                'showing_time': '15:30',
                'showing_datetime_utc': '2025-10-26T14:30:00+00:00',
                'showing_datetime_display': 'Sat 26 Oct 15:30',
                'format_keywords': 'IMAX',
                'detail_url_path': 'detail.asp?id=3',
                'availability_status': 'G',
                'availability_count': 150,
            },
            {
                'bfi_showing_id': '4',
                'movie_title': 'Film D',
                'movie_slug': 'film-d',
                'rating': 'PG',
                'showing_date': '2025-10-26',
                'showing_time': '19:30',
                'showing_datetime_utc': '2025-10-26T18:30:00+00:00',
                'showing_datetime_display': 'Sat 26 Oct 19:30',
                'format_keywords': 'IMAX',
                'detail_url_path': 'detail.asp?id=4',
                'availability_status': 'G',
                'availability_count': 150,
            },
        ]

        mock_fetcher.fetch.return_value = create_html_with_showings(showings)
        result = manager.scrape_date('2025-10-26')

        assert result.is_complete is True
        assert result.status == 'complete'

    def test_partial_schedule_detected(self, manager, mock_fetcher, db):
        """Test that partial schedule is marked as partial."""
        # Cache runtime
        db.cache_runtime('Film A', 90, 'test')

        showings = [
            {
                'bfi_showing_id': '1',
                'movie_title': 'Film A',
                'movie_slug': 'film-a',
                'rating': 'PG',
                'showing_date': '2025-10-26',
                'showing_time': '12:00',  # Late start
                'showing_datetime_utc': '2025-10-26T11:00:00+00:00',
                'showing_datetime_display': 'Sat 26 Oct 12:00',
                'format_keywords': 'IMAX',
                'detail_url_path': 'detail.asp?id=1',
                'availability_status': 'G',
                'availability_count': 150,
            },
        ]

        mock_fetcher.fetch.return_value = create_html_with_showings(showings)
        result = manager.scrape_date('2025-10-26')

        assert result.is_complete is False
        assert result.status == 'partial'


class TestGetDatesToScrape:
    """Test date prioritization logic."""

    def test_get_dates_to_scrape_excludes_complete(self, manager, mock_fetcher, db):
        """Test that complete dates are excluded."""
        # Setup: add some dates
        db.add_to_scrape_schedule('2025-10-26', 'partial', '2025-10-25T00:00:00+00:00')
        db.add_to_scrape_schedule('2025-10-27', 'complete', '2025-10-25T00:00:00+00:00')
        db.add_to_scrape_schedule('2025-10-28', 'unknown', '2025-10-25T00:00:00+00:00')

        dates = manager.get_dates_to_scrape()

        assert '2025-10-26' in dates
        assert '2025-10-27' not in dates  # Complete, excluded
        assert '2025-10-28' in dates

    def test_get_dates_to_scrape_empty_schedule(self, manager, db):
        """Test with no scheduled dates."""
        dates = manager.get_dates_to_scrape()
        assert dates == []


class TestFullWorkflow:
    """Test complete end-to-end workflows."""

    def test_daily_workflow_simulation(self, manager, mock_fetcher, db):
        """Simulate a daily scraping workflow."""
        # upcoming_showings filters on date('now'), so use dates relative to today
        from datetime import date, timedelta
        date_a = (date.today() + timedelta(days=7)).isoformat()
        date_b = (date.today() + timedelta(days=9)).isoformat()

        # Cache some runtimes
        db.cache_runtime('Film A', 120, 'test')
        db.cache_runtime('Film B', 120, 'test')

        # Step 1: Horizon scan
        mock_fetcher.fetch.return_value = create_html_with_performance_days([
            date_a, date_b
        ])
        horizon_result = manager.update_horizon()

        assert len(horizon_result.new_dates) == 2

        # Step 2: Get dates to scrape
        dates_to_scrape = manager.get_dates_to_scrape()
        assert len(dates_to_scrape) == 2

        # Step 3: Scrape each date
        showings_date_a = [
            {
                'bfi_showing_id': '1',
                'movie_title': 'Film A',
                'movie_slug': 'film-a',
                'rating': 'PG',
                'showing_date': date_a,
                'showing_time': '10:00',
                'showing_datetime_utc': f'{date_a}T09:00:00+00:00',
                'showing_datetime_display': f'{date_a} 10:00',
                'format_keywords': 'IMAX',
                'detail_url_path': 'detail.asp?id=1',
                'availability_status': 'G',
                'availability_count': 150,
            },
        ]

        showings_date_b = [
            {
                'bfi_showing_id': '2',
                'movie_title': 'Film B',
                'movie_slug': 'film-b',
                'rating': '12A',
                'showing_date': date_b,
                'showing_time': '14:00',
                'showing_datetime_utc': f'{date_b}T13:00:00+00:00',
                'showing_datetime_display': f'{date_b} 14:00',
                'format_keywords': '3D',
                'detail_url_path': 'detail.asp?id=2',
                'availability_status': 'G',
                'availability_count': 200,
            },
        ]

        def fetch_by_date(fetch_date):
            if fetch_date == date_a:
                return create_html_with_showings(showings_date_a)
            elif fetch_date == date_b:
                return create_html_with_showings(showings_date_b)
            return create_html_with_performance_days([date_a, date_b])

        mock_fetcher.fetch.side_effect = fetch_by_date

        results = []
        for date in dates_to_scrape:
            result = manager.scrape_date(date)
            results.append(result)

        assert len(results) == 2
        assert all(r.showing_count >= 1 for r in results)

        # Verify database state
        schedule_status_a = db.get_schedule_status(date_a)
        assert schedule_status_a is not None
        assert schedule_status_a['status'] in ['partial', 'complete']

        # Verify listings in database
        upcoming = db.get_upcoming_showings()
        assert len(upcoming) == 2
