---
loop: 2026-10-scraper-egress
product: listing
owner: dynamicalsystem
status: Act
parent: null
blocked-by: []
worktrees: [listing/scraper-egress (branch egress/instrument-challenges)]
prs: [https://github.com/dynamicalsystem/listing/pull/1]
triggers: []
---

# Scraper Egress

## Status

Act (experiment 1); Decision still pending experiments 2 and 3

**Owner:** dynamicalsystem

## Context

Opened 2026-10-24 from [[2026-10-sweep-timing]]. Every HTTP 403 the sweep
has ever logged is a Cloudflare bot-management challenge aimed at the
gateway's datacenter IP. Sweep timing cannot fix that, and when the
challenge is up the system misses announcements entirely, which is the
failure Simon cares about most. The 2026-09-deploy-gateway loop met the
same wall on 2026-09-07 and got past it with curl_cffi TLS impersonation;
that fix holds most days and fails on others.

## Observations

- 2026-10-24 21:45 UTC paired probe, same fetcher code, same Nov 5 URL:
  - gateway (Oracle Ampere, OCI London): 403, server=cloudflare,
    cf-mitigated=challenge, body "Just a moment..." (JS challenge).
  - Simon's Mac (residential, 85.255.235.168): 200, full searchResults
    payload, cf-cache-status DYNAMIC.
- 2026-10-24 21:53 UTC, agent box (Oracle Ampere, 140.238.91.154, same OCI
  region, no app traffic ever): 403 cf-mitigated=challenge on 3 of 3
  requests via the listing image. The challenge is on the IP class, not on
  the gateway's history or request volume.
- Challenge days since go-live (from exit codes; the sweep does not log
  cf-mitigated so these are inferred): Sep 15, 19, 22; Oct 13; Oct 15-22
  (continuous, 8 of 10 sweeps); Oct 24 21:42 UTC (all 37 dates) while the
  01:04 UTC sweep the same day exited 0. Flaps on a scale of hours to
  days, not requests.
- The sweep has no retry across the challenge: one pass, exit 1 or 2,
  wait 24h. During Oct 15-22 the feed carried nothing new for a week and
  Dune wave 1 (19 dates) surfaced only on Oct 23.
- The failure summary reports impossible percentages (438% on Oct 15) and
  attempts past dates when the horizon scan fails (backlog); both inflate
  the noise around a challenge day.
- Fetcher: curl_cffi Session(impersonate="chrome"), no proxy, no retry,
  since listing 12a72d3 (2026-09-07). curl_cffi honours proxies natively.
- Fleet: gateway and agent are both Oracle Ampere boxes; WireGuard hub is
  gateway 10.100.0.1. Simon's home machine geneticalgorithm.local was not
  resolvable from the Mac at 21:55 UTC tonight; whether it is a WireGuard
  peer and what its uptime is are unknown.
- Cloudflare's managed challenge issues a cf_clearance cookie on success;
  curl_cffi cannot execute the JavaScript to earn one.

## Orientation

The challenge keys on IP reputation (datacenter ASN), so better TLS or
header impersonation cannot fix it; September's fix was already the limit
of that approach. The options fall into three groups:

Degrade gracefully (product only, cheap):
- Retry across the challenge: on cf-mitigated=challenge, re-run the sweep
  hourly until it passes or the next scheduled sweep arrives. Turns "missed
  for 24h" into "late by hours" on flap days; does nothing on a week like
  Oct 15-22. Needs the instrumentation below to trigger on the right
  signal.
- Instrument: log cf-ray and cf-mitigated on every 403 and expose a
  challenge counter in /health, so the challenge rate is measured rather
  than inferred from exit codes.

Change the egress IP (infra, medium):
- Residential proxy over WireGuard: a SOCKS proxy on a residential box
  (home machine, or the Mac) reachable on the mesh; the fetcher takes a
  proxy URL from the environment. Cheapest route to a passing IP. Cost: the
  sweep inherits the home box's uptime and the home connection's
  reliability, and tinsnip gains a dependency on a non-fleet host.
- Run the sweep on the residential box and ship results to the gateway.
  Same IP benefit, but the sqlite database lives on the gateway so this
  needs a push interface. Larger change; only if the proxy route proves
  too fragile.
- Different cloud IP or provider: unknown whether reputation is per-IP or
  per-ASN; the agent result (fresh IP, same ASN, same challenge) suggests
  ASN. Low confidence, cheap to probe if a non-OCI box exists.

Pass the challenge (heavy):
- Headless browser (Playwright) on the gateway to earn cf_clearance, then
  hand the cookie to curl_cffi. Large image, fragile against Cloudflare
  updates, and may still fail from a datacenter IP. Last resort.
- Commercial residential proxy: works, costs money, and routes our traffic
  through a third party. Not preferred.
- Ask BFI for an allowlist or a feed. Zero cost to ask; low odds.

Recommendation to carry into Decide: instrument first (it is needed by
every other option and is a small product change), add retry-across-
challenge second, and run the residential-proxy experiment in parallel
since it is the only option that addresses a week-long block.

## Decision

Pending. Experiments to run before deciding:

1. Instrument the fetcher: log cf-ray and cf-mitigated on 403, count
   challenges per sweep, surface in /health. Product PR; no behaviour
   change.
2. Residential egress probe: stand up a SOCKS proxy on a residential box on
   the WireGuard mesh and run the paired probe from the gateway through it
   for 7 days at 18:30 UK. Record pass rate and the box's availability at
   that hour.
3. Retry-across-challenge: design the hourly retry (bound, jitter, stop
   time) and estimate from the Oct history how many challenge days it
   would have recovered.

## Action

- 2026-10-24 experiment 1 (instrument), PR
  https://github.com/dynamicalsystem/listing/pull/1 from worktree
  ~/work/listing/scraper-egress, branch egress/instrument-challenges:
  - fetch.py detects a Cloudflare challenge on 403 (cf-mitigated header or
    "Just a moment" body), logs cf-ray and cf-mitigated, raises
    CloudflareChallenge, counts requests and challenges per fetcher.
  - schema v2 adds sweep_runs (one row per sweep: dates attempted and
    scraped, errors, requests, challenges, last cf-ray, exit code); same
    SQL for fresh installs and the v1->v2 migration, which runs when the
    maintain container next constructs Database().
  - daily.py: summary carries the counters; exit-code logic extracted to
    determine_exit_code with the formula deliberately unchanged so
    2026-10-sweep-timing's exit-code measurement stays comparable;
    record_sweep writes the row and never raises.
  - /health gains last_sweep and sweeps_14d, null until the first migrated
    sweep so the webserver can start first.
  - Verified: 174 tests pass (21 new); migration run against a copy of the
    production database (v1->v2, 160 listings intact); one live request
    through the new code from the Mac: 200, cf-ray recorded.
  - Awaiting review/merge. Outcome 1 tests become checkable after the
    first 18:30 sweep following deploy.
- Experiments 2 (residential egress probe) and 3 (retry-across-challenge
  design) not started.

## Outcomes

### Outcome 1: Challenges are measured, not inferred

Tests:
- [ ] Every 403 in the journal carries cf-ray and cf-mitigated
- [ ] /health reports challenges seen in the last sweep and the last 14 days

### Outcome 2: A challenge day no longer means a missed day

Tests:
- [ ] Over 30 days after the chosen egress change ships, no BFI publish
      (cross-checked against BFI emails) takes more than 24h to reach the
      feed
- [ ] The Oct 15-22 pattern (7+ consecutive challenged sweeps) does not
      recur, or if it does the feed still updates within 24h

### Outcome 3: The egress decision is recorded with its trade-offs

Tests:
- [ ] Decision section names the chosen option, the rejected ones, and the
      operational dependency it adds (if any); promoted to
      architecture/docs/scraper-egress/ on main
