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
  or after 2026-10-08); closed 2026-10-24, Succeeded

## Observations

- 2026-10-24: BFI intermittently answers the sweep with HTTP 403. In-window
  hits: Sep 15, 19, 22 (1 day each). Out of window: Oct 13, then Oct 15-22
  continuously (8 of 10 sweeps non-zero, 342 403-lines on Oct 15), clean
  again from Oct 23 with no change shipped. Looks like rate limiting or
  bot blocking of the curl_cffi fingerprint rather than an outage. Candidate
  loop: characterise the 403 pattern (time of day, request count before
  first 403, which paths) before deciding on backoff, jitter, or spreading
  the sweep.

- 2026-10-24: the sweep's failure summary reports impossible percentages
  ("Critical: 438% of scrapes failed" on Oct 15; 126-204% on other days).
  The numerator is counting retries or per-date failures against a
  denominator of scheduled dates. Exit code 2 is derived from this number,
  so the critical threshold is firing on a wrong figure.

- 2026-10-24: when the horizon scan fails (403), the sweep goes on to
  attempt dates already in the past ("Failed to scrape 2026-09-08" logged
  on Oct 22; 2026-09-18 on Oct 13). The fallback schedule is not pruned to
  today onward. Harmless for the public page (prune still runs) but it
  inflates the failure count above and wastes requests against a host that
  is already refusing us.

- 2026-10-24: podman-auto-update.service on gateway failed Oct 10, Oct 23,
  Oct 24 with "container <id> does not exist in database". A manual
  --dry-run at 20:35 UTC lists gazette/festers/listing fine, and all
  containers were "Up 19 minutes", so a restart may have raced the timer.
  Worth watching: if auto-update stays broken, fixes merged to main will
  not reach the box.

- 2026-10-24: every listing-maintain journal line appears twice under two
  PIDs. Probably stdout plus a journald/syslog handler in the container, or
  two logging handlers. Doubles log volume and every grep count.

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
