"""Data models for web server."""

from typing import Optional
from pydantic import BaseModel


class Showing(BaseModel):
    """A single movie showing."""
    showing_date: str
    showing_time: str
    showing_datetime_utc: str
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


class HealthInfo(BaseModel):
    """Health check information."""
    status: str  # "healthy", "degraded", "unhealthy"
    last_scrape: Optional[str] = None
    last_scrape_status: Optional[str] = None
    listings_count: int = 0
    oldest_listing: Optional[str] = None
    newest_listing: Optional[str] = None
