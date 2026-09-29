"""A network hiccup during an analysis retries the status check, not the run.

Reported from Fedora: one TLS handshake that timed out during a HedgeHog
analysis ended the whole run. Status checks (GET) are safe to repeat; a new
job (POST) or a token refresh is not, since repeating it could start a second
job or reuse a rotated refresh token.
"""

import pytest

from ankigammon.utils.hedgehog_client import HedgehogClient, HedgehogRefusal, TokenStore

TOKENS = {"access_token": "a", "refresh_token": "r"}


class Store(TokenStore):
    def load(self):
        return dict(TOKENS)

    def save(self, tokens):
        pass

    def clear(self):
        pass


def _client(failures: int):
    pauses = []
    client = HedgehogClient(store=Store(), sleep=pauses.append)
    calls = []

    def send(method, path, headers, data):
        calls.append(method)
        if len(calls) <= failures:
            raise HedgehogRefusal("unreachable", "Could not reach HedgeHog (The handshake operation timed out).")
        return 200, {}, b'{"status": "running"}'

    client._send = send
    return client, calls, pauses


def test_a_status_check_survives_a_timed_out_handshake():
    client, calls, pauses = _client(failures=2)

    assert client.request("GET", "/api/v1/analyze/position/job") == {"status": "running"}
    assert calls == ["GET", "GET", "GET"]
    assert len(pauses) == 2


def test_a_status_check_gives_up_after_three_tries():
    client, calls, _ = _client(failures=3)

    with pytest.raises(HedgehogRefusal, match="handshake"):
        client.request("GET", "/api/v1/analyze/position/job")
    assert calls == ["GET", "GET", "GET"]


def test_a_new_job_is_never_sent_twice():
    client, calls, _ = _client(failures=1)

    with pytest.raises(HedgehogRefusal, match="handshake"):
        client.request("POST", "/api/v1/analyze/positions", json_body={"ogids": []})
    assert calls == ["POST"]
