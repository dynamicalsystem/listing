# BFI IMAX Website Constraints

**Date**: 2025-10-24
**Updated**: 2025-10-25
**Status**: [~] Access method validated, HTML analysis pending
**Phase**: OBSERVE

## Purpose

Document the BFI IMAX website structure, access patterns, anti-scraping measures, and technical constraints.

## Target URL

Primary schedule page:
```
https://whatson.bfi.org.uk/imax/Online/default.asp
```

Query parameters for date filtering:
```
?BOset::WScontent::SearchCriteria::search_from=2025-10-25
&BOset::WScontent::SearchCriteria::search_to=2025-10-25
&doWork::WScontent::search=1
&BOparam::WScontent::search::article_search_id=49C49C83-6BA0-420C-A784-9B485E36E2E0
```

## Observed Constraints

### 1. Anti-Automation Measures

**Finding**: Cloudflare "Managed Challenge" bot protection
**Date Observed**: 2025-10-24
**Validated Solution**: 2025-10-25

**Test Results**:
- [x] Basic HTTP (curl, requests): 403 Forbidden + Cloudflare challenge page
- [x] HTTP with browser User-Agent: 403 Forbidden + Cloudflare challenge page
- [/] **cloudscraper library**: SUCCESS (103,852 bytes HTML retrieved)

**Cloudflare Challenge Details**:
- JavaScript crypto puzzle must be solved
- Returns "Just a moment..." page to simple HTTP clients
- Requires JavaScript execution or Cloudflare-bypass library
- cloudscraper successfully bypasses without headless browser

**Validated Approach**:
```python
import cloudscraper
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'darwin', 'desktop': True}
)
html = scraper.get(url).text  # Works!
```

**Access Requirements**:
- [x] cloudscraper library handles Cloudflare challenge
- [x] No manual User-Agent spoofing needed
- [x] No cookies manually required (handled by cloudscraper)
- [x] JavaScript challenge solved automatically
- [ ] Rate limiting: Unknown (observe during testing)

**Decision Impact**:
- **Scraper approach validated**: HTTP library (cloudscraper) + BeautifulSoup works
- No headless browser needed (saves resources, reduces complexity)
- Aligns with priorities: simplicity, low resource, ease of maintenance

### 2. URL Structure

**Pattern**:
```
Base: https://whatson.bfi.org.uk/imax/Online/default.asp
Parameters:
  - BOset::WScontent::SearchCriteria::search_from=YYYY-MM-DD
  - BOset::WScontent::SearchCriteria::search_to=YYYY-MM-DD
  - doWork::WScontent::search=1
  - BOparam::WScontent::search::article_search_id=49C49C83-6BA0-420C-A784-9B485E36E2E0
  - BOset::WScontent::SearchCriteria::search_criteria= (empty)
  - Other filters (venue, city, month, type, category): empty for IMAX-only
```

**Validated**:
- [x] article_search_id appears constant: 49C49C83-6BA0-420C-A784-9B485E36E2E0
- [x] search_from and search_to can be same date (single-day query)
- [x] URL structure works with cloudscraper

**Pending Questions**:
- [ ] What happens with invalid date ranges?
- [ ] Can search_to be far future, or does it limit range?
- [ ] What response for dates with no listings?

### 3. Calendar Sparsity

**User Report**: Calendar is "gappy and gets filled in non-contiguously"

**Observations Needed**:
- [ ] How far ahead does calendar extend?
- [ ] How frequently do new dates get added?
- [ ] Do listings appear/disappear or only appear?
- [ ] Are there time-of-day patterns (e.g., updates at midnight)?

### 4. HTML Structure

**Status**: Not yet observed (blocked by 403)

**Information Needed**:
- [ ] How are movie listings structured in HTML?
- [ ] What CSS classes/IDs identify movies?
- [ ] Where are movie detail links?
- [ ] Where are booking links?
- [ ] How are dates represented?
- [ ] How are movie formats indicated (3D, IMAX 70mm, etc.)?
- [ ] What indicates sold out vs available?

## Investigation Plan

### Phase 1: Manual Browser Inspection
- [ ] Load page in browser
- [ ] Inspect HTML structure
- [ ] Identify movie listing elements
- [ ] Identify link patterns
- [ ] Document CSS selectors
- [ ] Check for JavaScript rendering

### Phase 2: Access Pattern Testing [x] COMPLETE
- [x] Try different User-Agent strings (failed)
- [x] Test with curl + browser headers (failed)
- [x] Test with cloudscraper (SUCCESS)
- [x] Document working approach (cloudscraper + BeautifulSoup)
- [ ] Monitor for rate limiting (ongoing during development)

### Phase 3: Data Pattern Analysis
- [ ] Query multiple dates
- [ ] Identify date ranges with/without listings
- [ ] Document format indicators (3D, 70mm, etc.)
- [ ] Test edge cases (invalid dates, far future)
- [ ] Document error responses

### Phase 4: Change Detection
- [ ] Scrape same date multiple times over days
- [ ] Document when new listings appear
- [ ] Identify patterns in calendar updates
- [ ] Test if listings can disappear

## Completed Validations

**2025-10-25**: Access method testing
- Validated cloudscraper bypasses Cloudflare
- Retrieved 103,852 bytes of HTML for 2025-10-26
- BeautifulSoup successfully parses response
- Sample HTML saved: `experiments/bfi_cloudscraper_2025-10-26.html`
- Page title: "Search results"

**Decision Validation**:
- HTTP library approach (cloudscraper) works [/]
- No headless browser required [/]
- BeautifulSoup compatible [/]

## Next Steps

1. [x] Validate access method (cloudscraper)
2. [ ] Inspect saved HTML to document structure
3. [ ] Write HTML parser for movie listings
4. [ ] Create ORIENT phase designs based on findings
5. [ ] Update decision.md with validated approach

## Related Documents

- [Outcomes](../outcomes.md) - What we're trying to achieve
- [Decision](../decision.md) - Architecture decisions (pending findings)
