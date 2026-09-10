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
