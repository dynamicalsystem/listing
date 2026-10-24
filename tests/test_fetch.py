"""Tests for fetch.py - Cloudflare challenge detection and request accounting."""

import logging
from unittest.mock import MagicMock

import pytest

from dynamicalsystem.listing.scraper.fetch import BFIFetcher, CloudflareChallenge


def make_response(status_code=200, headers=None, text="<html>searchResults</html>"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text
    return resp


@pytest.fixture
def fetcher():
    f = BFIFetcher()
    f.scraper = MagicMock()
    return f


def test_200_returns_text_and_counts_request(fetcher):
    fetcher.scraper.get.return_value = make_response(200, {'cf-ray': 'abc123-LHR'})

    html = fetcher.fetch('2026-11-05')

    assert 'searchResults' in html
    assert fetcher.stats.requests == 1
    assert fetcher.stats.challenges == 0
    assert fetcher.stats.last_cf_ray == 'abc123-LHR'


def test_403_with_cf_mitigated_header_raises_challenge(fetcher, caplog):
    fetcher.scraper.get.return_value = make_response(
        403, {'server': 'cloudflare', 'cf-mitigated': 'challenge', 'cf-ray': 'a4fc2b87-LHR'},
        text="<html><title>Just a moment...</title></html>")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(CloudflareChallenge) as exc:
            fetcher.fetch('2026-11-05')

    assert exc.value.cf_ray == 'a4fc2b87-LHR'
    assert exc.value.cf_mitigated == 'challenge'
    assert exc.value.status_code == 403
    assert fetcher.stats.requests == 1
    assert fetcher.stats.challenges == 1
    assert fetcher.stats.last_challenge_at is not None
    assert 'cf-ray=a4fc2b87-LHR' in caplog.text
    assert 'cf-mitigated=challenge' in caplog.text
    fetcher.scraper.get.return_value.raise_for_status.assert_not_called()


def test_403_with_interstitial_body_but_no_header_is_still_a_challenge(fetcher):
    fetcher.scraper.get.return_value = make_response(
        403, {'server': 'cloudflare'}, text="<html>Just a moment...</html>")

    with pytest.raises(CloudflareChallenge):
        fetcher.fetch('2026-11-05')
    assert fetcher.stats.challenges == 1


def test_plain_403_is_not_counted_as_challenge(fetcher):
    resp = make_response(403, {'server': 'nginx'}, text="<html>Forbidden</html>")
    resp.raise_for_status.side_effect = RuntimeError("HTTP Error 403")
    fetcher.scraper.get.return_value = resp

    with pytest.raises(RuntimeError):
        fetcher.fetch('2026-11-05')
    assert fetcher.stats.requests == 1
    assert fetcher.stats.challenges == 0


def test_500_defers_to_raise_for_status(fetcher):
    resp = make_response(500, {'cf-ray': 'zzz-LHR'}, text="error")
    resp.raise_for_status.side_effect = RuntimeError("HTTP Error 500")
    fetcher.scraper.get.return_value = resp

    with pytest.raises(RuntimeError):
        fetcher.fetch('2026-11-05')
    assert fetcher.stats.challenges == 0


def test_counters_accumulate_across_calls(fetcher):
    ok = make_response(200)
    challenge = make_response(403, {'cf-mitigated': 'challenge', 'cf-ray': 'r1'})
    fetcher.scraper.get.side_effect = [ok, challenge, ok, challenge, challenge]

    for _ in range(5):
        try:
            fetcher.fetch('2026-11-05')
        except CloudflareChallenge:
            pass

    assert fetcher.stats.requests == 5
    assert fetcher.stats.challenges == 3
