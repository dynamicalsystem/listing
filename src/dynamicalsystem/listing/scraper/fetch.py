"""BFI IMAX website fetcher with Cloudflare bypass."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CloudflareChallenge(Exception):
    """Cloudflare answered with a bot-management challenge instead of the page.

    Raised on HTTP 403 when the response carries Cloudflare's challenge
    markers (cf-mitigated header or the "Just a moment..." interstitial).
    The fetcher cannot solve the JavaScript challenge; the point of the
    distinct exception is that challenge frequency is measured rather than
    inferred from sweep exit codes.
    """

    def __init__(self, url: str, status_code: int,
                 cf_ray: Optional[str], cf_mitigated: Optional[str]):
        self.url = url
        self.status_code = status_code
        self.cf_ray = cf_ray
        self.cf_mitigated = cf_mitigated
        super().__init__(
            f"HTTP Error {status_code}: Cloudflare challenge "
            f"(cf-mitigated={cf_mitigated}, cf-ray={cf_ray})"
        )


@dataclass
class FetchStats:
    """Per-fetcher request accounting, read by the sweep summary."""
    requests: int = 0
    challenges: int = 0
    last_cf_ray: Optional[str] = None
    last_challenge_at: Optional[str] = None  # UTC ISO 8601


class BFIFetcher:
    """Fetches BFI IMAX schedule pages, handling Cloudflare protection."""

    BASE_URL = "https://whatson.bfi.org.uk/imax/Online/default.asp"
    ARTICLE_SEARCH_ID = "49C49C83-6BA0-420C-A784-9B485E36E2E0"
    CHALLENGE_BODY_MARKER = "Just a moment"

    def __init__(self):
        """Initialize fetcher with a TLS-impersonating session.

        curl_cffi, not cloudscraper: Cloudflare rejects requests from
        datacenter IPs (the OCI gateway box) unless the TLS fingerprint
        matches a real browser, which cloudscraper cannot fake. Even so,
        Cloudflare intermittently serves a JavaScript challenge to the OCI
        IP class; see CloudflareChallenge.
        """
        self.scraper = curl_requests.Session(impersonate="chrome")
        self.stats = FetchStats()

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

    @classmethod
    def is_challenge(cls, response) -> bool:
        """True if a 403 response is a Cloudflare challenge, not a plain deny."""
        if response.status_code != 403:
            return False
        headers = response.headers
        if headers.get('cf-mitigated'):
            return True
        text = getattr(response, 'text', '') or ''
        return cls.CHALLENGE_BODY_MARKER in text[:4000]

    def fetch(self, date_from: str, date_to: Optional[str] = None) -> str:
        """Fetch BFI schedule page HTML.

        Args:
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format (defaults to date_from)

        Returns:
            HTML content as string

        Raises:
            CloudflareChallenge: If Cloudflare served a challenge page
            Exception: If the request otherwise fails
        """
        url = self.build_url(date_from, date_to)
        response = self.scraper.get(url, timeout=30)
        self.stats.requests += 1
        cf_ray = response.headers.get('cf-ray')
        if cf_ray:
            self.stats.last_cf_ray = cf_ray

        if self.is_challenge(response):
            cf_mitigated = response.headers.get('cf-mitigated')
            self.stats.challenges += 1
            self.stats.last_challenge_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
            logger.warning(
                f"Cloudflare challenge for {date_from}: status={response.status_code} "
                f"cf-mitigated={cf_mitigated} cf-ray={cf_ray}"
            )
            raise CloudflareChallenge(url, response.status_code, cf_ray, cf_mitigated)

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
