---
loop: 2026-09-query-alerts
product: listing
owner: dynamicalsystem
status: Decide
parent: null
blocked-by: []
worktrees: []
prs: []
triggers: []
---

# Query Alerts

## Status

Decide

**Owner:** dynamicalsystem

## Context

Opened 2026-09-10. Motivating incident: Dune: Part Three appeared on the BFI
horizon while the system watched - the 2026-09-10 sweep picked up a new
preview date (2026-12-15) to add to the Dec 18/19/20 showings already
captured - but the information died in the journal. Simon, who wanted
exactly that alert, found out by accident a day later. The scraper sees;
nothing tells anyone.

Goal: users register a query and get alerted when new showings match it.
The obvious query is movie name; the complicated ones are date functions
(day of week, bag of dates, ranges).

## Observations

- The daily sweep already computes exactly the needed delta:
  schedule_changes rows (first_seen and field-level changes) per date, and
  the ChangeDetector hash-compares snapshots. Alert evaluation can consume
  this delta instead of re-diffing anything.
- /rss/daily already serves a global last-24h changes feed - per-query RSS
  is a filtered variant of an existing mechanism.
- Delivery infra exists on the box: signal-cli-rest-api runs on signal-net
  (gazette publishes through it; the tinsnip deploy notifier posts to a
  Signal group). listing.container would need signal-net.network added in
  tinsnip to reach it.
- festers (same box) already implements magic-link auth: HMAC-fingerprinted
  links keyed by a FESTERS_SECRET env var; the secret's stability is
  load-bearing (a changed secret orphans every link). Pattern to study, not
  import - festers is a separate codebase.
- The webserver is read-only today; registration adds the first
  user-writable state (subscriptions) to the SQLite database that the
  maintenance one-shot also writes. Write concurrency stays trivial
  (short transactions) but backups start mattering.
- 2026-09-07 closure finding, still true: the site is public, so any
  registration UI is an abuse surface - hence magic links, rate limiting,
  and caps on subscriptions per identity.

## Orientation

A subscription is a predicate over showings:

- title: case-insensitive substring on movie_title (v1); worth normalising
  so "Dune 3" can match "Dune: Part Three" later, but v1 is substring.
- date function, composable:
  - day-of-week set (e.g. {Fri, Sat})
  - explicit date bag (e.g. {2026-12-15, 2026-12-19})
  - date range (from/to)
  - absent = any date
- possible later: time-of-day window, format (IMAX 70mm vs laser),
  availability transitions ("went from sold out to available").

Evaluation point: a post-sweep step. The sweep already writes
schedule_changes; a dispatcher reads the delta (new showings first; field
changes later), evaluates registered predicates against it, and emits one
alert per (subscription, showing) - deduplicated by a delivered-alerts
table so re-scrapes never re-alert.

Delivery (decided: both):
- Per-query RSS: /rss/query/<token> renders the subscription's matches;
  the token doubles as the capability to read it. Pull, zero delivery infra.
- Signal push: dispatcher posts to the subscriber's number or a group via
  signal-cli-rest-api. Push, requires signal-net membership for the
  sending container.

Identity (decided: magic links, festers pattern): public form on the site;
subscription is claimed/managed via an HMAC-fingerprinted link (own secret,
e.g. LISTING_SECRET, same stability constraint as FESTERS_SECRET).
Verification target is the delivery channel itself (the Signal number or
the feed reader) so a subscription can only alert somewhere its owner
controls.

Natural sub-loop cut (each independently testable):
1. query-model: subscription schema + predicate evaluator + dedup. Pure
   Python + SQLite, no UI, no delivery. Testable against recorded
   schedule_changes fixtures (the Dune preview day is the fixture).
2. delivery: dispatcher + Signal send + per-query RSS endpoint, driven by
   seeded subscriptions. Needs the tinsnip signal-net change.
3. registration: public form, magic-link issue/verify/manage, rate
   limiting and per-identity caps. Study festers first.

## Decision

Build in three sub-loops in the order above - the evaluator is useful the
day it lands (we can seed our own subscriptions by SQL long before the
registration UI exists), delivery makes it audible, registration makes it
public. Each sub-loop gets its own outcomes and tests; this parent closes
when all three do.

Rationale from orientation: the change-detection delta already exists, so
the evaluator is cheap and low-risk; delivery reuses proven on-box infra;
registration is the largest and riskiest surface (auth + abuse) and is
deliberately last so the useful core never waits on it.

## Action

Not started. Sub-loops to be created:

- [ ] 2026-09-alerts-query-model
- [ ] 2026-09-alerts-delivery
- [ ] 2026-09-alerts-registration

## Outcomes

### Outcome 1: A registered movie-name query alerts on new showings

Tests:
- [ ] A subscription for "Dune" receives a Signal message when a new Dune
      showing first appears in a sweep, and never a duplicate for the same
      showing on later sweeps
- [ ] The subscription's RSS feed serves the same matches

### Outcome 2: Date-function queries work

Tests:
- [ ] A {Fri,Sat} day-of-week subscription matches only Friday/Saturday
      showings
- [ ] A date-bag subscription matches only showings on its listed dates
- [ ] Composed title + date-function predicates match the intersection

### Outcome 3: Registration is safe on the public site

Tests:
- [ ] A subscription can only be created/managed via its magic link, and
      alerts only reach a channel its owner demonstrably controls
- [ ] Rate limits and per-identity caps hold under a scripted abuse attempt
