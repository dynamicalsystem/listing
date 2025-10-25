# OODA Loop Workflow

This document explains how to track OODA loops through branch development and mark them complete.

## Overview

Each ACT task corresponds to:
1. An OODA design document (OBSERVE/ORIENT phase output)
2. A git branch (ACT phase implementation)
3. A merge to main (completion)

## Phase Progression

### OBSERVE Phase
**Goal**: Understand current state and constraints

**Activities**:
- Audit existing systems
- Document constraints
- Identify patterns
- Gather requirements

**Completion Criteria**:
- All unknowns documented
- Constraints identified
- Sufficient understanding to design

### ORIENT Phase
**Goal**: Design solutions

**Activities**:
- Propose architectures
- Design data models
- Plan algorithms
- Document alternatives

**Completion Criteria**:
- Multiple design options documented
- Trade-offs analyzed
- Designs reference OBSERVE findings

### DECIDE Phase
**Goal**: Select approach

**Activities**:
- Evaluate designs against requirements
- Document decisions and rationale
- Get confirmation on key choices
- Finalize architecture

**Completion Criteria**:
- decision.md updated with choices
- Trade-offs documented
- Alternatives and rejections explained
- Key decisions confirmed

### ACT Phase
**Goal**: Implement

**Activities**:
- Create implementation branches
- Write code
- Test against outcomes
- Merge to main

**Completion Criteria**:
- All outcomes verified
- Tests pass
- Documentation updated

## Branch Tracking with BRANCH.md

Each ACT phase has its own `BRANCH.md` file for detailed tracking.

### BRANCH.md Structure

```markdown
# Branch Status: <Task Name>

**Branch**: `feature/branch-name`
**Status**: [...] Not Started | [~] In Progress | [x] Complete
**Started**: YYYY-MM-DD
**Completed**: YYYY-MM-DD

## Quick Links

- **Plan**: [plan.md](./plan.md)
- **OBSERVE/ORIENT**: [../../observe/doc.md](../../observe/doc.md)
- **Merge Commit**: abc123f

## Timeline

| Event | Date | Notes |
|-------|------|-------|
| Branch created | YYYY-MM-DD | feature/branch-name |
| First commit | YYYY-MM-DD | Description |
| Testing | YYYY-MM-DD | Test results summary |
| Outcome verified | YYYY-MM-DD | Validation results |
| Merged to main | YYYY-MM-DD | Direct merge or PR# |

## Testing

- [ ] Test case 1
- [ ] Test case 2
- [ ] Outcome verification

## Issues Encountered

1. **Issue title**: Description
   - Resolution: How it was fixed

## Notes

Any significant observations or decisions during implementation.
```

### When to Update BRANCH.md

1. **On branch creation** - set status to "In Progress", add start date
2. **During development** - add timeline events, testing results, issues as they occur
3. **On completion** - set status to "Complete", add completion date and merge commit

Don't batch updates - update BRANCH.md as events happen for better audit trail.

## Workflow Steps

### 1. Starting a Branch

When starting work on an ACT task:

```bash
# Create and checkout branch
git checkout -b feature/initial-scraper

# Update ooda/2025-10-imax-listing-scraper/README.md
# Change status from "[...] Not Started" to "[~] In Progress"
# Add start date

# Update ooda/README.md top-level status

# Commit the status update
git add ooda/
git commit -m "docs(ooda): Start ACT-1 initial scraper"
```

### 2. During Development

**Reference OODA docs in commit messages:**
```bash
git commit -m "feat(scraper): Add BFI page fetcher

Implements headless browser approach per website-constraints.md findings.

Refs: ooda/2025-10-imax-listing-scraper/observe/website-constraints.md"
```

**Link to implementation plan:**
```bash
git commit -m "test(scraper): Verify movie extraction

Tests outcome #1 from outcomes.md.

Refs: ooda/2025-10-imax-listing-scraper/outcomes.md"
```

### 3. After Merge

**Update ooda/2025-10-imax-listing-scraper/README.md:**
```markdown
### ACT-1: Initial Scraper
**Branch**: `feature/initial-scraper`
**Status**: [x] Complete
**Started**: 2025-10-25
**Completed**: 2025-10-26
**Merge Commit**: `abc123f`
```

**Update ooda/README.md** with overall progress.

**Commit to main:**
```bash
git checkout main
git pull
git add ooda/
git commit -m "docs(ooda): Mark ACT-1 complete

Initial scraper implementation merged.

Merge commit: abc123f"
git push
```

## Status Indicators

Use these in README.md files:

- `[...]` **Not Started** - Branch not created yet
- `[~]` **In Progress** - Branch active, commits being made
- `[?]` **In Review** - PR open, awaiting review
- `[x]` **Complete** - Merged to main
- `[ ]` **Not done** - Task not completed
- `[||]` **Paused** - Temporarily on hold (with reason)

## Commit Message Format

```
<type>(<scope>): <subject>

<body>

Refs: ooda/2025-10-imax-listing-scraper/<document>.md
```

**Types:** feat, fix, docs, test, refactor, chore

**Scopes:** scraper, storage, web, maintenance, ooda

## Integration with Todos

The todo list tracks high-level progress:
```bash
# When starting ACT-1
TodoWrite: Mark ACT-1 "in_progress"

# When completing ACT-1
TodoWrite: Mark ACT-1 "completed"
```

Todos provide quick status, README.md provides detailed tracking.

## Tips

1. **Update status immediately** when starting/completing branches
2. **Always reference OODA docs** in commits for traceability
3. **Keep README.md current** - it's the single source of truth for status
4. **Document issues as they occur** in BRANCH.md
5. **Use consistent formatting** for easy parsing/scripting
6. **Verify outcomes** before marking complete
