"""Runtime fetcher for movie runtimes.

Fetches movie runtimes from Wikipedia.

Caches results in database to avoid repeated requests.

Design decision (2025-10-26): Wikipedia-only approach.
BFI detail pages blocked by Cloudflare (403). Wikipedia has 100% success
rate for IMAX films and is simpler (no cloudscraper needed).
"""

import re
import time
import logging
from typing import Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from dynamicalsystem.listing.storage.db import Database


logger = logging.getLogger(__name__)


@dataclass
class RuntimeResult:
    """Result from runtime fetch operation."""
    runtime_minutes: int
    source: str  # 'BFI' or 'Wikipedia'


class RuntimeFetcher:
    """Fetches and caches movie runtimes from Wikipedia.

    Strategy:
    1. Check database cache
    2. Fetch from Wikipedia
    3. Cache successful result
    4. Return None if not found
    """

    def __init__(self, db: Database):
        """Initialize runtime fetcher.

        Args:
            db: Database instance for caching
        """
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                         'AppleWebKit/537.36 (KHTML, like Gecko) '
                         'Chrome/119.0.0.0 Safari/537.36'
        })

        # Rate limiting state
        self._last_wikipedia_request = 0
        self._wikipedia_delay = 1.0  # seconds

    def get_runtime(self, movie_title: str) -> Optional[int]:
        """Get runtime for movie, with caching.

        Args:
            movie_title: Movie title

        Returns:
            Runtime in minutes or None if not found
        """
        # Check cache first
        cached = self.db.get_runtime(movie_title)
        if cached is not None:
            logger.debug(f"Cache hit for '{movie_title}': {cached}min")
            return cached

        logger.info(f"Fetching runtime for '{movie_title}'")

        # Fetch from Wikipedia
        result = self._fetch_from_wikipedia(movie_title)
        if result:
            logger.info(f"Found runtime from Wikipedia: {result.runtime_minutes}min")
            self.db.cache_runtime(movie_title, result.runtime_minutes, result.source)
            return result.runtime_minutes

        logger.warning(f"Runtime not found for '{movie_title}'")
        return None

    def _fetch_from_wikipedia(self, movie_title: str) -> Optional[RuntimeResult]:
        """Fetch runtime from Wikipedia.

        Args:
            movie_title: Movie title

        Returns:
            RuntimeResult or None if not found
        """
        normalized_title = self._normalize_title(movie_title)

        # Try multiple URL patterns
        url_patterns = [
            f"https://en.wikipedia.org/wiki/{normalized_title}_(film)",
            f"https://en.wikipedia.org/wiki/{normalized_title}",
            f"https://en.wikipedia.org/wiki/{normalized_title}_(2024_film)",
            f"https://en.wikipedia.org/wiki/{normalized_title}_(2025_film)",
        ]

        for url in url_patterns:
            # Rate limiting
            self._rate_limit_wikipedia()

            try:
                response = self.session.get(url, timeout=10)

                if response.status_code == 404:
                    continue  # Try next pattern

                response.raise_for_status()

                # Extract runtime from page
                runtime = self._extract_runtime_from_wikipedia_html(response.text)
                if runtime:
                    return RuntimeResult(runtime, 'Wikipedia')

            except requests.RequestException as e:
                logger.debug(f"Wikipedia fetch failed for {url}: {e}")
                continue

        return None

    def _extract_runtime_from_wikipedia_html(self, html: str) -> Optional[int]:
        """Extract runtime from Wikipedia HTML.

        Looks for patterns like:
        - "Running time</th><td>150 minutes"
        - "Running time</th><td>2 hours 30 minutes"

        Args:
            html: Wikipedia page HTML

        Returns:
            Runtime in minutes or None
        """
        soup = BeautifulSoup(html, 'html.parser')

        # Find "Running time" row in infobox
        for th in soup.find_all('th'):
            if 'running time' in th.get_text().lower():
                td = th.find_next_sibling('td')
                if td:
                    text = td.get_text()

                    # Pattern 1: "150 minutes" or "150 mins"
                    match = re.search(r'(\d+)\s*min', text, re.IGNORECASE)
                    if match:
                        return int(match.group(1))

                    # Pattern 2: "2 hours 30 minutes" or "2 hr 30 min"
                    match = re.search(r'(\d+)\s*(?:hours?|hrs?)\s*(?:(\d+)\s*(?:minutes?|mins?)?)?', text, re.IGNORECASE)
                    if match:
                        hours = int(match.group(1))
                        minutes = int(match.group(2)) if match.group(2) else 0
                        return hours * 60 + minutes

        return None

    def _normalize_title(self, title: str) -> str:
        """Normalize movie title for Wikipedia search.

        Removes format indicators and special characters.

        Args:
            title: Movie title like "Nosferatu - The IMAX 2D Experience"

        Returns:
            Normalized title like "Nosferatu"
        """
        # Remove common BFI format suffixes
        suffixes_to_remove = [
            r'\s*-\s*The IMAX.*',
            r'\s*-\s*IMAX.*',
            r'\s*\(IMAX.*\)',
            r'\s*-\s*3D.*',
            r'\s*-\s*70mm.*',
            r'\s*\+\s*Q&A.*',
            r'\s*-\s*Subtitled.*',
        ]

        normalized = title
        for pattern in suffixes_to_remove:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

        # Replace spaces with underscores for Wikipedia URL
        normalized = normalized.strip().replace(' ', '_')

        # Remove special characters that aren't URL-safe
        normalized = re.sub(r'[^\w\-_]', '', normalized)

        return normalized

    def _rate_limit_wikipedia(self):
        """Enforce rate limiting for Wikipedia requests."""
        now = time.time()
        time_since_last = now - self._last_wikipedia_request

        if time_since_last < self._wikipedia_delay:
            sleep_time = self._wikipedia_delay - time_since_last
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)

        self._last_wikipedia_request = time.time()
