---
loop: 2026-09-deploy-gateway
product: listing
owner: dynamicalsystem
status: Act
parent: null
blocked-by: []
worktrees: []
prs: []
triggers:
  - when: 2026-09-deploy-gateway reaches Closed
    then: "start the 30-day soak test abandoned at 2025-10-imax-listing-scraper closure"
---

# Deploy Listing to Gateway

## Status

Act

**Owner:** dynamicalsystem

## Context

The 2025-10-imax-listing-scraper loop closed on 2026-09-07 with the system
built and validated end-to-end, but not deployed anywhere. Its one abandoned
outcome test (30-day unattended operation) needs a production deployment.
Simon asked for the same deployment pattern as gazette: GHCR image built by
GitHub Actions, pulled onto the OCI gateway box by podman auto-update as
tinsnip-managed Quadlet units.

This loop also covers the repo's migration to the standard worktree layout
(~/work/listing/{main,ooda}) and its first push to GitHub - it had been a
local-only repo with an in-tree ooda/ directory.

## Observations

From ~/work/gazette/main and ~/work/tinsnip/main (2026-09-07):

- Service repos build multi-arch images (linux/amd64 + linux/arm64 for the
  Oracle Ampere box) via .github/workflows/release.yml on push to main,
  path-filtered to image-affecting files, pushed to
  ghcr.io/dynamicalsystem/<svc> with tags latest / sha / semver and a
  commit-subject label the deploy notifier reads.
- gazette's dockerfile: python:3.13-slim, pip install the package, config via
  env, state on a /data volume, EXPOSE 8000, long-lived serve as default CMD.
- tests.yml runs an offline pytest subset on PRs as a merge gate.
- tinsnip hosts/gateway/ holds the Quadlet units. Long-lived services use
  AutoUpdate=registry, EnvironmentFile= pointing at an on-box secrets file,
  a /data volume under ~/.local/state/dynamicalsystem/<svc>, an HTTP
  HealthCmd, and PodmanArgs=--sdnotify=healthy (health-gated swap; the
  Notify=healthy key is ignored on podman 4.9.3).
- Scheduled work is a one-shot container + systemd timer pair
  (gazette-publish.{container,timer}), sharing the serve container's cached
  :latest image and env file. Timers are TZ-qualified (Europe/London).
- Caddy is the public entrypoint; it reaches services by container name on the
  shared web network (no published app ports). The Caddyfile lives on the box
  at /etc/caddy, not in tinsnip.
- Secrets/env files never live in git; config/*.example templates in tinsnip
  document them, real values come from the password manager.
- Deploys reach the box via podman-auto-update.timer (5 min); changing what
  runs requires git pull + systemctl --user daemon-reload on the box.
- Listing already fits the mold: FastAPI /health on 8000, Config.DB_PATH
  defaults to /data/listing.db, daily maintenance is a one-shot module with
  three-tier exit codes.

## Orientation

Listing maps onto the gazette pattern almost mechanically:

- One image, two run modes: default CMD serves the web app (uvicorn :8000);
  the maintenance sweep is the same image with the command overridden
  (python -m dynamicalsystem.listing.maintenance.daily), exactly as
  gazette-publish reuses the gazette image.
- listing.container mirrors gazette.container (web network, /data volume,
  /health HealthCmd, auto-update, health gate).
- listing-maintain.{container,timer} mirror gazette-publish: one-shot at
  02:00 Europe/London, after the BFI day rolls over.
- In-container logging should go to stdout (journald), not the LOG_FILE
  default of /var/log/listing/daily.log.
- The webserver reads the SQLite file per request, so serve and maintain
  containers sharing the /data volume need no coordination beyond SQLite's
  own locking on the brief maintenance writes.
- Public exposure needs an on-box Caddyfile edit and a DNS record; SITE_URL
  in the env file must match for RSS self-links. Deferred to the on-box
  deployment steps; not blocking image/unit work.

## Decision

Replicate the gazette deployment shape exactly; novelty is risk here and the
pattern is proven on the same box.

1. Migrate the repo to ~/work/listing/{main,ooda} with the control plane on an
   ooda orphan branch; publish to github.com/dynamicalsystem/listing (public,
   so GHCR pulls stay anonymous like gazette/festers).
2. In listing: add dockerfile (python:3.13-slim, pip install, uvicorn CMD),
   release.yml (multi-arch GHCR build, path-filtered), tests.yml (offline
   suite as PR gate), and pin pytest to tests/ so CI never collects the live
   network experiments.
3. In tinsnip: add hosts/gateway/listing.container,
   listing-maintain.container, listing-maintain.timer, and
   config/listing.env.example; update the fleet list in README.
4. On-box steps (manual, Simon): create env file and state dir, git pull,
   daemon-reload, enable units, add Caddy route + DNS when choosing the
   public hostname.

## Action

- Repo migrated to ~/work/listing/{main,ooda}; ooda orphan branch created,
  in-tree ooda/ removed from main; pushed to dynamicalsystem/listing.
- listing branch deploy/containerise: dockerfile, .github/workflows/
  release.yml, .github/workflows/tests.yml, pytest testpaths pin.
- tinsnip (direct to main): listing Quadlet units, env example, README fleet
  update.

## Outcomes

### Outcome 1: Merges to main ship a deployable image

Tests:
- [ ] Push to main touching src/ or dockerfile triggers release.yml and
      publishes ghcr.io/dynamicalsystem/listing:latest (amd64 + arm64)
- [ ] PRs run the offline test suite via tests.yml

### Outcome 2: Gateway box serves the listings site unattended

Tests:
- [ ] listing.container starts on the box, passes its /health gate, and is
      reachable via caddy at the chosen hostname
- [ ] listing-maintain.timer fires at 02:00 Europe/London and the sweep exits 0
- [ ] podman auto-update swaps in a new image after a main merge with no
      manual steps beyond the merge
