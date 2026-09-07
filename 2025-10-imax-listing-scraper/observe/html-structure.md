# HTML Structure Analysis

**Date**: 2025-10-25
**File Analyzed**: `experiments/bfi_cloudscraper_2025-10-26.html` (103,852 bytes)
**Status**: [x] Complete

## TL;DR

BFI uses **client-side JavaScript rendering**. Movie data is embedded as a JavaScript array, NOT static HTML.

**Parser Strategy**: Extract `searchResults` array from JavaScript, parse as JSON.

---

## Architecture Discovery

### Page Rendering Method

The BFI search results page uses a client-side JavaScript widget to render movie listings:

1. **Data Source**: JavaScript `searchResults` array embedded in `<script>` tag
2. **Widget**: `SearchWebWidget2` registered via `TabularSearchResultsWidget.js`
3. **Rendering**: Client-side (JavaScript renders after page load)

**Implication**: We extract data from JavaScript, not HTML DOM.

---

## Data Location

### JavaScript Variable

**Location**: `<script>` tag in HTML head section (around line 362)

**Variable Path**: `articleContext.searchResults`

**Format**: Array of arrays (each inner array is one movie showing)

**Example**:
```javascript
searchResults : [
  [ "62F928E8-F582-4027-B3D9-8765A1A5605C", "P", "IMAX", "IMAX BIG SCREEN",
    "frank_26oct25", "Frankenstein", "Frankenstein",
    "Sunday 26 October 2025 10:45", "10:45", "26", "9", "2025",
    ... // 90+ more fields
  ],
  [ /* next showing */ ],
  ...
]
```

---

## Data Schema

### Field Indices

Based on `searchHeaders` array (line 360-361), key fields:

| Index | Field Name | Example | Notes |
|-------|-----------|---------|-------|
| 0 | `id` | `62F928E8-F582-4027-B3D9-8765A1A5605C` | Unique showing ID |
| 4 | `name` | `frank_26oct25` | Internal slug |
| 5 | `description` | `Frankenstein` | **Movie title** |
| 7 | `start_date` | `Sunday 26 October 2025 10:45` | Full datetime string |
| 8 | `start_date_time` | `10:45` | Time only |
| 9 | `start_date_date` | `26` | Day of month |
| 10 | `start_date_month` | `9` | **0-indexed** month (Oct=9) |
| 11 | `start_date_year` | `2025` | Year |
| 14 | `sales_status` | `S` | On sale status |
| 15 | `availability_status` | `L`, `G` | Limited / Good |
| 17 | `keywords` | `IMAX with Laser,3D` | **Format indicators** |
| 18 | `additional_info` | `default.asp?doWork::...` | **Movie detail URL** (relative) |
| 42 | `performance_id` | `479731` | Performance ID |
| 43 | `rating` | `15`, `12A` | Age rating |

### Booking Links

**Not in searchResults array**. Booking links are generated client-side by widget based on showing ID and performance ID.

**Pattern**: `default.asp?BOparam::WScontent::loadArticle::article_id={showing_id}&...`

---

## Sample Data

### Extracted Showings (2025-10-26)

1. **Frankenstein**
   - Time: 10:45
   - Format: IMAX with Laser
   - Availability: Limited (38 seats)

2. **Tron: Ares (3D)**
   - Time: 14:10
   - Format: IMAX with Laser, 3D
   - Availability: Good (332 seats)

3. **One Battle After Another**
   - Time: 17:00
   - Format: imax, 70mm
   - Availability: Good (255 seats)

4. **Chainsaw Man - The Movie: Reze Arc**
   - Time: 20:30
   - Format: English subtitles, IMAX with Laser
   - Availability: Limited (85 seats)

---

## Parser Implementation

### Strategy: Regex + JSON

**Approach**:
1. Load HTML as string
2. Use regex to find `searchResults : [ ... ]` array
3. Extract array content
4. Parse as JSON
5. Map indices to structured fields

**Why Not BeautifulSoup HTML Parsing?**
- No static HTML elements to select
- Data is in JavaScript, not DOM
- BeautifulSoup still useful for HTML escaping/validation

### Regex Pattern

```python
pattern = r'searchResults\s*:\s*\[\s*((?:\[.*?\],?\s*)+)\]'
match = re.search(pattern, html_content, re.DOTALL)
array_content = match.group(1)
json_data = json.loads(f"[{array_content}]")
```

### Validation Script

**File**: `experiments/test_parser.py`

**Result**: Successfully extracted 4 showings from sample HTML

**Output**: `experiments/parsed_listings.json`

---

## Data Availability

### Fields We Can Extract

- [x] Movie title
- [x] Showing date (YYYY-MM-DD)
- [x] Showing time (HH:MM)
- [x] Full datetime string
- [x] Format indicators (3D, IMAX Laser, 70mm, subtitles)
- [x] Movie detail URL (relative path)
- [x] Showing ID (unique)
- [x] Availability status
- [x] Age rating

### Fields Not Available

- [ ] Booking URL (generated client-side, not in data)
- [ ] Sold-out indicator (can infer from `availability_status`)
- [ ] Venue name (always "BFI IMAX" for this site)
- [ ] Prices (empty in searchResults, likely session-dependent)

### Venue Information

**Venue**: Always "BFI IMAX, Waterloo"
- Hard-code in schema
- Venue ID in data: `7666F32B-DBF8-4F92-BA4C-397D5C1FAD88`

---

## Format Detection

### Keywords Field (Index 17)

Comma-separated format indicators:

**Common Formats**:
- `IMAX with Laser` - Standard IMAX projection
- `3D` - 3D screening
- `imax,70mm` or `15/70 IMAX` - 70mm film projection
- `English subtitles`, `subtitles` - Accessibility

**Parsing Strategy**:
```python
keywords = record[17].split(',')
is_3d = '3D' in keywords
is_70mm = '70mm' in keywords or '15/70' in keywords
has_subtitles = 'subtitles' in keywords or 'English subtitles' in keywords
```

---

## Edge Cases

### No Results

**Question**: What does HTML look like when no showings found?

**Test Needed**: Fetch date with no listings (e.g., far past)

**Expected**: Empty `searchResults: []` array

### Multiple Days

**Current Sample**: Single day (2025-10-26)

**Question**: How are multi-day results structured?

**Test Needed**: Fetch date range (e.g., 2025-10-26 to 2025-11-26)

**Expected**: All showings in one array, multiple dates mixed

### Calendar Performance Days

**Observed**: `performanceDays` array (line 388) contains ALL performance datetimes

**Use Case**: Could use for "days with showings" calendar view

**Format**: `["2025-10-25T10:45:00.000", "1"]` (datetime, count)

---

## CSS Selectors (For Verification)

Even though data extraction is JavaScript-based, here are HTML elements:

### Page Structure

```css
div#content                          /* Main content wrapper */
  div.bodyDetails                    /* Article body */
    div#searchBox                    /* Search form */
    div[role="main"]                 /* Main article container */
      div#search                     /* Widget container */
        div[name="avWidget"]         /* Widget registration */
```

### Widget Registration

```html
<div name="avWidget" id="avWidget_49C49C83-6BA0-420C-A784-9B485E36E2E0_...">
  <script type="text/javascript">
    registerWidget("SearchWebWidget2", "avWidget_...", {...});
  </script>
</div>
```

**Note**: Widget renders content after page load. Static HTML has no movie listings.

---

## Booking URL Construction

### Movie Detail URL

**Available**: Relative path in `additional_info` (index 18)

**Base URL**: `https://whatson.bfi.org.uk/imax/Online/`

**Full URL**: `{base_url}{detail_url_path}`

**Example**:
```
https://whatson.bfi.org.uk/imax/Online/default.asp?doWork::WScontent::loadArticle=Load&BOparam::WScontent::loadArticle::article_id=ABCC0BB0-C879-4320-A7E6-DFAAA0C2B7B8&BOparam::WScontent::loadArticle::context_id=62F928E8-F582-4027-B3D9-8765A1A5605C
```

### Booking URL

**Not directly available** in searchResults.

**Widget Behavior**: Widget generates booking link client-side based on showing ID.

**Decision**: Store movie detail URL, let users navigate from there to booking.

**Alternative**: Reverse-engineer booking URL pattern from widget JavaScript (future enhancement).

---

## Sold-Out Detection

### Availability Status (Index 15)

Observed values:
- `G` = Good availability
- `L` = Limited availability
- `S` = Sold out (inferred, not seen in sample)

### Availability Number (Index 16)

Seats remaining:
- `332` = 332 seats available
- `38` = 38 seats available

**Sold-Out Logic**:
```python
is_sold_out = (availability_status == 'S') or (availability_num == '0')
```

---

## Next Steps

### Immediate (ORIENT Phase)

1. **Design Parser Module**
   - `src/dynamicalsystem/listing/scraper/parse.py`
   - Function: `parse_search_results(html: str) -> List[Dict]`
   - Integrate with `BFIFetcher`

2. **Test Edge Cases**
   - Fetch date with no listings
   - Fetch wide date range
   - Fetch far future date

3. **Validate Field Mapping**
   - Confirm all indices correct
   - Handle missing/null values
   - Test with multiple samples

### Future Enhancements

- [ ] Extract booking URL pattern from widget JavaScript
- [ ] Parse movie detail page for additional metadata
- [ ] Extract pricing information (if available)
- [ ] Capture images/posters

---

## Files Created

- `experiments/test_parser.py` - Parser validation script
- `experiments/parsed_listings.json` - Sample parsed output (4 showings)

---

## Conclusion

**Finding**: BFI uses client-side JavaScript rendering, NOT static HTML.

**Solution**: Extract `searchResults` JavaScript array, parse as JSON.

**Status**: Parser strategy validated, ready for ORIENT phase implementation.

**No CSS Selectors Needed**: Data extraction is regex + JSON, not DOM traversal.
