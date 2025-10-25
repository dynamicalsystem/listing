"""
Tests for BFI IMAX parser module
"""
import pytest
from pathlib import Path

from dynamicalsystem.listing.scraper.parse import (
    parse_search_results,
    extract_performance_days,
    has_results,
    parse_format_keywords,
    build_detail_url,
)


# Fixtures for test data
@pytest.fixture
def sample_html_with_results():
    """Load sample HTML with 4 showings from Oct 26"""
    fixture_path = Path(__file__).parent.parent / "experiments" / "bfi_cloudscraper_2025-10-26.html"
    return fixture_path.read_text(encoding='utf-8')


@pytest.fixture
def sample_html_no_results():
    """Load sample HTML with no results from Oct 27"""
    fixture_path = Path(__file__).parent.parent / "experiments" / "bfi_no_results_2025-10-27.html"
    return fixture_path.read_text(encoding='utf-8')


class TestParseSearchResults:
    """Test parse_search_results function"""

    def test_parse_oct26_showings(self, sample_html_with_results):
        """Test parsing 4 showings from Oct 26 sample"""
        results = parse_search_results(sample_html_with_results)

        assert len(results) == 4, "Should extract 4 showings from Oct 26 HTML"

        # Verify first showing (Frankenstein)
        first = results[0]
        assert first['movie_title'] == 'Frankenstein'
        assert first['showing_date'] == '2025-10-26'
        assert first['showing_time'] == '10:45'
        assert 'IMAX with Laser' in first['format_keywords']

    def test_parse_no_results(self, sample_html_no_results):
        """Test parsing page with no showings"""
        results = parse_search_results(sample_html_no_results)

        assert results == [], "Should return empty list for no results"

    def test_parse_invalid_html(self):
        """Test handling of invalid HTML"""
        results = parse_search_results("")
        assert results == []

        results = parse_search_results("<html></html>")
        assert results == []

    def test_month_conversion(self, sample_html_with_results):
        """Test 0-indexed month is converted to 1-indexed"""
        results = parse_search_results(sample_html_with_results)

        # October should be month 10, not 9
        for showing in results:
            if showing['showing_date']:
                month = int(showing['showing_date'].split('-')[1])
                assert month == 10, f"October should be month 10, got {month}"

    def test_all_required_fields_present(self, sample_html_with_results):
        """Test that all expected fields are present in parsed results"""
        results = parse_search_results(sample_html_with_results)

        required_fields = [
            'id', 'movie_title', 'movie_slug', 'showing_datetime',
            'showing_date', 'showing_time', 'format_keywords',
            'detail_url_path', 'availability_status', 'availability_count', 'rating'
        ]

        for showing in results:
            for field in required_fields:
                assert field in showing, f"Field '{field}' missing from showing"


class TestExtractPerformanceDays:
    """Test extract_performance_days function"""

    def test_extract_from_oct26(self, sample_html_with_results):
        """Test extracting unique dates from performanceDays array"""
        dates = extract_performance_days(sample_html_with_results)

        # From OBSERVE docs: 23 unique dates across 267-day span
        assert len(dates) >= 20, "Should extract at least 20 unique dates"
        assert '2025-10-26' in dates, "Should include Oct 26"
        assert '2025-11-12' in dates, "Should include Nov 12"

    def test_dates_format(self, sample_html_with_results):
        """Test that dates are in YYYY-MM-DD format"""
        dates = extract_performance_days(sample_html_with_results)

        for date in dates:
            parts = date.split('-')
            assert len(parts) == 3, f"Date {date} should have 3 parts"
            assert len(parts[0]) == 4, f"Year should be 4 digits in {date}"
            assert len(parts[1]) == 2, f"Month should be 2 digits in {date}"
            assert len(parts[2]) == 2, f"Day should be 2 digits in {date}"

    def test_no_results_page(self, sample_html_no_results):
        """Test extracting from page with no results"""
        dates = extract_performance_days(sample_html_no_results)

        # No results page may still have performanceDays array
        assert isinstance(dates, set)


class TestHasResults:
    """Test has_results quick check function"""

    def test_has_results_true(self, sample_html_with_results):
        """Test detecting page with results"""
        assert has_results(sample_html_with_results) is True

    def test_has_results_false(self, sample_html_no_results):
        """Test detecting page without results"""
        assert has_results(sample_html_no_results) is False

    def test_has_results_empty(self):
        """Test with empty/invalid HTML"""
        assert has_results("") is False
        assert has_results("<html></html>") is False


class TestParseFormatKeywords:
    """Test parse_format_keywords helper function"""

    def test_parse_3d_laser(self):
        """Test parsing 3D and Laser keywords"""
        result = parse_format_keywords("IMAX with Laser,3D")

        assert result['is_3d'] is True
        assert result['is_laser'] is True
        assert result['is_70mm'] is False
        assert result['has_subtitles'] is False

    def test_parse_70mm(self):
        """Test parsing 70mm keywords"""
        result = parse_format_keywords("imax,70mm")

        assert result['is_70mm'] is True
        assert result['is_3d'] is False

    def test_parse_subtitles(self):
        """Test parsing subtitle keywords"""
        result = parse_format_keywords("English subtitles,IMAX with Laser")

        assert result['has_subtitles'] is True
        assert result['is_laser'] is True

    def test_case_insensitive(self):
        """Test that parsing is case-insensitive"""
        result1 = parse_format_keywords("3D,LASER")
        result2 = parse_format_keywords("3d,laser")

        assert result1 == result2


class TestBuildDetailUrl:
    """Test build_detail_url helper function"""

    def test_build_url(self):
        """Test building full URL from relative path"""
        path = "default.asp?doWork::WScontent::loadArticle=Load&BOparam=123"
        url = build_detail_url(path)

        assert url.startswith("https://whatson.bfi.org.uk/imax/Online/")
        assert path in url

    def test_url_format(self):
        """Test URL is properly formatted"""
        path = "test.asp"
        url = build_detail_url(path)

        assert url == "https://whatson.bfi.org.uk/imax/Online/test.asp"
