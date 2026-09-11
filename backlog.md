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
