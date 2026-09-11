# BFI IMAX Listings

Scrapes the BFI IMAX schedule daily and serves it as a web page and RSS
feeds. Live at https://listing.dynamicalsystem.com.

The RSS feed is the primary interface: point a feed reader at it and new
showings arrive as unread items after the nightly scrape. Each item carries
the film, date/time, ticket availability, and a link straight to the
showing's seat-selection page.

## Feeds

| URL | Contents |
|---|---|
| `/rss/current` | every upcoming showing |
| `/rss/daily` | showings added in the last 24 hours |

### Filtering

Both feeds accept query parameters; a "subscription" is just a bookmarked
URL. Filters compose as intersection. Invalid values return a 400 so a bad
bookmark fails when you create it, not silently forever.

| Parameter | Example | Meaning |
|---|---|---|
| `title` | `?title=dune` | case-insensitive substring on the film title |
| `dow` | `?dow=fri,sat` | day-of-week set (`mon`..`sun`) |
| `dates` | `?dates=2026-12-15,2026-12-19` | explicit dates (YYYY-MM-DD) |
| `from` / `to` | `?from=2026-12-01&to=2026-12-31` | inclusive date range |

Examples:

    https://listing.dynamicalsystem.com/rss/current?title=dune
    https://listing.dynamicalsystem.com/rss/current?dow=fri,sat
    https://listing.dynamicalsystem.com/rss/current?title=odyssey&dates=2026-09-19

## Other endpoints

- `/` - HTML view of all upcoming showings
- `/health` - JSON health and freshness info

## Development

Python 3.13, managed with uv:

    uv sync
    uv run pytest              # offline suite (live probes live in experiments/)
    uv run uvicorn dynamicalsystem.listing.webserver.main:app

Daily maintenance (scrape + prune) runs as a one-shot:

    uv run python -m dynamicalsystem.listing.maintenance.daily --dry-run

Deployment: merges to main build a multi-arch image to GHCR
(.github/workflows/release.yml); the gateway box pulls it via podman
auto-update as tinsnip-managed Quadlet units. Planning happens on the
`ooda` orphan branch (control plane); see that branch for loops and
decisions.
