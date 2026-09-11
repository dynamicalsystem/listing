"""Stateless query filters for the feed endpoints.

A query lives entirely in the URL - bookmarking the filtered feed URL in a
reader is the whole registration model. Filters compose as intersection.

Supported parameters:
    title=dune                  case-insensitive substring on movie title
    dow=fri,sat                 day-of-week set (mon..sun)
    dates=2026-12-15,2026-12-19 explicit date bag (YYYY-MM-DD)
    from=2026-12-01             inclusive lower date bound
    to=2026-12-31               inclusive upper date bound
"""

from datetime import date
from typing import Dict, Optional, Tuple

from dynamicalsystem.listing.webserver.models import Showing

DOW_TOKENS = {
    'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6,
}


class FilterError(ValueError):
    """Invalid filter input; endpoints turn this into a 400."""


def parse_filters(
    title: Optional[str] = None,
    dow: Optional[str] = None,
    dates: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Tuple[Dict, str]:
    """Validate raw query params into a filter spec.

    Returns:
        (spec, description) - description is a short human label for the
        feed title, e.g. "title~dune dow=fri,sat".

    Raises:
        FilterError: on any malformed value.
    """
    spec: Dict = {}
    parts = []

    if title is not None:
        cleaned = title.strip().lower()
        if not cleaned:
            raise FilterError("title must not be empty")
        spec['title'] = cleaned
        parts.append(f"title~{cleaned}")

    if dow is not None:
        tokens = [t.strip().lower() for t in dow.split(',') if t.strip()]
        if not tokens:
            raise FilterError("dow must list days, e.g. dow=fri,sat")
        unknown = [t for t in tokens if t not in DOW_TOKENS]
        if unknown:
            raise FilterError(
                f"unknown day(s): {','.join(unknown)} (use mon..sun)")
        spec['dow'] = {DOW_TOKENS[t] for t in tokens}
        parts.append(f"dow={','.join(tokens)}")

    if dates is not None:
        tokens = [t.strip() for t in dates.split(',') if t.strip()]
        if not tokens:
            raise FilterError("dates must list YYYY-MM-DD values")
        try:
            spec['dates'] = {date.fromisoformat(t).isoformat() for t in tokens}
        except ValueError:
            raise FilterError("dates must be YYYY-MM-DD, comma-separated")
        parts.append(f"dates={','.join(sorted(spec['dates']))}")

    for key, value in (('from', date_from), ('to', date_to)):
        if value is not None:
            try:
                spec[key] = date.fromisoformat(value.strip()).isoformat()
            except ValueError:
                raise FilterError(f"{key} must be YYYY-MM-DD")
            parts.append(f"{key}={spec[key]}")

    return spec, ' '.join(parts)


def matches(showing: Showing, spec: Dict) -> bool:
    """True if the showing satisfies every filter in the spec."""
    if 'title' in spec and spec['title'] not in showing.movie_title.lower():
        return False

    needs_date = {'dow', 'dates', 'from', 'to'} & spec.keys()
    if needs_date:
        try:
            d = date.fromisoformat(showing.showing_date)
        except ValueError:
            return False
        if 'dow' in spec and d.weekday() not in spec['dow']:
            return False
        iso = d.isoformat()
        if 'dates' in spec and iso not in spec['dates']:
            return False
        if 'from' in spec and iso < spec['from']:
            return False
        if 'to' in spec and iso > spec['to']:
            return False

    return True
