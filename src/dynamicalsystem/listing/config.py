"""Configuration management for BFI IMAX listing scraper.

Loads configuration from environment variables with sensible defaults.
"""

import os


class Config:
    """Configuration settings for the listing scraper."""

    # Database
    DB_PATH = os.getenv('LISTING_DB_PATH', '/data/listing.db')

    # Logging
    LOG_FILE = os.getenv('LISTING_LOG_FILE', '/var/log/listing/daily.log')
    LOG_LEVEL = os.getenv('LISTING_LOG_LEVEL', 'INFO')

    # Maintenance schedule
    MAINTENANCE_HOUR = int(os.getenv('LISTING_MAINTENANCE_HOUR', '2'))  # 02:00 UTC

    # Alert thresholds
    MAX_ERROR_RATE = float(os.getenv('LISTING_MAX_ERROR_RATE', '0.5'))  # 50%

    # Health check URL (optional)
    HEALTHCHECK_URL = os.getenv('HEALTHCHECK_URL', None)

    # Site configuration (for RSS feeds, future use)
    SITE_TITLE = os.getenv('SITE_TITLE', 'BFI IMAX Listings')
    SITE_URL = os.getenv('SITE_URL', 'http://localhost:8080')

    @classmethod
    def validate(cls) -> bool:
        """Validate configuration settings.

        Returns:
            True if configuration is valid, False otherwise
        """
        # Check critical settings
        if not cls.DB_PATH:
            return False

        if cls.MAINTENANCE_HOUR < 0 or cls.MAINTENANCE_HOUR > 23:
            return False

        if cls.MAX_ERROR_RATE < 0 or cls.MAX_ERROR_RATE > 1:
            return False

        return True
