"""Tests for the web server feeds - guid stability and item content."""

import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from dynamicalsystem.listing.config import Config
from dynamicalsystem.listing.storage.db import Database
from dynamicalsystem.listing.webserver.main import app

FUTURE_DATE = (date.today() + timedelta(days=7)).isoformat()


def make_showing(showing_id: str, title: str, time: str = "19:30") -> dict:
    return {
        'bfi_showing_id': showing_id,
        'movie_title': title,
        'movie_slug': title.lower().replace(' ', '-'),
        'rating': '12A',
        'showing_date': FUTURE_DATE,
        'showing_time': time,
        'showing_datetime_utc': f'{FUTURE_DATE}T{time}:00+00:00',
        'showing_datetime_display': f'{FUTURE_DATE} {time}',
        'format_keywords': 'IMAX',
        'is_laser': False,
        'detail_url_path': 'default.asp?article_id=ABC',
        'availability_status': 'G',
        'availability_count': 150,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient backed by a seeded temporary database."""
    db_path = str(tmp_path / "test.db")
    Database(db_path)  # creates schema
    monkeypatch.setattr(Config, 'DB_PATH', db_path)
    return TestClient(app), Database(db_path)


def guids(rss_text: str) -> list:
    return re.findall(r'<guid[^>]*>([^<]+)</guid>', rss_text)


def test_current_feed_guid_is_showing_id(client):
    tc, db = client
    db.insert_showings([make_showing('SHOW-1', 'Dune: Part Three')])

    rss = tc.get('/rss/current').text
    assert [g for g in guids(rss)] == [f'{Config.SITE_URL}/showing/SHOW-1']


def test_current_feed_guids_stable_across_rescrape(client):
    tc, db = client
    showing = make_showing('SHOW-1', 'Dune: Part Three')
    db.insert_showings([showing])
    first = guids(tc.get('/rss/current').text)

    # re-scrape: same showing inserted again (ignored as duplicate)
    db.insert_showings([showing])
    second = guids(tc.get('/rss/current').text)

    assert first == second
    assert len(second) == 1


def test_new_showing_yields_exactly_one_new_guid(client):
    tc, db = client
    db.insert_showings([make_showing('SHOW-1', 'Dune: Part Three')])
    before = set(guids(tc.get('/rss/current').text))

    # the Dune-preview case: a new showing appears in a later sweep
    db.insert_showings([make_showing('SHOW-2', 'Dune: Part Three', time='14:00')])
    after = set(guids(tc.get('/rss/current').text))

    assert len(after - before) == 1
    assert after - before == {f'{Config.SITE_URL}/showing/SHOW-2'}


def test_replacement_film_in_same_slot_gets_new_guid(client):
    tc, db = client
    db.insert_showings([make_showing('SHOW-1', 'Dune: Part Three')])
    before = set(guids(tc.get('/rss/current').text))

    # BFI swaps the slot: same date/time, different film, different showing id
    db.insert_showings([make_showing('SHOW-9', 'The Odyssey')])
    after = set(guids(tc.get('/rss/current').text))

    assert f'{Config.SITE_URL}/showing/SHOW-9' in after
    assert after != before


def test_current_feed_item_content(client):
    tc, db = client
    db.insert_showings([make_showing('SHOW-1', 'Dune: Part Three')])

    rss = tc.get('/rss/current').text
    assert 'Dune: Part Three' in rss
    assert f'{FUTURE_DATE} at 19:30' in rss
    assert 'Good (150 tickets)' in rss
    assert 'whatson.bfi.org.uk/imax/Online/default.asp?article_id=ABC' in rss


def test_current_feed_count_absent_degrades(client):
    tc, db = client
    showing = make_showing('SHOW-1', 'Dune: Part Three')
    showing['availability_count'] = None
    showing['availability_status'] = 'S'
    db.insert_showings([showing])

    rss = tc.get('/rss/current').text
    assert 'Sold Out' in rss
    assert 'tickets' not in rss


def test_daily_feed_guid_includes_scrape_time(client):
    tc, db = client
    db.insert_showings([make_showing('SHOW-1', 'Dune: Part Three')])

    rss = tc.get('/rss/daily').text
    gs = guids(rss)
    assert len(gs) == 1
    assert gs[0].startswith(f'{Config.SITE_URL}/change/SHOW-1/')


def test_health_endpoint(client):
    tc, db = client
    db.insert_showings([make_showing('SHOW-1', 'Dune: Part Three')])

    body = tc.get('/health').json()
    assert body['status'] == 'healthy'
    assert body['listings_count'] == 1
