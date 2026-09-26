"""Hand a study pack to the browser trainer running on this computer.

The desktop app serves the pack once from 127.0.0.1 behind a random key and
opens ankigammon.com/train/#desktop=<port>.<key>; the trainer fetches
/pack/<key> and imports it. The key travels in the URL fragment, which the
browser never sends to the website. Browsers that refuse to reach loopback
from an https page (Safari) never fetch, so the caller offers the file
export when `on_timeout` fires.
"""

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import urlsplit

TRAINER_URL = os.environ.get("ANKIGAMMON_TRAINER_URL", "https://ankigammon.com/train/")
TIMEOUT_SECONDS = 120


def origin_allowed(origin: str) -> bool:
    """The live site, or a local copy of it for development."""
    if origin == "https://ankigammon.com":
        return True
    parts = urlsplit(origin)
    return parts.scheme in ("http", "https") and parts.hostname in ("localhost", "127.0.0.1")


class PackHandoff:
    """Serves one pack, once, until it is fetched, closed, or times out."""

    def __init__(self, pack: dict, on_fetched: Optional[Callable[[], None]] = None,
                 on_timeout: Optional[Callable[[], None]] = None,
                 timeout: float = TIMEOUT_SECONDS) -> None:
        self.key = secrets.token_hex(16)
        self._body = json.dumps(pack, separators=(",", ":")).encode("utf-8")
        self._on_fetched = on_fetched
        self._on_timeout = on_timeout
        self._timeout = timeout
        self._lock = threading.Lock()
        self._done = False
        self._server: Optional[ThreadingHTTPServer] = None
        self._port = 0
        self._timer: Optional[threading.Timer] = None

    @property
    def port(self) -> int:
        return self._port

    def url(self, base: str = TRAINER_URL) -> str:
        return f"{base}#desktop={self.port}.{self.key}"

    def start(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._server.daemon_threads = True
        self._port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self._timer = threading.Timer(self._timeout, self._expire)
        self._timer.daemon = True
        self._timer.start()

    def close(self) -> None:
        """Stop serving. Safe to call more than once, from any thread."""
        with self._lock:
            self._done = True
        if self._timer is not None:
            self._timer.cancel()
        server, self._server = self._server, None
        if server is not None:
            # shutdown() waits for serve_forever, which may be answering on
            # this very thread; a helper thread keeps that from deadlocking.
            threading.Thread(target=self._shutdown, args=(server,), daemon=True).start()

    @staticmethod
    def _shutdown(server: ThreadingHTTPServer) -> None:
        server.shutdown()
        server.server_close()

    def _expire(self) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
        self.close()
        if self._on_timeout:
            self._on_timeout()

    def _claim(self) -> bool:
        with self._lock:
            if self._done:
                return False
            self._done = True
            return True

    def _release(self) -> None:
        with self._lock:
            self._done = False

    def _handler_class(self):
        handoff = self

        class Handler(BaseHTTPRequestHandler):
            def _cors(self) -> bool:
                origin = self.headers.get("Origin")
                if origin is None:
                    return True
                if not origin_allowed(origin):
                    return False
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                return True

            def do_OPTIONS(self) -> None:
                origin = self.headers.get("Origin")
                if origin is None or not origin_allowed(origin):
                    self.send_response(403)
                    self.end_headers()
                    return
                self.send_response(204)
                self._cors()
                self.send_header("Access-Control-Allow-Methods", "GET")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Access-Control-Max-Age", "60")
                self.end_headers()

            def do_GET(self) -> None:
                origin = self.headers.get("Origin")
                if origin is not None and not origin_allowed(origin):
                    self.send_response(403)
                    self.end_headers()
                    return
                if self.path != f"/pack/{handoff.key}" or not handoff._claim():
                    self.send_response(404)
                    self._cors()
                    self.end_headers()
                    return
                try:
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(handoff._body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(handoff._body)
                    self.wfile.flush()
                except OSError:
                    # The tab went away mid-transfer. Released, the pack
                    # still times out and the caller offers the file instead.
                    handoff._release()
                    return
                handoff.close()
                if handoff._on_fetched:
                    handoff._on_fetched()

            def log_message(self, format: str, *args) -> None:
                pass

        return Handler
