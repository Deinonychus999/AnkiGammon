"""The desktop → trainer handoff server, spoken to the way the trainer does."""

import json
import re
import threading
import urllib.error
import urllib.request

import pytest

from ankigammon.trainer_handoff import PackHandoff, origin_allowed

PACK = {"format": "ankigammon-position-pack", "version": 1,
        "deck": {"title": "Handoff test"}, "positions": [{"xgid": "XGID=-a"}]}
SITE = "https://ankigammon.com"


def request(handoff, path=None, origin=SITE, method="GET"):
    url = f"http://127.0.0.1:{handoff.port}{path or '/pack/' + handoff.key}"
    headers = {"Origin": origin} if origin else {}
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def receipt(handoff, key=None, origin=SITE):
    return request(handoff, path=f"/done/{key or handoff.key}", origin=origin, method="POST")


@pytest.fixture
def served():
    events = {"delivered": threading.Event(), "timeout": threading.Event()}
    handoffs = []

    def make(timeout=30):
        h = PackHandoff(PACK, on_delivered=events["delivered"].set,
                        on_timeout=events["timeout"].set, timeout=timeout)
        h.start()
        handoffs.append(h)
        return h

    yield make, events
    for h in handoffs:
        h.close()


def test_url_matches_the_trainer_contract(served):
    make, _ = served
    h = make()
    assert re.fullmatch(r"https://ankigammon\.com/train/#desktop=\d{1,5}\.[0-9a-f]{32}", h.url())


def test_trainer_gets_the_pack(served):
    make, _ = served
    h = make()
    status, headers, body = request(h)
    assert status == 200
    assert json.loads(body) == PACK
    assert headers["Access-Control-Allow-Origin"] == SITE


def test_a_fetch_alone_is_not_delivery(served):
    """Chrome lets the fetch through before the user answers its
    local-network prompt, then holds the response: the page may never see it."""
    make, events = served
    h = make()
    assert request(h)[0] == 200
    assert not events["delivered"].wait(0.2)
    assert request(h)[0] == 200


def test_receipt_reports_delivery_and_ends_the_handoff(served):
    make, events = served
    h = make()
    assert request(h)[0] == 200
    status, headers, _ = receipt(h)
    assert status == 204
    assert headers["Access-Control-Allow-Origin"] == SITE
    assert events["delivered"].wait(2)

    # The server shuts down right after, so a later fetch is refused or 404s.
    try:
        again = request(h)[0]
    except (urllib.error.URLError, ConnectionError):
        again = None
    assert again in (404, None)


def test_a_wrong_key_neither_serves_nor_confirms(served):
    make, events = served
    h = make()
    assert request(h, path="/pack/" + "0" * 32)[0] == 404
    assert receipt(h, key="0" * 32)[0] == 404
    assert not events["delivered"].is_set()
    assert request(h)[0] == 200


def test_other_websites_are_refused(served):
    make, events = served
    h = make()
    status, headers, _ = request(h, origin="https://example.com")
    assert status == 403
    assert "Access-Control-Allow-Origin" not in headers
    assert receipt(h, origin="https://example.com")[0] == 403
    assert not events["delivered"].is_set()
    assert request(h)[0] == 200


def test_local_copy_of_the_site_is_allowed():
    assert origin_allowed("http://localhost:8790")
    assert origin_allowed("http://127.0.0.1:8790")
    assert not origin_allowed("https://ankigammon.com.evil.example")
    assert not origin_allowed("http://localhost.evil.example")


def test_chrome_private_network_preflight_is_answered(served):
    make, events = served
    h = make()
    status, headers, _ = request(h, method="OPTIONS")
    assert status == 204
    assert headers["Access-Control-Allow-Private-Network"] == "true"
    assert headers["Access-Control-Allow-Origin"] == SITE
    assert "POST" in headers["Access-Control-Allow-Methods"]
    assert not events["delivered"].is_set()


def test_unconfirmed_pack_times_out_even_after_a_fetch(served):
    make, events = served
    h = make(timeout=0.3)
    assert request(h)[0] == 200
    assert events["timeout"].wait(3)
    assert not events["delivered"].is_set()


def test_confirmed_pack_never_reports_a_timeout(served):
    make, events = served
    h = make(timeout=0.3)
    assert receipt(h)[0] == 204
    assert not events["timeout"].wait(0.6)


def test_cancel_stops_serving_without_a_timeout(served):
    make, events = served
    h = make(timeout=0.3)
    h.close()
    assert not events["timeout"].wait(0.6)
