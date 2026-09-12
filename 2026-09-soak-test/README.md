---
loop: 2026-09-soak-test
product: listing
owner: dynamicalsystem
status: Act
parent: 2026-09-deploy-gateway
blocked-by: []
worktrees: []
prs: []
triggers: []
---

# Listing 30-Day Soak Test

## Status

Act

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

## Orientation

Nothing to build; this loop is a measurement window. The soak clock starts
at the first scheduled firing (2026-09-08), so 30 consecutive days ends
2026-10-07 inclusive; verify on or after 2026-10-08.

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

## Outcomes

### Outcome 1: The system runs unattended for 30 days

Tests:
- [ ] Every scheduled sweep from 2026-09-08 to 2026-10-07 exited 0 with no
      manual intervention
- [ ] Health endpoint reports a scrape within the last 24h and
      oldest_listing >= today on 2026-10-08
- [ ] No stale (past-dated) showings visible on the public page
