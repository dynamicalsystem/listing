# BFI IMAX Listing Scraper

**Start Date**: 2025-10-24
**Status**: [x] OBSERVE Phase Complete, ORIENT Phase Starting
**Outcome**: Scrape BFI IMAX schedule, maintain daily listings, present via webpage

## Quick Status

- [x] **OBSERVE** Complete (5 audits complete)
- [~] **ORIENT** Starting
- [x] **DECIDE** Core decisions validated
- [...] **ACT** Not Started

## Overview

This OODA outcome implements a scraper and presentation system for BFI IMAX movie listings.

### Problem Statement

**Current**: No programmatic way to track BFI IMAX listings over time
**Solution**: Automated scraper with daily maintenance and web presentation

## Requirements

1. Scrape BFI IMAX schedule from whatson.bfi.org.uk
2. Extract movie records:
   - Movie title (e.g., "Blue Whales: Return of the Giants (3D)")
   - Movie detail link
   - Showing date
   - Booking link
3. Handle sparse/gappy calendar that fills non-contiguously
4. Create webpage presenting all listings
5. Daily maintenance:
   - Delete yesterday's records
   - Add new listings

## OBSERVE Phase [x]

**Status**: Complete (5 audits complete, 2025-10-25)
**Goal**: Understand BFI website structure, constraints, and data patterns

**Completed**:
- [x] [website-constraints.md](./observe/website-constraints.md) - Cloudflare protection, URL structure
- [x] [access-method-experiment.md](./observe/access-method-experiment.md) - cloudscraper validation
- [x] [html-structure.md](./observe/html-structure.md) - JavaScript rendering, data extraction strategy
- [x] [edge-cases-and-strategy.md](./observe/edge-cases-and-strategy.md) - No results, partial days, horizon scanning
- [x] [completion-heuristic.md](./observe/completion-heuristic.md) - Runtime-based schedule modeling
- [x] [schedule-change-tracking.md](./observe/schedule-change-tracking.md) - Learning BFI patterns over time

**Key Findings**:
- BFI uses client-side JavaScript rendering (extract from searchResults array)
- Calendar is 91.4% sparse (23 days with showings across 267-day span)
- Runtime-based completion detection is canonical (model slots with film runtime + 40min overhead)
- performanceDays array enables single-request horizon discovery
- Change tracking required to learn scheduling patterns

## ORIENT Phase [~]

**Status**: Starting
**Goal**: Design scraper architecture, storage, and presentation layer

**Pending Designs**:
- [ ] Parser module architecture (searchResults, performanceDays, runtimes)
- [ ] SQLite schema (listings, schedules, changes, runtimes)
- [ ] Schedule manager design (horizon scan, dates_to_query, re-scrape logic)
- [ ] Runtime fetcher design (BFI + Wikipedia/IMDb fallback)
- [ ] Daily maintenance workflow
- [ ] Go web server architecture

## DECIDE Phase [x]

**Status**: Core decisions validated
**Goal**: Select architecture and technologies

**Key Decisions Made**:
1. [x] **Scraping**: cloudscraper + Regex/JSON parsing (VALIDATED 2025-10-25)
2. [x] **Languages**: Python (scraper) + Go (web server)
3. [x] **Storage**: SQLite database
4. [x] **Presentation**: Go HTTP server, phased HTML → React, RSS feeds
5. [x] **Maintenance**: Cron inside Docker container
6. [x] **Discovery**: Horizon scan via performanceDays array (REFINED 2025-10-25)
7. [x] **Completion**: Runtime-based schedule modeling (NEW 2025-10-25)
8. [x] **Learning**: Change tracking for pattern discovery (NEW 2025-10-25)

**Refined Strategy**:
- Single performanceDays fetch reveals all dates with showings (replaces two-tier polling)
- Runtime extraction from BFI + Wikipedia fallback enables definitive completion detection
- Change tracking enables learning actual BFI scheduling behavior over time
- Estimated daily load: ~16 requests (down from 25 in original proposal)

See [decision.md](./decision.md) for full rationale and trade-offs.

## ACT Phase [...]

**Status**: Not Started
**Goal**: Implement system

Implementation branches TBD.

## Related Documents

- [outcomes.md](./outcomes.md) - Measurable outcomes and verification tests
- [decision.md](./decision.md) - Architecture decisions (pending)
