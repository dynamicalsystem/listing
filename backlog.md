# Backlog

Durable observations and cross-loop triggers for the listing product.

## Triggers

- when: push latency or availability-transition alerts (sold out ->
  available) are demonstrably needed for listing
  then: "unpark Signal push + magic-link registration - design context is
  preserved in 2026-09-query-alerts Observations (first-draft decision,
  re-cut 2026-09-10 to RSS-first)"

- [fired 2026-09-10] when: 2026-09-deploy-gateway reaches Closed
  then: start the 30-day soak test -> opened 2026-09-soak-test (verify on
  or after 2026-10-08)

## Observations

- 2026-09-12: the daily feed only lists showings first seen in the last
  24h; availability refreshes deliberately leave scraped_at alone. So a
  quiet BFI (no new showings since 2026-09-10) and a broken scraper look
  identical to a subscriber. Verified working by diffing BFI live (83) vs
  feed (87, the extra 4 being that day's showings): 0 missing. Consider a
  way for subscribers to tell quiet from broken, e.g. last-sweep time in
  the channel description or a daily heartbeat item.

- Availability status codes beyond G/L/S exist in BFI data (e.g. 'E', seen
  on Super Nature rows) and render as "Unknown (N tickets)" in the feed.
  Harmless but worth mapping when the meaning is known.

- 2026-09-10: feed guid hardening re-surfaced all items as unread for the
  feed's two live subscribers; the cost was accepted unilaterally instead
  of being asked about. Rule going forward: any breaking change to a live
  user-facing interface (feed guids, URLs, payload shapes) gets surfaced
  to Simon before shipping, with the user impact stated.

- Unit tests mock Database with a bare MagicMock, which masked two wrong-method
  calls in daily.py until closure validation (2026-09-07). Consider
  Mock(spec=Database) across the suite so signature drift fails loudly.
- BFI serves a no-results page (no performanceDays array) for a same-day query
  late in the day. Horizon scan now falls back to tomorrow; worth watching for
  other query-shape surprises.
