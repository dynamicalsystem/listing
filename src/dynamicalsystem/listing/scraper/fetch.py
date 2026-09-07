"""BFI IMAX website fetcher with Cloudflare bypass."""

from typing import Optional
from urllib.parse import urlencode
import cloudscraper
from bs4 import BeautifulSoup


class BFIFetcher:
    """Fetches BFI IMAX schedule pages, handling Cloudflare protection."""

    BASE_URL = "https://whatson.bfi.org.uk/imax/Online/default.asp"
    ARTICLE_SEARCH_ID = "49C49C83-6BA0-420C-A784-9B485E36E2E0"

    def __init__(self):
        """Initialize fetcher with cloudscraper session."""
        # firefox, not chrome: Cloudflare 403s the chrome profile when the
        # request comes from a Linux container (TLS fingerprint mismatch);
        # the firefox profile passes from both macOS and Linux.
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'firefox',
                'platform': 'linux',
                'desktop': True
            }
        )

    def build_url(self, date_from: str, date_to: Optional[str] = None) -> str:
        """Build BFI search URL for date range.

        Args:
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format (defaults to date_from)

        Returns:
            Full URL with query parameters
        """
        if date_to is None:
            date_to = date_from

        params = {
            'BOset::WScontent::SearchCriteria::venue_filter': '',
            'BOset::WScontent::SearchCriteria::city_filter': '',
            'BOset::WScontent::SearchCriteria::month_filter': '',
            'BOset::WScontent::SearchCriteria::object_type_filter': '',
            'BOset::WScontent::SearchCriteria::category_filter': '',
            'BOset::WScontent::SearchCriteria::search_from': date_from,
            'BOset::WScontent::SearchCriteria::search_to': date_to,
            'doWork::WScontent::search': '1',
            'BOparam::WScontent::search::article_search_id': self.ARTICLE_SEARCH_ID,
            'BOset::WScontent::SearchCriteria::search_criteria': '',
        }

        return f"{self.BASE_URL}?{urlencode(params)}"

    def fetch(self, date_from: str, date_to: Optional[str] = None) -> str:
        """Fetch BFI schedule page HTML.

        Args:
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format (defaults to date_from)

        Returns:
            HTML content as string

        Raises:
            Exception: If request fails
        """
        url = self.build_url(date_from, date_to)
        response = self.scraper.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    def fetch_soup(self, date_from: str, date_to: Optional[str] = None) -> BeautifulSoup:
        """Fetch and parse BFI schedule page.

        Args:
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format (defaults to date_from)

        Returns:
            BeautifulSoup parsed HTML

        Raises:
            Exception: If request fails
        """
        html = self.fetch(date_from, date_to)
        return BeautifulSoup(html, 'lxml')
