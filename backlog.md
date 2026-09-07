# Backlog

Durable observations and cross-loop triggers for the listing product.

## Triggers

- when: 2026-09-deploy-gateway reaches Closed
  then: "start the 30-day soak test abandoned at 2025-10-imax-listing-scraper
  closure: confirm daily maintenance runs unattended for 30+ days with no
  stale data and no manual intervention"

## Observations

- Unit tests mock Database with a bare MagicMock, which masked two wrong-method
  calls in daily.py until closure validation (2026-09-07). Consider
  Mock(spec=Database) across the suite so signature drift fails loudly.
- BFI serves a no-results page (no performanceDays array) for a same-day query
  late in the day. Horizon scan now falls back to tomorrow; worth watching for
  other query-shape surprises.
