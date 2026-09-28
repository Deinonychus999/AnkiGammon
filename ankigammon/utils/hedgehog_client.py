"""HedgeHog partner API: tokens and the calls AnkiGammon makes.

HedgeHog (hedgehog-bg.com) analyses on its own servers, on behalf of a user who
connected their account over OAuth. The contract is docs/PARTNER_API.md in
gitlab.com/eranlambooij/hedgehog-public. Standard library only, and Qt-free.
"""

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

BASE = os.environ.get("ANKIGAMMON_HEDGEHOG_URL", "https://hedgehog-bg.com").rstrip("/")
CLIENT_ID = "https://ankigammon.com/oauth/client.json"
SCOPE = "analyze"

KEYRING_SERVICE = "AnkiGammon HedgeHog"
KEYRING_USER = "tokens"

# Two refreshes of the same refresh token revoke the whole connection, so every
# client in the process refreshes under this one lock.
_refresh_lock = threading.Lock()


class HedgehogRefusal(Exception):
    """HedgeHog declined a request. `message` is written for the user, and the
    Developer Terms require showing it as returned."""

    def __init__(self, code: str, message: str, status: int = 0, body: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.body = body or {}

    def __str__(self) -> str:
        return self.message


def not_connected() -> HedgehogRefusal:
    return HedgehogRefusal(
        "not_connected",
        "AnkiGammon is not connected to HedgeHog. Connect your account in Settings.",
    )


class TokenStore:
    """Keeps the token pair in the OS keychain, or in a private file where no
    keychain is available. Never in config.json, which diagnostics collect."""

    def __init__(self, fallback_path: Optional[Path] = None):
        self._fallback = fallback_path or Path.home() / ".ankigammon" / "hedgehog_tokens.json"

    @staticmethod
    def _keyring():
        try:
            import keyring
            from keyring.backends import fail
        except ImportError:
            return None
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring

    def load(self) -> Optional[dict]:
        keyring = self._keyring()
        raw = None
        if keyring is not None:
            try:
                raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
            except Exception:
                raw = None
        if raw is None and self._fallback.exists():
            try:
                raw = self._fallback.read_text(encoding="utf-8")
            except OSError:
                raw = None
        if not raw:
            return None
        try:
            tokens = json.loads(raw)
        except ValueError:
            return None
        return tokens if isinstance(tokens, dict) and tokens.get("refresh_token") else None

    def save(self, tokens: dict) -> None:
        raw = json.dumps(tokens)
        keyring = self._keyring()
        if keyring is not None:
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_USER, raw)
                self._remove_fallback()
                return
            except Exception:
                pass
        self._fallback.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self._fallback), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)

    def clear(self) -> None:
        keyring = self._keyring()
        if keyring is not None:
            try:
                keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
            except Exception:
                pass
        self._remove_fallback()

    def _remove_fallback(self) -> None:
        try:
            self._fallback.unlink()
        except OSError:
            pass


def ssl_context() -> ssl.SSLContext:
    """The system's trusted certificates, or certifi's when OpenSSL finds none:
    the Linux AppImage's OpenSSL looks where Ubuntu keeps them (/usr/lib/ssl),
    which Fedora and others don't have."""
    context = ssl.create_default_context()
    if not context.get_ca_certs():
        import certifi
        context.load_verify_locations(certifi.where())
    return context


_shared_context: Optional[ssl.SSLContext] = None


def _context() -> ssl.SSLContext:
    global _shared_context
    if _shared_context is None:
        _shared_context = ssl_context()
    return _shared_context


class HedgehogClient:
    """One connected user's view of the partner API."""

    def __init__(self, store: Optional[TokenStore] = None, base: str = BASE,
                 sleep: Callable[[float], None] = time.sleep):
        self.store = store or TokenStore()
        self.base = base
        self._sleep = sleep

    # --- HTTP ---------------------------------------------------------------

    def _send(self, method: str, path: str, headers: Dict[str, str],
              data: Optional[bytes]) -> Tuple[int, Dict[str, str], bytes]:
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60, context=_context()) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as err:
            return err.code, dict(err.headers or {}), err.read()
        except (urllib.error.URLError, OSError) as err:
            raise HedgehogRefusal(
                "unreachable", f"Could not reach HedgeHog ({getattr(err, 'reason', err)}). "
                "Check your internet connection and try again.",
            ) from err

    def request(self, method: str, path: str, *, json_body=None, raw: Optional[bytes] = None,
                form: Optional[dict] = None, auth: bool = True, retry: bool = True,
                expect_binary: bool = False):
        """Send one API request and return the decoded JSON (or bytes)."""
        headers: Dict[str, str] = {"Accept": "application/json"}
        data = None
        tokens = None
        if auth:
            tokens = self.store.load()
            if not tokens:
                raise not_connected()
            headers["Authorization"] = "Bearer " + tokens.get("access_token", "")
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urllib.parse.urlencode(form).encode()
        elif json_body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(json_body).encode()
        elif raw is not None:
            headers["Content-Type"] = "application/octet-stream"
            data = raw
        status, _, body = self._send(method, path, headers, data)
        if expect_binary and status < 400:
            return status, body
        try:
            answer = json.loads(body or b"{}")
        except ValueError:
            answer = {}
        if status == 401 and answer.get("error") == "invalid_token" and auth and retry:
            self._refresh(tokens.get("access_token"))
            return self.request(method, path, json_body=json_body, raw=raw, form=form,
                                retry=False, expect_binary=expect_binary)
        if status >= 500:
            raise HedgehogRefusal(
                "server_error",
                f"HedgeHog had a problem on its side (HTTP {status}). Try again later, "
                "and tell HedgeHog if it keeps happening with this file.",
                status, answer,
            )
        if status >= 400:
            message = (answer.get("message") or answer.get("error_description")
                       or f"HedgeHog answered HTTP {status}.")
            if answer.get("error") == "invalid_match" and answer.get("detail"):
                message = f"{message} {answer['detail']}"
            raise HedgehogRefusal(answer.get("error") or f"http_{status}", message, status, answer)
        return (status, answer) if expect_binary else answer

    # --- Tokens -------------------------------------------------------------

    def exchange_code(self, code: str, redirect_uri: str, verifier: str) -> dict:
        tokens = self.request("POST", "/api/v1/oauth/token", auth=False, form={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            "client_id": CLIENT_ID, "code_verifier": verifier,
        })
        self.store.save(tokens)
        return tokens

    def _refresh(self, stale_access_token: Optional[str]) -> None:
        with _refresh_lock:
            current = self.store.load()
            if not current:
                raise not_connected()
            if current.get("access_token") != stale_access_token:
                return  # another thread already rotated the pair
            try:
                tokens = self.request("POST", "/api/v1/oauth/token", auth=False, form={
                    "grant_type": "refresh_token", "refresh_token": current["refresh_token"],
                    "client_id": CLIENT_ID,
                })
            except HedgehogRefusal as refusal:
                if refusal.code == "invalid_grant":
                    self.store.clear()
                    raise HedgehogRefusal(
                        "not_connected",
                        "Your HedgeHog connection has ended. Connect your account again in Settings.",
                    ) from refusal
                raise
            self.store.save(tokens)

    def revoke(self) -> None:
        """End the connection on HedgeHog and forget the tokens here."""
        tokens = self.store.load()
        self.store.clear()
        if tokens:
            try:
                self.request("POST", "/api/v1/oauth/revoke", auth=False, form={
                    "token": tokens["refresh_token"], "client_id": CLIENT_ID,
                    "token_type_hint": "refresh_token",
                })
            except HedgehogRefusal:
                pass

    # --- API ----------------------------------------------------------------

    def me(self) -> dict:
        return self.request("GET", "/api/v1/oauth/me")

    def import_match(self, path: str) -> dict:
        """Convert a match file to OGXM JSON on HedgeHog; nothing is stored."""
        data = Path(path).read_bytes()
        kind = Path(path).suffix.lower().lstrip(".")
        if kind not in ("mat", "xg", "bgf", "sgf"):
            # JellyFish text often comes as .txt or with no extension at all
            kind = "xg" if data[:4] == b"RGMH" else "sgf" if data.lstrip()[:2] == b"(;" else "mat"
        return self.request("POST", f"/api/v1/matches/import/{kind}", raw=data)

    def save_match(self, match: dict) -> dict:
        return self.request("POST", "/api/v1/matches/save", json_body=match)

    def analyze_match(self, match_id: str, preset: str) -> dict:
        try:
            return self.request("POST", "/api/v1/analyze",
                                json_body={"match_id": match_id, "preset": preset, "notify": False})
        except HedgehogRefusal as refusal:
            if refusal.code == "already_analysing" and refusal.body.get("analysis_id"):
                return refusal.body
            raise

    def wait_analysis(self, analysis_id: str, cancelled: Callable[[], bool] = lambda: False,
                      interval: float = 5.0) -> dict:
        while True:
            analysis = self.request("GET", f"/api/v1/analysis/{analysis_id}")
            status = analysis.get("status")
            if status == "completed":
                return analysis
            if status in ("failed", "cancelled"):
                error = analysis.get("error") or {}
                raise HedgehogRefusal(
                    error.get("error", status),
                    error.get("message") or f"The HedgeHog analysis was {status}.",
                    body=error,
                )
            if cancelled():
                raise InterruptedError("Analysis cancelled by user")
            self._sleep(interval)

    def analysis_file(self, analysis_id: str) -> bytes:
        _, body = self.request("GET", f"/api/v1/analysis/{analysis_id}/ogxm", expect_binary=True)
        return body

    def analyze_positions(self, ogids: List[str], preset: str, jacoby: bool = False,
                          cancelled: Callable[[], bool] = lambda: False,
                          interval: float = 0.5) -> List[dict]:
        """Analyse OGIDs as one batch job; one result or failure per OGID, in order."""
        job = self.request("POST", "/api/v1/analyze/positions",
                           json_body={"ogids": ogids, "preset": preset, "jacoby": jacoby})
        while True:
            answer = self.request("GET", f"/api/v1/analyze/position/{job['job_id']}")
            status = answer.get("status")
            if status == "completed":
                return answer["result"]["results"]
            if status == "failed":
                error = answer.get("error") or {}
                raise HedgehogRefusal(
                    error.get("error", "analysis_failed"),
                    error.get("message") or "HedgeHog could not analyze these positions.",
                    body=error,
                )
            if cancelled():
                raise InterruptedError("Analysis cancelled by user")
            self._sleep(interval)
