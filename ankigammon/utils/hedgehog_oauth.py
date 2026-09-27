"""Connect a HedgeHog account: OAuth authorization code with PKCE over a
loopback redirect (RFC 8252). HedgeHog accepts any port on
http://127.0.0.1/callback, as registered in ankigammon.com/oauth/client.json.
"""

import base64
import hashlib
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

from ankigammon.utils.hedgehog_client import CLIENT_ID, SCOPE, HedgehogClient, HedgehogRefusal

TIMEOUT_SECONDS = 300

_PAGE = """<!doctype html><meta charset="utf-8"><title>AnkiGammon</title>
<body style="font-family:system-ui,sans-serif;background:#1e1e2e;color:#cdd6f4;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center"><h2>{title}</h2><p>{body}</p></div></body>"""


def _pkce_pair():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class HedgehogConnect:
    """Waits for one authorization callback, then exchanges the code and
    stores the tokens. Exactly one of on_done(me), on_error(message) or
    on_timeout() fires, unless it is closed first."""

    def __init__(self, client: Optional[HedgehogClient] = None,
                 on_done: Optional[Callable[[dict], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None,
                 on_timeout: Optional[Callable[[], None]] = None,
                 timeout: float = TIMEOUT_SECONDS) -> None:
        self.client = client or HedgehogClient()
        self._on_done = on_done
        self._on_error = on_error
        self._on_timeout = on_timeout
        self._timeout = timeout
        self._state = secrets.token_urlsafe(24)
        self._verifier, self._challenge = _pkce_pair()
        self._lock = threading.Lock()
        self._done = False
        self._server: Optional[ThreadingHTTPServer] = None
        self._port = 0
        self._timer: Optional[threading.Timer] = None

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self._port}/callback"

    def authorize_url(self) -> str:
        return self.client.base + "/oauth/authorize?" + urllib.parse.urlencode({
            "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": self.redirect_uri,
            "scope": SCOPE, "state": self._state,
            "code_challenge": self._challenge, "code_challenge_method": "S256",
        })

    def start(self) -> str:
        """Start listening; returns the URL to open in the system browser."""
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._server.daemon_threads = True
        self._port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self._timer = threading.Timer(self._timeout, self._finish, args=(self._on_timeout,))
        self._timer.daemon = True
        self._timer.start()
        return self.authorize_url()

    def close(self) -> None:
        """Stop listening. Safe to call more than once, from any thread."""
        with self._lock:
            self._done = True
        if self._timer is not None:
            self._timer.cancel()
        server, self._server = self._server, None
        if server is not None:
            threading.Thread(target=self._shutdown, args=(server,), daemon=True).start()

    @staticmethod
    def _shutdown(server: ThreadingHTTPServer) -> None:
        server.shutdown()
        server.server_close()

    def _claim(self) -> bool:
        with self._lock:
            if self._done:
                return False
            self._done = True
            return True

    def _finish(self, callback, *args) -> None:
        if not self._claim():
            return
        self.close()
        if callback:
            callback(*args)

    def _complete(self, params: dict) -> None:
        """Runs off the request thread: the browser already has its page."""
        self.close()
        try:
            self.client.exchange_code(params["code"], self.redirect_uri, self._verifier)
            me = self.client.me()
        except HedgehogRefusal as refusal:
            if self._on_error:
                self._on_error(refusal.message)
            return
        if self._on_done:
            self._on_done(me)

    def _handle(self, query: str):
        """Returns (http status, page title, page body)."""
        params = dict(urllib.parse.parse_qsl(query))
        if params.get("state") != self._state or params.get("iss") != self.client.base:
            return 400, "Not recognised", "This reply was not for AnkiGammon's request. Try connecting again."
        if not self._claim():
            return 409, "Already handled", "You can close this tab."
        if "error" in params:
            message = (
                "You did not approve AnkiGammon on HedgeHog."
                if params["error"] == "access_denied"
                else params.get("error_description") or f"HedgeHog refused: {params['error']}."
            )
            self.close()
            if self._on_error:
                threading.Thread(target=self._on_error, args=(message,), daemon=True).start()
            return 200, "Not connected", message
        threading.Thread(target=self._complete, args=(params,), daemon=True).start()
        return 200, "Connected to HedgeHog", "You can close this tab and return to AnkiGammon."

    def _handler_class(self):
        connect = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parts = urllib.parse.urlsplit(self.path)
                if parts.path != "/callback":
                    self.send_error(404)
                    return
                status, title, body = connect._handle(parts.query)
                page = _PAGE.format(title=title, body=body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)

            def log_message(self, *args):
                pass

        return Handler
