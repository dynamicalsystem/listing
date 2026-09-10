---
loop: 2026-09-query-alerts
product: listing
owner: dynamicalsystem
status: Act
parent: null
blocked-by: []
worktrees: []
prs: []
triggers: []
---

# Query Alerts

## Status

Act

**Owner:** dynamicalsystem

## Context

Opened 2026-09-10. Motivating incident: Dune: Part Three appeared on the BFI
horizon while the system watched - the 2026-09-10 sweep picked up a new
preview date (2026-12-15) to add to the Dec 18/19/20 showings already
captured - but the information died in the journal. Simon, who wanted
exactly that alert, found out by accident a day later. The scraper sees;
nothing tells anyone.

Re-cut 2026-09-10 (same day): the first draft decided on Signal push +
magic-link registration + per-query RSS. Simon's challenge - "should the
RSS feed just be an unfiltered list of everything? the website might
collapse to an RSS link, and registration/Signal might not be necessary" -
survived scrutiny and the loop was re-scoped around RSS-first.

## Observations

- /rss/current already IS the unfiltered everything-feed: one item per
  showing (96 today) with title, date/time, format, rating, availability
  status, per-showing detail link.
- Gaps against the "primary interface" bar:
  - availability_count is in the database but the feed renders only the
    status word ("Sold Out"), not the ticket count.
  - No purchase link was ever captured - only the showing's detail page
    URL. The per-showing context_id we do capture may make a direct
    booking URL derivable (original observe notes recorded booking links
    on the page; verify).
  - The item guid is the display string ("showing/Sunday 20 December 2026
    20:30") - it carries no film identity and no stable id. A film swapped
    into the same slot would keep the same guid and never resurface in
    readers. bfi_showing_id is the right guid.
- RSS reader unread-state is an alerting mechanism: a new showing becomes
  a new guid, surfaced as unread on the reader's next poll after the 02:00
  sweep. It also provides per-reader dedup for free - the delivered-alerts
  table from the first draft falls away.
- The daily sweep's schedule_changes delta still exists for anything that
  later needs push semantics.
- Delivery/auth infra observed for the first draft (signal-cli-rest-api on
  the box, festers magic-link pattern) remains available if push is ever
  justified; recorded here so the parked option keeps its context.

## Orientation

Two capabilities, in order of leverage:

1. The everything-feed as the product. Fix the three gaps (guid ->
   bfi_showing_id; ticket count in item title/description; booking link -
   verify derivability from context_id, else keep detail link and say so).
   The feed then carries: date/time, title, purchase (or detail) link,
   available tickets - Simon's four fields. New showings arrive as unread
   items with no further machinery.

2. Stateless filtered feeds. A query is encoded entirely in the URL, e.g.
   /rss/current?title=dune&dow=fri,sat&dates=2026-12-15,2026-12-19 -
   title substring + composable date functions (day-of-week set, date bag,
   range). The predicate evaluator from the first draft survives but runs
   at render time; "registering" is bookmarking the URL in a reader.
   No accounts, no subscription storage, no abuse surface beyond
   rate-limiting a public read endpoint.

What RSS genuinely cannot do (the only remaining case for push +
registration, parked until evidence demands it):
- sub-poll-interval latency (on-sale timing for hot previews),
- availability-transition alerts (sold out -> available) - these do not
  map to unread semantics without guid abuse.

The website remains as the already-built view; no further investment.

## Decision

RSS-first, two acts, no registration:

1. ACT feed-hardening: guid = bfi_showing_id, availability count rendered,
   booking link verified/derived or explicitly settled as detail link.
2. ACT query-feeds: stateless query-parameter filtering on the feed
   (title substring; day-of-week set; date bag; date range; composable),
   with tests over recorded fixtures (the Dune preview day).

Signal push and magic-link registration are PARKED, not planned. Unblocker
recorded in the backlog: demonstrated need for push latency or for
availability-transition alerts.

Rationale from orientation: capability 1 is a small hardening of a live
endpoint and immediately covers the motivating incident; capability 2
reuses the predicate design with zero state; everything cut was
infrastructure whose job a feed reader already does.

## Action

- [x] ACT feed-hardening (branch feed/hardening, merged to main
      2026-09-10; deployed by auto-update and verified live). Booking-link
      investigation settled: the per-showing detail link (article_id +
      context_id) lands directly on BFI's "Buy cinema tickets for ..."
      page - it IS the purchase link; no separate URL exists to derive.
      guids are bfi_showing_id (daily-changes guids append scraped_at so
      repeat changes resurface); availability renders the ticket count.
      8 new tests in tests/test_webserver.py cover the guid properties.
      PROCESS ERROR, flagged by Simon: the guid change re-surfaced all
      ~96 items as unread once in existing readers' feeds - a user-facing
      cost shipped without asking, with two live subscribers. Reverting
      would repeat the flood, so the change stands; the lesson (breaking
      changes to live user-facing interfaces get asked about first) is
      recorded in the backlog.
- [ ] ACT query-feeds (branch: feed/query-filters)

## Outcomes

### Outcome 1: The everything-feed is a trustworthy primary interface

Tests:
- [/] Each item carries date/time, title, ticket availability count, and
      the bookable link (verified live 2026-09-10; the detail link is the
      purchase page, decision recorded in Action)
- [/] Item guids are bfi_showing_id: re-scrape stability and
      one-new-item-per-new-showing unit tested (test_webserver.py);
      live guids confirmed as BFI showing UUIDs
- [/] A film replacing another in the same slot yields a new guid
      (unit tested)

### Outcome 2: Query feeds answer the motivating use cases statelessly

Tests:
- [ ] /rss/current?title=dune serves only Dune showings; bookmarking it in
      a reader and re-polling after a sweep that adds a Dune showing
      surfaces exactly one unread item
- [ ] A {fri,sat} day-of-week filter serves only Friday/Saturday showings;
      a date-bag filter serves only its listed dates; title + date filters
      compose as intersection
- [ ] An invalid or empty query degrades cleanly (400 or empty feed, not a
      500)
