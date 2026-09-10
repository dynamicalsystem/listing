# Archived

- **Closed**: 2026-09-10 07:15 UTC
- **Status**: Succeeded
- **Summary**: Listing deployed to the gateway box in the gazette pattern
  (GHCR image via Actions, tinsnip Quadlets, podman auto-update) and live at
  https://listing.dynamicalsystem.com; repo migrated to the worktree layout
  and published to GitHub. Key experiment finding: Cloudflare blocks all
  cloudscraper profiles from datacenter IPs - curl_cffi TLS impersonation
  is required.
- **Outcomes**: 5/5 tests passed (image build+publish, PR test gate, serve
  container health-gated behind caddy, timer sweeps exit 0 on schedule for
  three consecutive days, unattended auto-update swap).
- **Follow-up**: [2026-09-soak-test](../2026-09-soak-test/README.md) - the
  30-day unattended-operation test carried forward from the scraper loop.
