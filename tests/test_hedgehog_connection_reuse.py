"""HedgeHog requests share one connection.

A new TLS handshake per status check (two a second) made every analysis
depend on dozens of handshakes; on a route that stalls some of them
(reported from Russia) one stall ended the run.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ankigammon.utils.hedgehog_client import HedgehogClient, TokenStore


class Store(TokenStore):
    def load(self):
        return {"access_token": "a", "refresh_token": "r"}

    def save(self, tokens):
        pass

    def clear(self):
        pass


@pytest.fixture
def server():
    connections = set()
    polls = {"left": 4}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _reply(self, payload):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            connections.add(self.client_address)
            if self.path.startswith("/api/v1/analyze/position/"):
                polls["left"] -= 1
                if polls["left"] > 0:
                    self._reply({"status": "running"})
                else:
                    self._reply({"status": "completed", "result": {"results": []}})
            else:
                self._reply({"username": "PlayerOne"})

        def do_POST(self):
            connections.add(self.client_address)
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self._reply({"job_id": "job"})

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", connections
    httpd.shutdown()
    httpd.server_close()


def test_requests_reuse_one_connection(server):
    base, connections = server
    client = HedgehogClient(store=Store(), base=base, sleep=lambda s: None)

    for _ in range(5):
        client.request("GET", "/api/v1/oauth/me")

    assert len(connections) == 1


def test_a_whole_job_polls_over_the_same_connection(server):
    base, connections = server
    pauses = []
    client = HedgehogClient(store=Store(), base=base, sleep=pauses.append)

    client.analyze_positions(["ogid"], "2ply")

    assert pauses == [0.5, 0.5, 0.5]
    assert len(connections) == 1
