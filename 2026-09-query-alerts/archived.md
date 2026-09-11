# Archived

- **Closed**: 2026-09-11 21:10 UTC
- **Status**: Succeeded
- **Summary**: RSS-first alerting shipped in three acts (feed-hardening,
  feed-polish, query-feeds): stable per-showing guids, live availability
  with ticket counts, direct seat-selection buy links, and stateless
  query-parameter filters - a subscription is a bookmarked URL. Signal
  push and magic-link registration were parked behind a backlog trigger
  rather than built. One process error en route: the guid change
  re-surfaced existing items for live subscribers without asking first
  (rule recorded in backlog).
- **Outcomes**: 6/6 tests passed (3 feed-as-primary-interface, 3
  stateless query feeds), verified live on the gateway box.
- **Follow-up**: backlog trigger to unpark push/registration if push
  latency or availability-transition alerts are ever demonstrably
  needed. The motivating case is served: /rss/current?title=dune.
