---
loop: 2026-09-soak-test
product: listing
owner: dynamicalsystem
status: Closed
parent: 2026-09-deploy-gateway
blocked-by: []
worktrees: []
prs: []
triggers: []
---

# [ARCHIVED] Listing 30-Day Soak Test

## Status

Closed

**Owner:** dynamicalsystem

## Context

Fired by the backlog trigger when [[2026-09-deploy-gateway]] closed on
2026-09-10. Carries the one outcome test abandoned at the
2025-10-imax-listing-scraper closure: "No manual intervention needed for
30+ days". The system went live on the gateway box on 2026-09-07 and the
scheduled timer has run clean since 2026-09-08.

## Observations

- Scheduled sweeps at 02:00 Europe/London (01:00 UTC under BST) on
  Sep 08/09/10 all exited 0, scraped 33-34 dates, detected changes daily,
  and pruned expired listings (oldest_listing tracks today).
- podman auto-update swapped the curl_cffi image unattended on 2026-09-07.
- 2026-09-12 22:44 UTC health check: status healthy, last_scrape
  2026-09-12T01:05:58Z, 87 listings, oldest_listing 2026-09-12 (today),
  newest 2026-12-20. last_scrape_status "partial" is the completeness of
  the last date scraped (scrape_schedule.status), not the sweep exit code;
  exit codes are only visible in the gateway journal.
- 2026-09-12 23:00 UTC: Simon reported no new listings since Sep 10.
  Independent check from a local venv: BFI publishes 83 upcoming showings
  (Sep 13 to Dec 20), all 83 present in the feed. Not a system fault; BFI
  had added nothing. Gateway journal exit codes not yet read (ssh read
  blocked from the session; Simon to run manually).
- 2026-10-24 20:30 UTC verification (journal read over ssh, 16 days late):
  - Window 2026-09-08 to 2026-10-07: 30 sweeps fired, 27 exited 0.
    Non-zero: Sep 15 (exit 1), Sep 19 (exit 2), Sep 22 (exit 2). Every
    non-zero exit was BFI returning HTTP 403 to the horizon scan and/or
    per-date scrapes. Each time the next day's sweep exited 0 with no
    change to the system.
  - No manual intervention in the window. podman auto-update shows no
    listing image pulls after 2026-09-11 (the last query-alerts merge), so
    no code was shipped to recover.
  - Health 2026-10-24 20:31 UTC: healthy, last_scrape 2026-10-24T01:04:52Z,
    160 listings, oldest_listing 2026-10-24 (today), newest 2027-01-07.
  - Public page: earliest date token 2026-10-24; no past-dated showings.
- Outside the window: a longer 403 streak Oct 13-22 (8 of 10 sweeps
  non-zero, peaking at 342 403-lines on Oct 15), self-recovered Oct 23.
  Signals raised from it are in the backlog, not here.

## Orientation

Nothing to build; this loop is a measurement window. The soak clock starts
at the first scheduled firing (2026-09-08), so 30 consecutive days ends
2026-10-07 inclusive; verify on or after 2026-10-08.

Verification: the strict clause of test 1 ("every sweep exited 0") fails
on three BFI-side 403 days. The intervention clause holds. The Decision
below says the clock restarts only if the cause required a change to the
system; it did not, so the window stands and the loop closes.

## Decision

Passive observation. No changes to the system during the window except
unattended auto-update deploys, which are part of what is being soaked.
If a sweep fails or manual intervention is needed, record it here and
restart the clock only if the cause required a change to the system.

## Action

Verification (on/after 2026-10-08), from the journal and health endpoint:

    journalctl --user -u listing-maintain.service --since 2026-09-08 \
      | grep "exit code"
    curl -s https://listing.dynamicalsystem.com/health

Performed 2026-10-24 20:30 UTC. Results in Observations.

## Outcomes

### Outcome 1: The system runs unattended for 30 days

Tests:
- [x] FAILED as written: 27/30 sweeps exited 0. Sep 15/19/22 exited
      non-zero on BFI 403s and self-recovered next day. No manual
      intervention in the window (the clause this loop actually carries
      from the scraper closure) - that half passes.
- [/] Health endpoint reports a scrape within the last 24h and
      oldest_listing >= today (checked 2026-10-24, not 2026-10-08)
- [/] No stale (past-dated) showings visible on the public page
