# OODA Loop Tracking

This directory contains outcome-based OODA (Observe, Orient, Decide, Act) loop documentation.

## Current Status: [~] ACT Planning

## Active Outcomes

### 2025-10-imax-listing-scraper
**Status**: [x] OBSERVE Complete, [x] ORIENT Complete, [~] ACT In Progress
**Start Date**: 2025-10-24
**Directory**: [2025-10-imax-listing-scraper/](./2025-10-imax-listing-scraper/)

Scrape BFI IMAX schedule, maintain daily listings database, and present data via webpage.

**Progress**:
- [x] OBSERVE Complete (6 audits complete, 2025-10-25)
- [x] ORIENT Complete (6/6 designs complete, 2025-10-26)
- [x] DECIDE Core decisions validated
- [~] ACT In Progress (ACT-04 complete, ACT-05 next, 2025-10-26)

**Key Findings**:
- [x] Data extraction: JavaScript searchResults array (regex + JSON parsing)
- [x] Horizon discovery: performanceDays array (~16 req/day vs 25 originally)
- [x] Completion detection: Runtime-based schedule modeling (near 100% accuracy)
- [x] Change tracking: Designed to learn BFI scheduling patterns

**Quick Links**:
- [README](./2025-10-imax-listing-scraper/README.md) - Outcome overview
- [outcomes.md](./2025-10-imax-listing-scraper/outcomes.md) - Measurable outcomes and tests
- [decision.md](./2025-10-imax-listing-scraper/decision.md) - Architecture decisions
- [access-method-experiment.md](./2025-10-imax-listing-scraper/observe/access-method-experiment.md) - Validation results

## Structure

```
ooda/
├── README.md                                    # This file
└── 2025-10-imax-listing-scraper/                # Outcome folder (date-prefixed)
    ├── README.md                                # Outcome status dashboard
    ├── decision.md                              # Architecture decisions
    ├── outcomes.md                              # Measurable outcomes and tests
    ├── observe/                                 # OBSERVE phase documents
    ├── orient/                                  # ORIENT phase designs
    └── act/                                     # ACT phase implementation
```

## Creating New OODA Outcomes

When starting a new significant architectural change:

1. Create date-prefixed outcome folder: `YYYY-MM-outcome-name/`
2. Create phase subdirectories: `observe/`, `orient/`, `act/`
3. Add outcome README.md with status dashboard
4. Add outcomes.md defining measurable outcomes and tests
5. Add decision.md for architecture decisions
6. Track individual branches in `act/NN-branch-name/` folders
