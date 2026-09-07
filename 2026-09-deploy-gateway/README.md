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

Done 2026-09-07:

- Repo migrated to ~/work/listing/{main,ooda}; ooda orphan branch created,
  in-tree ooda/ removed from main; repo created at dynamicalsystem/listing
  (public) and both branches pushed.
- listing branch deploy/containerise (fc9d0a5, merged): dockerfile,
  release.yml, tests.yml, pytest testpaths pin, plus two bugs the container
  smoke test surfaced:
  - starlette 1.x (image) removed the legacy TemplateResponse signature the
    webserver used; calls updated to the modern request-first form.
  - Cloudflare 403s cloudscraper's chrome profile from a Linux container
    (TLS fingerprint mismatch) while macOS passes; the firefox/linux profile
    passes from both. Without the container smoke test this would have
    shipped a box that could serve but never scrape.
  - Verified in-container: maintenance dry-run exit 0 (33 dates), /,
    /health, /rss/current all serving.
- tinsnip 68585c3 (pushed to main): hosts/gateway/listing.container,
  listing-maintain.container, listing-maintain.timer,
  config/listing.env.example, fleet list update.
- On-box deployment (2026-09-07, via SSH): tinsnip pulled, install.sh re-run,
  state dir + listing.env created (SITE_URL=https://listing.dynamicalsystem.com
  - wildcard DNS already points *.dynamicalsystem.com at the box),
  /etc/caddy/conf.d/listing.caddy added (festers pattern), caddy reloaded,
  listing.service started (health gate passed), listing-maintain.timer
  enabled. Public HTTPS route verified.
- Experiment: first on-box maintenance run failed - Cloudflare 403s EVERY
  cloudscraper browser profile from the box (OCI datacenter IP range gets
  stricter rules than residential; the firefox-profile fix only helped from
  residential IPs). curl_cffi TLS impersonation passes from the box with
  chrome/firefox/safari profiles. Fetcher swapped to curl_cffi
  (listing 12a72d3, merged aee3338); verified live from the box before the
  code change, and in a local container after it.

Blocked / remaining:

- [x] Push listing main to GitHub (done 2026-09-07 after Simon refreshed
      the gh token with the workflow scope; first GHCR build succeeded).
- [ ] On-box (Simon): create /home/ubuntu/listing/deploy/listing.env from
      config/listing.env.example; mkdir -p
      ~/.local/state/dynamicalsystem/listing; git pull tinsnip; re-run
      install.sh (or symlink the new units); systemctl --user daemon-reload;
      enable/start listing.container and listing-maintain.timer.
- [ ] Choose the public hostname: DNS record, caddy route on the box
      (/etc/caddy/Caddyfile), and SITE_URL in listing.env to match.

## Outcomes

### Outcome 1: Merges to main ship a deployable image

Tests:
- [/] Push to main touching src/ or dockerfile triggers release.yml and
      publishes ghcr.io/dynamicalsystem/listing:latest (amd64 + arm64)
      (verified 2026-09-07: run 34158256631 succeeded; manifest carries
      both arches)
- [ ] PRs run the offline test suite via tests.yml

### Outcome 2: Gateway box serves the listings site unattended

Tests:
- [ ] listing.container starts on the box, passes its /health gate, and is
      reachable via caddy at the chosen hostname
- [ ] listing-maintain.timer fires at 02:00 Europe/London and the sweep exits 0
- [ ] podman auto-update swaps in a new image after a main merge with no
      manual steps beyond the merge
