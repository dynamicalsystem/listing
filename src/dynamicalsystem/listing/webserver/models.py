"""Data models for web server."""

from typing import Optional
from pydantic import BaseModel


class Showing(BaseModel):
    """A single movie showing."""
    bfi_showing_id: Optional[str] = None
    showing_date: str
    showing_time: str
    showing_datetime_utc: str
    scraped_at: Optional[str] = None
    movie_title: str
    format_keywords: Optional[str] = None
    rating: Optional[str] = None
    detail_url_path: Optional[str] = None
    availability_status: Optional[str] = None
    availability_count: Optional[int] = None
    is_3d: bool = False
    is_70mm: bool = False
    is_laser: bool = False
    has_subtitles: bool = False

    def detail_url(self) -> str:
        """Get full BFI detail URL."""
        if self.detail_url_path:
            return f"https://whatson.bfi.org.uk/imax/Online/{self.detail_url_path}"
        return ""

    def buy_url(self) -> str:
        """Seat-selection page for this specific showing.

        bfi_showing_id is BFI's performance id; mapSelect binds the seat
        widget to it (verified live 2026-09-11). Falls back to the film
        detail page when the id is missing.
        """
        if self.bfi_showing_id:
            return (
                "https://whatson.bfi.org.uk/imax/Online/mapSelect.asp"
                "?doWork::WSmap::loadMap=1"
                f"&BOparam::WSmap::loadMap::performance_ids={self.bfi_showing_id}"
            )
        return self.detail_url()

    def day_of_week(self) -> str:
        """Abbreviated day of week for the showing date, e.g. 'Thu'."""
        from datetime import date as _date
        try:
            return _date.fromisoformat(self.showing_date).strftime('%a')
        except ValueError:
            return ""

    def date_display(self) -> str:
        """Short human date with day of week, e.g. 'Thu 10-Sep'."""
        from datetime import date as _date
        try:
            d = _date.fromisoformat(self.showing_date)
            return d.strftime('%a %d-%b')
        except ValueError:
            return self.showing_date

    def title_display(self) -> str:
        """Feed item title: '<movie title> - Thu 10-Sep 22:30'."""
        return f"{self.movie_title} - {self.date_display()} {self.showing_time}"

    def format_display(self) -> str:
        """Get human-readable format string."""
        formats = []
        if self.is_70mm:
            formats.append("70mm")
        if self.is_3d:
            formats.append("3D")
        if self.is_laser:
            formats.append("IMAX with Laser")
        if self.has_subtitles:
            formats.append("Subtitles")

        return ", ".join(formats) if formats else "IMAX"

    def availability_display(self) -> str:
        """Get human-readable availability."""
        status_map = {
            "G": "Good",
            "L": "Limited",
            "S": "Sold Out"
        }
        return status_map.get(self.availability_status or "", "Unknown")

    def availability_full(self) -> str:
        """Availability with ticket count when known."""
        base = self.availability_display()
        if self.availability_count is not None:
            return f"{base} ({self.availability_count} tickets)"
        return base

    def guid_key(self) -> str:
        """Stable per-showing identity for feed guids.

        bfi_showing_id survives re-scrapes and changes when a different
        film takes the slot; the datetime fallback only covers legacy rows.
        """
        return self.bfi_showing_id or self.showing_datetime_utc


class HealthInfo(BaseModel):
    """Health check information."""
    status: str  # "healthy", "degraded", "unhealthy"
    last_scrape: Optional[str] = None
    last_scrape_status: Optional[str] = None
    listings_count: int = 0
    oldest_listing: Optional[str] = None
    newest_listing: Optional[str] = None
