"""Change detection for schedule snapshots.

Compares schedule snapshots to detect additions, removals, and modifications
of movie showings.

Design: Pure comparison logic with no external dependencies beyond database.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Dict, List, Optional

from dynamicalsystem.listing.storage.db import Database


logger = logging.getLogger(__name__)


@dataclass
class Change:
    """Detected schedule change."""
    date: str
    change_type: str  # 'first_seen', 'added', 'removed', 'modified'
    showing_time: Optional[str] = None
    movie_title: Optional[str] = None
    details: Optional[str] = None  # JSON string with change details


def compute_snapshot_hash(showings: List[Dict]) -> str:
    """Compute hash of schedule snapshot.

    Hash includes: showing times + movie titles + formats
    Excludes: availability counts (change frequently, don't indicate schedule change)

    Args:
        showings: List of showing dictionaries

    Returns:
        16-character hex hash
    """
    # Normalize showings for hashing
    normalized = sorted([
        {
            'time': s.get('showing_time', ''),
            'title': s.get('movie_title', ''),
            'format': s.get('format_keywords', '')
        }
        for s in showings
    ], key=lambda x: x['time'])

    # Compute hash
    content = json.dumps(normalized, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class ChangeDetector:
    """Detects changes between schedule snapshots.

    Pure comparison logic - fetches previous snapshot from database,
    compares to current, and returns list of changes detected.

    Example:
        detector = ChangeDetector(db)
        changes = detector.detect_changes('2025-10-26', current_showings)
    """

    def __init__(self, db: Database):
        """Initialize change detector.

        Args:
            db: Database instance
        """
        self.db = db

    def detect_changes(
        self,
        date: str,
        current_showings: List[Dict]
    ) -> List[Change]:
        """Detect changes between current showings and previous snapshot.

        Fetches previous snapshot from database internally.

        Args:
            date: Date to check (YYYY-MM-DD)
            current_showings: Current showings from latest scrape

        Returns:
            List of Change objects (added/removed/modified)
        """
        # Get previous snapshot
        previous_snapshot = self.db.get_latest_snapshot(date)

        if not previous_snapshot:
            # First time seeing this date
            logger.info(f"First snapshot for {date}: {len(current_showings)} showings")
            return [Change(
                date=date,
                change_type='first_seen',
                showing_time=None,
                movie_title=None,
                details=json.dumps({
                    'showing_count': len(current_showings)
                })
            )]

        # Get previous showings from snapshot
        previous_showings = previous_snapshot.get('showings', [])

        # Quick check: hash comparison
        current_hash = compute_snapshot_hash(current_showings)
        previous_hash = previous_snapshot.get('snapshot_hash', '')

        if current_hash == previous_hash:
            # No changes detected
            logger.debug(f"No changes detected for {date} (hash match)")
            return []

        # Hash differs, perform detailed comparison
        logger.info(f"Schedule changed for {date}, performing detailed comparison")
        return self._compare_showings(date, previous_showings, current_showings)

    def _compare_showings(
        self,
        date: str,
        previous: List[Dict],
        current: List[Dict]
    ) -> List[Change]:
        """Compare two showing lists and detect specific changes.

        Args:
            date: Date being compared
            previous: Previous showings
            current: Current showings

        Returns:
            List of Change objects
        """
        changes = []

        # Create lookup dicts by showing ID
        prev_by_id = {s['bfi_showing_id']: s for s in previous}
        curr_by_id = {s['bfi_showing_id']: s for s in current}

        # Detect additions
        added_ids = set(curr_by_id.keys()) - set(prev_by_id.keys())
        for showing_id in added_ids:
            showing = curr_by_id[showing_id]
            changes.append(Change(
                date=date,
                change_type='added',
                showing_time=showing.get('showing_time'),
                movie_title=showing.get('movie_title'),
                details=json.dumps({
                    'showing_id': showing_id,
                    'time': showing.get('showing_time'),
                    'title': showing.get('movie_title'),
                    'format': showing.get('format_keywords')
                })
            ))
            logger.info(f"Added showing: {showing.get('showing_time')} {showing.get('movie_title')}")

        # Detect removals
        removed_ids = set(prev_by_id.keys()) - set(curr_by_id.keys())
        for showing_id in removed_ids:
            showing = prev_by_id[showing_id]
            changes.append(Change(
                date=date,
                change_type='removed',
                showing_time=showing.get('showing_time'),
                movie_title=showing.get('movie_title'),
                details=json.dumps({
                    'showing_id': showing_id,
                    'time': showing.get('showing_time'),
                    'title': showing.get('movie_title')
                })
            ))
            logger.info(f"Removed showing: {showing.get('showing_time')} {showing.get('movie_title')}")

        # Detect modifications (field-level changes)
        common_ids = set(prev_by_id.keys()) & set(curr_by_id.keys())
        for showing_id in common_ids:
            prev = prev_by_id[showing_id]
            curr = curr_by_id[showing_id]

            field_changes = self._compare_fields(prev, curr)
            if field_changes:
                changes.append(Change(
                    date=date,
                    change_type='modified',
                    showing_time=curr.get('showing_time'),
                    movie_title=curr.get('movie_title'),
                    details=json.dumps({
                        'showing_id': showing_id,
                        'time': curr.get('showing_time'),
                        'title': curr.get('movie_title'),
                        'changes': field_changes
                    })
                ))
                logger.info(f"Modified showing: {curr.get('showing_time')} {curr.get('movie_title')}")

        return changes

    def _compare_fields(self, prev: Dict, curr: Dict) -> Dict:
        """Compare fields between two showings.

        Args:
            prev: Previous showing
            curr: Current showing

        Returns:
            Dict of field changes (field_name -> {from, to})
        """
        fields_to_check = [
            'showing_time',
            'format_keywords',
            'availability_status',
            'availability_count',
            'rating'
        ]

        changes = {}
        for field in fields_to_check:
            prev_val = prev.get(field)
            curr_val = curr.get(field)

            if prev_val != curr_val:
                changes[field] = {
                    'from': prev_val,
                    'to': curr_val
                }

        return changes
