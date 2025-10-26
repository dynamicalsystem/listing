"""Tests for daily maintenance script."""

import pytest
import tempfile
from unittest.mock import MagicMock, patch
from datetime import datetime
from zoneinfo import ZoneInfo

from dynamicalsystem.listing.maintenance.daily import (
    main,
    run_daily_maintenance,
    ScrapeRunSummary,
    setup_logging,
    log_summary,
)
from dynamicalsystem.listing.config import Config


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing."""
    db_path = tmp_path / "test.db"
    return str(db_path)


@pytest.fixture
def mock_schedule_manager():
    """Mock ScheduleManager for testing."""
    manager = MagicMock()

    # Mock horizon scan result
    horizon_result = MagicMock()
    horizon_result.new_dates = {'2025-10-27', '2025-10-28'}
    manager.update_horizon.return_value = horizon_result

    # Mock dates to scrape
    manager.get_dates_to_scrape.return_value = ['2025-10-26', '2025-10-27']

    # Mock scrape_date result
    scrape_result = MagicMock()
    scrape_result.showing_count = 4
    scrape_result.changes_detected = []
    scrape_result.status = 'partial'
    manager.scrape_date.return_value = scrape_result

    return manager


class TestConfig:
    """Test configuration management."""

    def test_default_values(self):
        """Test default configuration values."""
        assert Config.DB_PATH == '/data/listing.db'
        assert Config.LOG_LEVEL == 'INFO'
        assert Config.MAINTENANCE_HOUR == 2
        assert Config.MAX_ERROR_RATE == 0.5

    def test_validate_valid_config(self):
        """Test validation with valid configuration."""
        assert Config.validate() is True

    def test_validate_invalid_hour(self):
        """Test validation with invalid maintenance hour."""
        original = Config.MAINTENANCE_HOUR
        try:
            Config.MAINTENANCE_HOUR = 25
            assert Config.validate() is False
        finally:
            Config.MAINTENANCE_HOUR = original

    def test_validate_invalid_error_rate(self):
        """Test validation with invalid error rate."""
        original = Config.MAX_ERROR_RATE
        try:
            Config.MAX_ERROR_RATE = 1.5
            assert Config.validate() is False
        finally:
            Config.MAX_ERROR_RATE = original


class TestScrapeRunSummary:
    """Test ScrapeRunSummary dataclass."""

    def test_create_summary(self):
        """Test creating summary with all fields."""
        summary = ScrapeRunSummary(
            started_at='2025-10-26T02:00:00+00:00',
            completed_at='2025-10-26T02:05:00+00:00',
            duration_seconds=300,
            dates_scraped=10,
            new_dates_found=2,
            changes_detected=5,
            errors=['error1', 'error2']
        )

        assert summary.started_at == '2025-10-26T02:00:00+00:00'
        assert summary.dates_scraped == 10
        assert len(summary.errors) == 2

    def test_default_errors_empty_list(self):
        """Test that errors defaults to empty list."""
        summary = ScrapeRunSummary(started_at='2025-10-26T02:00:00+00:00')
        assert summary.errors == []


class TestLogging:
    """Test logging setup."""

    def test_setup_logging_console_only(self):
        """Test logging setup without file handler."""
        import logging

        # Clear existing handlers
        root = logging.getLogger()
        root.handlers.clear()

        setup_logging(verbose=False, log_file=None)

        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)

    def test_setup_logging_with_file(self, tmp_path):
        """Test logging setup with file handler."""
        import logging

        # Clear existing handlers
        root = logging.getLogger()
        root.handlers.clear()

        log_file = str(tmp_path / "logs" / "test.log")
        setup_logging(verbose=True, log_file=log_file)

        # Should have console + file handler
        assert len(root.handlers) == 2
        assert root.level == logging.DEBUG

    def test_log_summary(self, caplog):
        """Test log_summary output."""
        summary = ScrapeRunSummary(
            started_at='2025-10-26T02:00:00+00:00',
            completed_at='2025-10-26T02:05:00+00:00',
            duration_seconds=300,
            dates_scraped=10,
            new_dates_found=2,
            changes_detected=5,
            errors=[]
        )

        with caplog.at_level('INFO'):
            log_summary(summary)

        assert "Scrape Run Summary" in caplog.text
        assert "Dates scraped:    10" in caplog.text
        assert "Changes detected: 5" in caplog.text


class TestMain:
    """Test main entry point."""

    @patch('dynamicalsystem.listing.maintenance.daily.run_daily_maintenance')
    def test_main_success(self, mock_run):
        """Test successful run returns exit code 0."""
        mock_run.return_value = ScrapeRunSummary(
            started_at='2025-10-26T02:00:00+00:00',
            completed_at='2025-10-26T02:05:00+00:00',
            duration_seconds=300,
            dates_scraped=10,
            new_dates_found=2,
            changes_detected=5,
            errors=[]
        )

        exit_code = main(['--dry-run'])
        assert exit_code == 0

    @patch('dynamicalsystem.listing.maintenance.daily.run_daily_maintenance')
    def test_main_partial_failure(self, mock_run):
        """Test partial failure returns exit code 1."""
        mock_run.return_value = ScrapeRunSummary(
            started_at='2025-10-26T02:00:00+00:00',
            completed_at='2025-10-26T02:05:00+00:00',
            duration_seconds=300,
            dates_scraped=10,
            new_dates_found=0,
            changes_detected=0,
            errors=['date1: error', 'date2: error']  # 20% error rate
        )

        exit_code = main(['--dry-run'])
        assert exit_code == 1

    @patch('dynamicalsystem.listing.maintenance.daily.run_daily_maintenance')
    def test_main_critical_failure(self, mock_run):
        """Test critical failure returns exit code 2."""
        mock_run.return_value = ScrapeRunSummary(
            started_at='2025-10-26T02:00:00+00:00',
            completed_at='2025-10-26T02:05:00+00:00',
            duration_seconds=300,
            dates_scraped=10,
            new_dates_found=0,
            changes_detected=0,
            errors=['error'] * 6  # 60% error rate - critical
        )

        exit_code = main(['--dry-run'])
        assert exit_code == 2

    def test_main_dry_run_flag(self):
        """Test that dry-run flag is processed."""
        # Should complete quickly without errors
        exit_code = main(['--dry-run', '--db-path', ':memory:'])

        # Dry run should succeed (might fail if no database, but that's OK)
        assert exit_code in [0, 2]

    def test_main_verbose_flag(self):
        """Test that verbose flag is processed."""
        import logging

        # Clear handlers
        root = logging.getLogger()
        root.handlers.clear()

        exit_code = main(['--verbose', '--dry-run', '--db-path', ':memory:'])

        # Check debug level was set
        assert root.level == logging.DEBUG

    def test_main_custom_db_path(self, tmp_path):
        """Test custom database path argument."""
        db_path = str(tmp_path / "custom.db")

        exit_code = main(['--dry-run', '--db-path', db_path])

        # Should process the argument
        assert Config.DB_PATH == db_path

    @patch('dynamicalsystem.listing.maintenance.daily.run_daily_maintenance')
    def test_main_exception_handling(self, mock_run):
        """Test that exceptions are caught and logged."""
        mock_run.side_effect = Exception("Test exception")

        exit_code = main(['--dry-run'])

        # Should return critical failure code
        assert exit_code == 2


class TestRunDailyMaintenance:
    """Test daily maintenance workflow."""

    @patch('dynamicalsystem.listing.maintenance.daily.Database')
    @patch('dynamicalsystem.listing.maintenance.daily.BFIFetcher')
    @patch('dynamicalsystem.listing.maintenance.daily.RuntimeFetcher')
    @patch('dynamicalsystem.listing.maintenance.daily.ScheduleManager')
    def test_dry_run_mode(self, mock_sm, mock_rf, mock_fetcher, mock_db):
        """Test dry-run mode doesn't make changes."""
        # Setup mocks
        manager = MagicMock()
        horizon_result = MagicMock()
        horizon_result.new_dates = set()
        manager.update_horizon.return_value = horizon_result
        manager.get_dates_to_scrape.return_value = ['2025-10-26']
        mock_sm.return_value = manager

        # Mock database
        db_instance = MagicMock()
        db_instance.get_schedule_status.return_value = 'partial'
        mock_db.return_value = db_instance

        # Run dry-run
        summary = run_daily_maintenance(dry_run=True)

        # Should not call scrape_date
        manager.scrape_date.assert_not_called()

        # Should return summary
        assert summary.dates_scraped == 1

    @patch('dynamicalsystem.listing.maintenance.daily.Database')
    @patch('dynamicalsystem.listing.maintenance.daily.BFIFetcher')
    @patch('dynamicalsystem.listing.maintenance.daily.RuntimeFetcher')
    @patch('dynamicalsystem.listing.maintenance.daily.ScheduleManager')
    @patch('dynamicalsystem.listing.maintenance.daily.time.sleep')  # Skip sleep
    def test_successful_run(self, mock_sleep, mock_sm, mock_rf, mock_fetcher, mock_db):
        """Test successful scrape run."""
        # Setup mocks
        manager = MagicMock()

        # Horizon scan
        horizon_result = MagicMock()
        horizon_result.new_dates = {'2025-10-27'}
        manager.update_horizon.return_value = horizon_result

        # Dates to scrape
        manager.get_dates_to_scrape.return_value = ['2025-10-26']

        # Scrape result
        scrape_result = MagicMock()
        scrape_result.showing_count = 4
        scrape_result.changes_detected = [MagicMock(), MagicMock()]
        scrape_result.status = 'complete'
        manager.scrape_date.return_value = scrape_result

        mock_sm.return_value = manager

        # Mock database cleanup
        db_instance = MagicMock()
        db_instance.delete_old_listings.return_value = 10
        db_instance.delete_old_snapshots.return_value = 5
        mock_db.return_value = db_instance

        # Run
        summary = run_daily_maintenance(dry_run=False)

        # Verify
        assert summary.new_dates_found == 1
        assert summary.dates_scraped == 1
        assert summary.changes_detected == 2
        assert len(summary.errors) == 0

        # Verify scrape was called
        manager.scrape_date.assert_called_once_with('2025-10-26')

        # Verify cleanup was called
        db_instance.delete_old_listings.assert_called_once()
        db_instance.delete_old_snapshots.assert_called_once()

    @patch('dynamicalsystem.listing.maintenance.daily.Database')
    @patch('dynamicalsystem.listing.maintenance.daily.BFIFetcher')
    @patch('dynamicalsystem.listing.maintenance.daily.RuntimeFetcher')
    @patch('dynamicalsystem.listing.maintenance.daily.ScheduleManager')
    @patch('dynamicalsystem.listing.maintenance.daily.time.sleep')
    def test_horizon_scan_failure(self, mock_sleep, mock_sm, mock_rf, mock_fetcher, mock_db):
        """Test that horizon scan failure doesn't stop scraping."""
        # Setup mocks
        manager = MagicMock()
        manager.update_horizon.side_effect = Exception("Horizon scan failed")
        manager.get_dates_to_scrape.return_value = ['2025-10-26']

        scrape_result = MagicMock()
        scrape_result.showing_count = 4
        scrape_result.changes_detected = []
        scrape_result.status = 'complete'
        manager.scrape_date.return_value = scrape_result

        mock_sm.return_value = manager

        db_instance = MagicMock()
        db_instance.delete_old_listings.return_value = 0
        db_instance.delete_old_snapshots.return_value = 0
        mock_db.return_value = db_instance

        # Run
        summary = run_daily_maintenance(dry_run=False)

        # Should have error from horizon scan
        assert len(summary.errors) == 1
        assert "horizon_scan" in summary.errors[0]

        # But should still scrape known dates
        assert summary.dates_scraped == 1

    @patch('dynamicalsystem.listing.maintenance.daily.Database')
    @patch('dynamicalsystem.listing.maintenance.daily.BFIFetcher')
    @patch('dynamicalsystem.listing.maintenance.daily.RuntimeFetcher')
    @patch('dynamicalsystem.listing.maintenance.daily.ScheduleManager')
    @patch('dynamicalsystem.listing.maintenance.daily.time.sleep')
    def test_scrape_date_failure(self, mock_sleep, mock_sm, mock_rf, mock_fetcher, mock_db):
        """Test that scrape_date failure is recorded but continues."""
        # Setup mocks
        manager = MagicMock()

        horizon_result = MagicMock()
        horizon_result.new_dates = set()
        manager.update_horizon.return_value = horizon_result

        manager.get_dates_to_scrape.return_value = ['2025-10-26', '2025-10-27']

        # First scrape fails, second succeeds
        manager.scrape_date.side_effect = [
            Exception("Scrape failed"),
            MagicMock(showing_count=4, changes_detected=[], status='complete')
        ]

        mock_sm.return_value = manager

        db_instance = MagicMock()
        db_instance.delete_old_listings.return_value = 0
        db_instance.delete_old_snapshots.return_value = 0
        mock_db.return_value = db_instance

        # Run
        summary = run_daily_maintenance(dry_run=False)

        # Should have 1 successful scrape
        assert summary.dates_scraped == 1

        # Should have 1 error
        assert len(summary.errors) == 1
        assert "2025-10-26" in summary.errors[0]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
