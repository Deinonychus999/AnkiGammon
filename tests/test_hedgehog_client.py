"""The HedgeHog client, connect flow and analyzer against a fake partner API."""

import json
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from ankigammon.models import DecisionType
from ankigammon.utils.hedgehog_analyzer import BATCH_SIZES, HedgehogAnalyzer
from ankigammon.utils.hedgehog_client import HedgehogClient, HedgehogRefusal, TokenStore
from ankigammon.utils.hedgehog_oauth import HedgehogConnect

DATA = Path(__file__).parent / "data" / "hedgehog"
CHECKER_RESULT = json.loads((DATA / "position_checker.json").read_text())["result"]
CHECKER_XGID = "XGID=--BCBBC--b--bB---bbcb-b-A-:0:0:-1:16:1:2:1:3:8"
CUBE_XGID = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:0:0:0:3:8"
MONEY_JACOBY_XGID = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:0:0:1:0:8"


class MemoryStore(TokenStore):
    def __init__(self, tokens=None):
        self.tokens = tokens

    def load(self):
        return dict(self.tokens) if self.tokens else None

    def save(self, tokens):
        self.tokens = dict(tokens)

    def clear(self):
        self.tokens = None


class FakeHedgehog:
    """Just enough of hedgehog-bg.com: tokens, me, revoke and position batches."""

    def __init__(self):
        self.access = "hho_1"
        self.refresh = "hhr_1"
        self.refresh_calls = 0
        self.revoked = []
        self.batches = []
        self.refusal = None
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def tokens(self):
        return {"access_token": self.access, "refresh_token": self.refresh, "expires_in": 900}

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _authorized(self):
                if self.headers.get("Authorization") != f"Bearer {fake.access}":
                    self._reply(401, {"error": "invalid_token", "message": "Your HedgeHog sign-in has expired."})
                    return False
                return True

            def do_GET(self):
                if not self._authorized():
                    return
                if self.path == "/api/v1/oauth/me":
                    self._reply(200, {"user_id": "u1", "username": "frank", "presets": {"position": ["1ply", "2ply"]}})
                elif self.path.startswith("/api/v1/analyze/position/"):
                    ogids, jacoby = fake.batches[int(self.path.rsplit("/", 1)[1])]
                    results = [dict(CHECKER_RESULT, ogid=ogid, jacoby_sent=jacoby) for ogid in ogids]
                    self._reply(200, {"status": "completed", "result": {"decision_type": "batch", "results": results}})
                else:
                    self._reply(404, {"error": "not_found", "message": "There is nothing at that address."})

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if self.path == "/api/v1/oauth/token":
                    form = dict(urllib.parse.parse_qsl(body.decode()))
                    with fake.lock:
                        if form["grant_type"] == "refresh_token":
                            fake.refresh_calls += 1
                            if form["refresh_token"] != fake.refresh:
                                self._reply(400, {"error": "invalid_grant", "error_description": "reused"})
                                return
                            fake.access = f"hho_{fake.refresh_calls + 1}"
                            fake.refresh = f"hhr_{fake.refresh_calls + 1}"
                        elif form.get("code") != "the-code":
                            self._reply(400, {"error": "invalid_grant", "error_description": "bad code"})
                            return
                        self._reply(200, fake.tokens())
                elif self.path == "/api/v1/oauth/revoke":
                    fake.revoked.append(dict(urllib.parse.parse_qsl(body.decode()))["token"])
                    self._reply(200, {})
                elif self.path == "/api/v1/analyze/positions":
                    if not self._authorized():
                        return
                    if fake.refusal:
                        self._reply(429, fake.refusal)
                        return
                    request = json.loads(body)
                    fake.batches.append((request["ogids"], request["jacoby"]))
                    self._reply(202, {"job_id": str(len(fake.batches) - 1), "status": "queued"})
                else:
                    self._reply(404, {"error": "not_found", "message": "There is nothing at that address."})

            def log_message(self, *args):
                pass

        return Handler


@pytest.fixture
def fake():
    server = FakeHedgehog()
    yield server
    server.close()


def _client(fake, tokens=None):
    return HedgehogClient(store=MemoryStore(tokens or fake.tokens()), base=fake.base, sleep=lambda s: None)


def test_an_expired_access_token_is_refreshed_once_and_the_call_repeated(fake):
    client = _client(fake)
    fake.access = "hho_rotated_elsewhere"  # the server no longer accepts the stored one
    fake.refresh = "hhr_1"
    assert client.me()["username"] == "frank"
    assert fake.refresh_calls == 1
    assert client.store.tokens["refresh_token"] == "hhr_2"


def test_concurrent_calls_refresh_only_once(fake):
    store = MemoryStore(fake.tokens())
    clients = [HedgehogClient(store=store, base=fake.base) for _ in range(6)]
    fake.access = "hho_stale"
    errors = []

    def call(client):
        try:
            client.me()
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)

    threads = [threading.Thread(target=call, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert fake.refresh_calls == 1


def test_a_revoked_connection_says_so_and_forgets_the_tokens(fake):
    client = _client(fake, {"access_token": "old", "refresh_token": "hhr_gone"})
    with pytest.raises(HedgehogRefusal) as refusal:
        client.me()
    assert refusal.value.code == "not_connected"
    assert client.store.tokens is None


def test_refusals_carry_hedgehogs_own_message(fake):
    fake.refusal = {"error": "allowance_exhausted", "message": "You've used today's free position analyses."}
    with pytest.raises(HedgehogRefusal) as refusal:
        _client(fake).analyze_positions(["x"], "2ply")
    assert refusal.value.code == "allowance_exhausted"
    assert str(refusal.value) == "You've used today's free position analyses."


def test_no_tokens_means_not_connected(fake):
    client = HedgehogClient(store=MemoryStore(None), base=fake.base)
    with pytest.raises(HedgehogRefusal) as refusal:
        client.me()
    assert refusal.value.code == "not_connected"


def test_disconnect_revokes_on_hedgehog_and_forgets_locally(fake):
    client = _client(fake)
    client.revoke()
    assert fake.revoked == ["hhr_1"]
    assert client.store.tokens is None


def _callback(url, **params):
    query = urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(f"{url}?{query}") as response:
            return response.status
    except urllib.error.HTTPError as err:
        return err.code


def test_connect_exchanges_the_code_and_reports_the_account(fake):
    done = threading.Event()
    seen = {}
    client = HedgehogClient(store=MemoryStore(None), base=fake.base)
    flow = HedgehogConnect(client, on_done=lambda me: (seen.update(me), done.set()))
    authorize = urllib.parse.urlsplit(flow.start())
    query = dict(urllib.parse.parse_qsl(authorize.query))
    assert query["code_challenge_method"] == "S256"
    assert query["redirect_uri"].startswith("http://127.0.0.1:")
    status = _callback(query["redirect_uri"], code="the-code", state=query["state"], iss=fake.base)
    assert status == 200
    assert done.wait(5)
    assert seen["username"] == "frank"
    assert client.store.tokens["refresh_token"] == "hhr_1"


@pytest.mark.parametrize("override", [{"state": "forged"}, {"iss": "https://evil.example"}])
def test_connect_ignores_replies_that_are_not_for_this_request(fake, override):
    client = HedgehogClient(store=MemoryStore(None), base=fake.base)
    flow = HedgehogConnect(client)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(flow.start()).query))
    params = dict(code="the-code", state=query["state"], iss=fake.base)
    params.update(override)
    try:
        assert _callback(query["redirect_uri"], **params) == 400
        assert client.store.tokens is None
    finally:
        flow.close()


def test_connect_reports_a_declined_approval(fake):
    failed = threading.Event()
    messages = []
    flow = HedgehogConnect(
        HedgehogClient(store=MemoryStore(None), base=fake.base),
        on_error=lambda message: (messages.append(message), failed.set()),
    )
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(flow.start()).query))
    _callback(query["redirect_uri"], error="access_denied", state=query["state"], iss=fake.base)
    assert failed.wait(5)
    assert "did not approve" in messages[0]


def test_connect_times_out():
    timed_out = threading.Event()
    flow = HedgehogConnect(HedgehogClient(store=MemoryStore(None)), on_timeout=timed_out.set, timeout=0.2)
    flow.start()
    assert timed_out.wait(5)


def test_positions_go_in_batches_small_enough_to_count_once(fake):
    analyzer = HedgehogAnalyzer(preset="2ply", client=_client(fake))
    xgids = [CHECKER_XGID] * 30
    progress = []
    results = analyzer.analyze_positions_parallel(xgids, progress_callback=lambda d, n: progress.append(d))
    assert [len(ogids) for ogids, _ in fake.batches] == [12, 12, 6]
    assert progress == [12, 24, 30]
    assert len(results) == 30 and all(t == DecisionType.CHECKER_PLAY for _, t in results)
    assert BATCH_SIZES["1ply"] == 64


def test_jacoby_positions_go_in_their_own_batch_and_results_keep_their_order(fake):
    analyzer = HedgehogAnalyzer(preset="2ply", client=_client(fake))
    xgids = [CUBE_XGID, MONEY_JACOBY_XGID, CHECKER_XGID]
    results = analyzer.analyze_positions_parallel(xgids)
    assert sorted(jacoby for _, jacoby in fake.batches) == [False, True]
    sent = [json.loads(raw)["ogid"] for raw, _ in results]
    assert sent[1].split(":")[8] == "0"          # the money position came back in its slot
    assert [t for _, t in results] == [DecisionType.CUBE_ACTION, DecisionType.CUBE_ACTION, DecisionType.CHECKER_PLAY]


def test_cancelling_stops_before_the_next_batch(fake):
    analyzer = HedgehogAnalyzer(preset="2ply", client=_client(fake))
    with pytest.raises(InterruptedError):
        analyzer.analyze_positions_parallel([CHECKER_XGID] * 30, cancellation_callback=lambda: True)
    assert fake.batches == []
