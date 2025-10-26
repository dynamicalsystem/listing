# BFI IMAX Listing Scraper

**Start Date**: 2025-10-24
**Status**: [x] OBSERVE Complete, [x] ORIENT Complete, [~] ACT In Progress
**Outcome**: Scrape BFI IMAX schedule, maintain daily listings, present via webpage

## Quick Status

- [x] **OBSERVE** Complete (6 audits complete, 2025-10-25)
- [x] **ORIENT** Complete (6 designs complete, 2025-10-26)
- [x] **DECIDE** Core decisions validated
- [~] **ACT** In Progress (started 2025-10-26)

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

**Status**: Complete (6 audits complete, 2025-10-25)
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

## ORIENT Phase [x]

**Status**: Complete (6/6 complete, 2025-10-26)
**Goal**: Design scraper architecture, storage, and presentation layer

**Completed**:
- [x] [parser-module-design.md](./orient/parser-module-design.md) - Parser module implemented and tested
  - Implementation: `src/dynamicalsystem/listing/scraper/parse.py`
  - Tests: `tests/test_parser.py` (17 tests passing)
  - Package structure: Proper installable namespace package with pytest
- [x] [sqlite-schema-design.md](./orient/sqlite-schema-design.md) - Database schema design
  - 5 core tables: listings, scrape_schedule, schedule_snapshots, schedule_changes, movie_runtimes
  - UTC timezone handling with denormalized UK local fields
  - Field-level change tracking, 30-day snapshot pruning
- [x] [runtime-fetcher-design.md](./orient/runtime-fetcher-design.md) - Runtime fetcher design
  - Multi-tier fallback: BFI → Wikipedia → IMDb → TMDb
  - Database caching strategy
  - Rate limiting and error handling
- [x] [schedule-manager-design.md](./orient/schedule-manager-design.md) - Schedule manager design
  - Horizon scanning via performanceDays array
  - Priority-based re-scrape logic (5 tiers)
  - Field-level change detection
  - Runtime-based completion detection
- [x] [daily-maintenance-workflow.md](./orient/daily-maintenance-workflow.md) - Daily maintenance design
  - Thin wrapper around ScheduleManager
  - Cron configuration inside Docker
  - Logging, monitoring, and health checks
  - Exit codes and error handling
- [x] [go-webserver-design.md](./orient/go-webserver-design.md) - Go web server design
  - Stdlib HTTP server (no framework)
  - HTML templates + RSS feeds
  - Health endpoint for monitoring
  - Mobile-responsive CSS

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

## ACT Phase [~]

**Status**: In Progress (started 2025-10-26)
**Goal**: Implement system

**Strategy**: [PLANNING.md](./act/PLANNING.md)

**Implementation Branches** (5 total):
1. [x] ACT-01: Database Layer (merged 2025-10-26, commit: 805d9e2)
   - [x] schema.py with 5 tables + 2 views
   - [x] db.py with Database class (13 operations)
   - [x] 42 unit tests passing
2. [x] ACT-02: Runtime Fetcher (merged 2025-10-26, commit: e1e1329)
   - [x] runtime.py with Wikipedia-only fetching
   - [x] Database caching (NULL = unknown, INTEGER = known)
   - [x] 16 unit tests + manual live testing (100% success)
3. [x] ACT-03: Schedule Manager (merged 2025-10-26, commit: f5eeb77)
   - [x] changes.py - ChangeDetector with hash-based snapshot comparison
   - [x] completion.py - CompletionChecker with runtime-based gap analysis
   - [x] schedule.py - ScheduleManager orchestrator
   - [x] 31 unit + integration tests passing
   - [x] Simplified re-scrape logic (binary filter vs 5-tier priority)
4. [x] ACT-04: Daily Maintenance (merged 2025-10-26, commit: 23a945e)
   - [x] config.py - Environment variable configuration
   - [x] daily.py - Production maintenance script
   - [x] CLI interface with dry-run, verbose, db-path options
   - [x] Three-tier exit codes (0/1/2) for monitoring
   - [x] 20 unit tests passing
5. [ ] ACT-05: Go Web Server (2-3 days)

**Timeline**: ~2 weeks (estimated)

## Related Documents

- [outcomes.md](./outcomes.md) - Measurable outcomes and verification tests
- [decision.md](./decision.md) - Architecture decisions (pending)
