# Parser Tests

Tests for the BFI IMAX parser module (MVP/PoC).

## Setup

Install package in editable mode:

```bash
uv pip install -e .
```

## Running Tests

Run all tests:

```bash
pytest tests/
```

Run with verbose output:

```bash
pytest tests/ -v
```

Run specific test:

```bash
pytest tests/test_parser.py::TestParseSearchResults::test_parse_oct26_showings -v
```

## Test Coverage

- `test_parser.py`: Parser module validation
  - Parsing showings from HTML
  - Extracting performance days
  - Month conversion (0-indexed to 1-indexed)
  - Format keyword parsing
  - Edge cases (no results, invalid HTML)

## Test Fixtures

Tests use sample HTML files from `experiments/`:
- `bfi_cloudscraper_2025-10-26.html`: 4 showings
- `bfi_no_results_2025-10-27.html`: No results
