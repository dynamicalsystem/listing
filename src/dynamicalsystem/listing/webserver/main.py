"""FastAPI web server for BFI IMAX listings."""

import os
from pathlib import Path
from typing import Dict
from collections import defaultdict
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import feedgen.feed

from dynamicalsystem.listing.config import Config
from .queries import get_upcoming_showings, get_recent_changes, get_health_info
from .models import Showing, HealthInfo


# Initialize FastAPI app
app = FastAPI(
    title="BFI IMAX Listings",
    description="BFI IMAX cinema listings with RSS feeds",
    version="0.1.0"
)

# Setup templates and static files
WEBSERVER_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(WEBSERVER_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(WEBSERVER_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def listings_page(request: Request):
    """Render HTML page with all upcoming listings."""
    try:
        showings = get_upcoming_showings(Config.DB_PATH)

        # Group showings by date
        grouped: Dict[str, list] = defaultdict(list)
        for showing in showings:
            grouped[showing.showing_date].append(showing)

        # Sort dates
        sorted_dates = sorted(grouped.keys())
        grouped_showings = {date: grouped[date] for date in sorted_dates}

        return templates.TemplateResponse(
            request,
            "listings.html",
            {
                "title": "BFI IMAX Listings",
                "showings": grouped_showings
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"error": str(e)},
            status_code=500
        )


@app.get("/health")
async def health_check():
    """Health check endpoint returning JSON."""
    try:
        health = get_health_info(Config.DB_PATH)
        return health.model_dump()
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/rss/current")
async def rss_current():
    """RSS feed of all upcoming showings."""
    try:
        showings = get_upcoming_showings(Config.DB_PATH)

        # Create feed
        fg = feedgen.feed.FeedGenerator()
        fg.id(f"{Config.SITE_URL}/rss/current")
        fg.title("BFI IMAX - Current Schedule")
        fg.author({"name": "BFI IMAX Listings", "email": "noreply@example.com"})
        fg.link(href=Config.SITE_URL, rel="alternate")
        fg.link(href=f"{Config.SITE_URL}/rss/current", rel="self")
        fg.description("All upcoming BFI IMAX showings")
        fg.language("en")

        # Add entries
        for showing in showings:
            fe = fg.add_entry()
            title = f"{showing.movie_title} - {showing.showing_date} {showing.showing_time}"
            fe.id(f"{Config.SITE_URL}/showing/{showing.showing_datetime_utc}")
            fe.title(title)
            fe.link(href=showing.detail_url())

            description = f"""
            <p><strong>{showing.movie_title}</strong></p>
            <p>Date: {showing.showing_date} at {showing.showing_time}</p>
            <p>Format: {showing.format_display()}</p>
            <p>Rating: {showing.rating or 'N/A'}</p>
            <p>Availability: {showing.availability_display()}</p>
            """
            fe.description(description)

            # Use showing datetime as published date
            try:
                pub_date = datetime.fromisoformat(showing.showing_datetime_utc)
                fe.published(pub_date)
            except:
                pass

        # Generate RSS XML
        rss_str = fg.rss_str(pretty=True)
        return Response(content=rss_str, media_type="application/rss+xml")

    except Exception as e:
        return Response(
            content=f"<?xml version='1.0'?><error>{str(e)}</error>",
            media_type="application/xml",
            status_code=500
        )


@app.get("/rss/daily")
async def rss_daily():
    """RSS feed of showings added/changed in last 24 hours."""
    try:
        showings = get_recent_changes(Config.DB_PATH, hours=24)

        # Create feed
        fg = feedgen.feed.FeedGenerator()
        fg.id(f"{Config.SITE_URL}/rss/daily")
        fg.title("BFI IMAX - Daily Changes")
        fg.author({"name": "BFI IMAX Listings", "email": "noreply@example.com"})
        fg.link(href=Config.SITE_URL, rel="alternate")
        fg.link(href=f"{Config.SITE_URL}/rss/daily", rel="self")
        fg.description("New and changed BFI IMAX showings in last 24 hours")
        fg.language("en")

        # Add entries
        for showing in showings:
            fe = fg.add_entry()
            title = f"{showing.movie_title} - {showing.showing_date} {showing.showing_time}"
            fe.id(f"{Config.SITE_URL}/change/{showing.showing_datetime_utc}")
            fe.title(title)
            fe.link(href=showing.detail_url())

            description = f"""
            <p><strong>{showing.movie_title}</strong></p>
            <p>Date: {showing.showing_date} at {showing.showing_time}</p>
            <p>Format: {showing.format_display()}</p>
            <p>Rating: {showing.rating or 'N/A'}</p>
            <p>Availability: {showing.availability_display()}</p>
            """
            fe.description(description)

            try:
                pub_date = datetime.fromisoformat(showing.showing_datetime_utc)
                fe.published(pub_date)
            except:
                pass

        # Generate RSS XML
        rss_str = fg.rss_str(pretty=True)
        return Response(content=rss_str, media_type="application/rss+xml")

    except Exception as e:
        return Response(
            content=f"<?xml version='1.0'?><error>{str(e)}</error>",
            media_type="application/xml",
            status_code=500
        )


@app.get("/robots.txt")
async def robots_txt():
    """Serve restrictive robots.txt."""
    content = """User-agent: *
Disallow: /

# BFI IMAX listings - low frequency, don't crawl
# If you want the data, contact us for API access
"""
    return Response(content=content, media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
