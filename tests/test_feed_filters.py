"""Tests for stateless feed query filters (the query-feeds act)."""

import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from dynamicalsystem.listing.config import Config
from dynamicalsystem.listing.storage.db import Database
from dynamicalsystem.listing.webserver.filters import (
    FilterError, matches, parse_filters,
)
from dynamicalsystem.listing.webserver.main import app
from tests.test_webserver import make_showing

# next Friday and the following Saturday/Sunday, always in the future
_today = date.today()
FRIDAY = (_today + timedelta(days=(4 - _today.weekday()) % 7 + 7)).isoformat()
SATURDAY = (date.fromisoformat(FRIDAY) + timedelta(days=1)).isoformat()
SUNDAY = (date.fromisoformat(FRIDAY) + timedelta(days=2)).isoformat()


def showing_on(showing_id, title, day):
    s = make_showing(showing_id, title)
    s['showing_date'] = day
    s['showing_datetime_utc'] = f'{day}T19:30:00+00:00'
    return s


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    Database(db_path)
    monkeypatch.setattr(Config, 'DB_PATH', db_path)
    db = Database(db_path)
    db.insert_showings([
        showing_on('DUNE-FRI', 'Dune: Part Three', FRIDAY),
        showing_on('DUNE-SUN', 'Dune: Part Three', SUNDAY),
        showing_on('ODYS-FRI', 'The Odyssey', FRIDAY),
        showing_on('ODYS-SAT', 'The Odyssey', SATURDAY),
    ])
    return TestClient(app)


def guids(rss_text):
    return [g.rsplit('/', 1)[-1]
            for g in re.findall(r'<guid[^>]*>([^<]+)</guid>', rss_text)]


# ---------------------------------------------------------------- unit level

def test_parse_rejects_bad_dow():
    with pytest.raises(FilterError):
        parse_filters(dow='fri,funday')


def test_parse_rejects_bad_dates():
    with pytest.raises(FilterError):
        parse_filters(dates='next tuesday')
    with pytest.raises(FilterError):
        parse_filters(date_from='12/01/2026')


def test_matches_composes_as_intersection():
    spec, _ = parse_filters(title='dune', dow='fri')
    from dynamicalsystem.listing.webserver.models import Showing
    hit = Showing(**{k: v for k, v in showing_on('X', 'Dune: Part Three', FRIDAY).items()
                     if k in Showing.model_fields})
    miss = Showing(**{k: v for k, v in showing_on('X', 'Dune: Part Three', SUNDAY).items()
                      if k in Showing.model_fields})
    assert matches(hit, spec)
    assert not matches(miss, spec)


# ------------------------------------------------------------ endpoint level

def test_title_filter_serves_only_matches(client):
    rss = client.get('/rss/current?title=dune').text
    assert sorted(guids(rss)) == ['DUNE-FRI', 'DUNE-SUN']
    assert 'The Odyssey' not in rss


def test_title_filter_surfaces_new_showing_as_one_item(client, tmp_path):
    before = set(guids(client.get('/rss/current?title=dune').text))
    Database(Config.DB_PATH).insert_showings(
        [showing_on('DUNE-SAT', 'Dune: Part Three', SATURDAY)])
    after = set(guids(client.get('/rss/current?title=dune').text))
    assert after - before == {'DUNE-SAT'}


def test_dow_filter(client):
    rss = client.get('/rss/current?dow=fri,sat').text
    assert sorted(guids(rss)) == ['DUNE-FRI', 'ODYS-FRI', 'ODYS-SAT']


def test_date_bag_filter(client):
    rss = client.get(f'/rss/current?dates={SATURDAY},{SUNDAY}').text
    assert sorted(guids(rss)) == ['DUNE-SUN', 'ODYS-SAT']


def test_range_filter(client):
    rss = client.get(f'/rss/current?from={SATURDAY}&to={SUNDAY}').text
    assert sorted(guids(rss)) == ['DUNE-SUN', 'ODYS-SAT']


def test_filters_compose_as_intersection(client):
    rss = client.get(f'/rss/current?title=odyssey&dow=fri').text
    assert guids(rss) == ['ODYS-FRI']


def test_no_match_yields_valid_empty_feed(client):
    resp = client.get('/rss/current?title=zardoz')
    assert resp.status_code == 200
    assert '<rss' in resp.text
    assert guids(resp.text) == []


def test_invalid_query_returns_400_not_500(client):
    assert client.get('/rss/current?dow=funday').status_code == 400
    assert client.get('/rss/current?dates=whenever').status_code == 400
    assert client.get('/rss/current?from=01-12-2026').status_code == 400
    assert 'unknown day' in client.get('/rss/current?dow=funday').text


def test_filtered_feed_title_labels_the_query(client):
    rss = client.get('/rss/current?title=dune&dow=fri').text
    assert '<title>BFI IMAX - Current Schedule (title~dune dow=fri)</title>' in rss


def test_unfiltered_feed_unchanged(client):
    rss = client.get('/rss/current').text
    assert '<title>BFI IMAX - Current Schedule</title>' in rss
    assert len(guids(rss)) == 4


def test_daily_feed_accepts_same_filters(client):
    rss = client.get('/rss/daily?title=dune').text
    # daily guids are /change/<showing id>/<scraped_at>
    full_guids = re.findall(r'<guid[^>]*>([^<]+)</guid>', rss)
    assert full_guids
    assert all('/change/DUNE' in g for g in full_guids)
    assert client.get('/rss/daily?dow=funday').status_code == 400
