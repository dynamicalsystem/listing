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

- 2026-10-24: BFI emails (friend's sample of 2) arrived Thu 2026-10-08
  17:31 UK and Mon 2026-10-19 before 18:02 UK. Email time is not site
  publish time: Godzilla listed the same day, Dune wave 2 listed next
  morning at the stated 09:00 on-sale, behind a queue. Full evidence and
  the publish-day table are in 2026-10-sweep-timing Observations.

- 2026-10-24: three of the four isolated 403 days (Sep 15, Sep 22, Oct 13)
  were Tuesdays at 01:00 UTC. Now that the cause is a Cloudflare IP
  challenge that also fired on a Saturday evening, this is weak evidence;
  kept only because those failures blur the Monday-vs-Tuesday publish
  days in 2026-10-sweep-timing.

- 2026-10-24: a BFI title arrived as "Godzilla Minus Zero&nbsp;" and is
  stored verbatim as a distinct movie_title (separate from "Godzilla Minus
  Zero"), which also breaks the runtime join. HTML entities and trailing
  whitespace should be normalised at parse time.

- 2026-10-24: the sweep's HTTP 403s are Cloudflare bot-management
  challenges against the gateway's datacenter IP (cf-mitigated=challenge,
  "Just a moment..." body), confirmed 21:45 UTC by a paired probe: same
  fetcher code, same URL, gateway 403 vs Mac 200, 14 s apart. Not BFI rate
  limiting, not time of day (hit at 01:00 and 21:42 UTC). History: Sep 15,
  19, 22; Oct 13; Oct 15-22 continuously; Oct 24 evening. Backoff and
  jitter will not help. Agent box (same OCI region, fresh IP) is challenged
  too, so it is the IP class. Opened as 2026-10-scraper-egress.

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
