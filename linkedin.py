"""Posting to LinkedIn with the official API ("Share on LinkedIn" + "Sign In with LinkedIn using OpenID Connect").

One-time setup (about 10 minutes):
  1. https://www.linkedin.com/developers/apps -> Create app (any company page, e.g. AquaRE).
  2. Products tab: add "Share on LinkedIn" and "Sign In with LinkedIn using OpenID Connect".
  3. Auth tab: add redirect URL  http://localhost:8000/auth/linkedin/callback
  4. Copy Client ID / Client Secret into LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET.
Then click "Connect LinkedIn" in the app. The token lasts about 60 days.

Without a connected account the app runs in test mode: nothing leaves your machine,
posts are written to outbox.log instead.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
import time
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN_FILE = Path(__file__).parent / "linkedin_token.json"
OUTBOX = Path(__file__).parent / "outbox.log"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
SCOPES = "openid profile w_member_social"
_pending_states: set[str] = set()


def _cfg(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def redirect_uri() -> str:
    return _cfg("LINKEDIN_REDIRECT_URI", "http://localhost:8000/auth/linkedin/callback")


def configured() -> bool:
    return bool(_cfg("LINKEDIN_CLIENT_ID") and _cfg("LINKEDIN_CLIENT_SECRET"))


def _token() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    t = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    return t if t.get("expires_at", 0) > time.time() + 60 else None


def status() -> dict:
    t = _token()
    if t:
        return {"connected": True, "name": t.get("name", ""), "expires_at": t["expires_at"], "test_mode": False}
    return {"connected": False, "configured": configured(), "test_mode": True}


def login_url() -> str:
    state = secrets.token_urlsafe(16)
    _pending_states.add(state)
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": _cfg("LINKEDIN_CLIENT_ID"),
        "redirect_uri": redirect_uri(), "state": state, "scope": SCOPES})


def _http(url: str, data: bytes | None = None, headers: dict | None = None, method: str | None = None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def finish_login(code: str, state: str) -> dict:
    if state not in _pending_states:
        raise ValueError("Login expired or was not started here. Try Connect LinkedIn again.")
    _pending_states.discard(state)
    code_, _, body = _http(TOKEN_URL, urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
        "client_id": _cfg("LINKEDIN_CLIENT_ID"), "client_secret": _cfg("LINKEDIN_CLIENT_SECRET")}).encode(),
        {"Content-Type": "application/x-www-form-urlencoded"})
    if code_ != 200:
        raise RuntimeError(f"LinkedIn token exchange failed ({code_}): {body[:300]!r}")
    tok = json.loads(body)
    c, _, ub = _http("https://api.linkedin.com/v2/userinfo",
                     headers={"Authorization": f"Bearer {tok['access_token']}"})
    if c != 200:
        raise RuntimeError(f"Could not read your LinkedIn profile ({c}).")
    me = json.loads(ub)
    saved = {"access_token": tok["access_token"], "expires_at": time.time() + int(tok.get("expires_in", 0)),
             "person_urn": f"urn:li:person:{me['sub']}", "name": me.get("name", "")}
    TOKEN_FILE.write_text(json.dumps(saved), encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    return saved


def disconnect():
    TOKEN_FILE.unlink(missing_ok=True)


def _api_version() -> str:
    # LinkedIn's versioned API wants a recent YYYYMM; use two months back unless overridden.
    if _cfg("LINKEDIN_VERSION"):
        return _cfg("LINKEDIN_VERSION")
    d = dt.date.today().replace(day=1)
    m = d.month - 2
    y = d.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y}{m:02d}"


def escape_commentary(text: str) -> str:
    """LinkedIn's 'little text' format treats these as markup; unescaped they cut the post short."""
    return re.sub(r"([\\|{}@\[\]()<>#*_~])", r"\\\1", text)


def publish(text: str, link: str = "", link_title: str = "") -> dict:
    """Publish now. Returns {'ok', 'post_urn' | 'error', 'test_mode'}."""
    t = _token()
    if not t:
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write(f"--- TEST MODE {dt.datetime.now().isoformat(timespec='seconds')} ---\n{text}\n\n")
        return {"ok": True, "test_mode": True, "post_urn": None}
    body = {
        "author": t["person_urn"],
        "commentary": escape_commentary(text),
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if link:
        body["content"] = {"article": {"source": link, "title": link_title or link}}
    code, headers, resp = _http("https://api.linkedin.com/rest/posts", json.dumps(body).encode(), {
        "Authorization": f"Bearer {t['access_token']}", "Content-Type": "application/json",
        "LinkedIn-Version": _api_version(), "X-Restli-Protocol-Version": "2.0.0"}, "POST")
    if code == 201:
        urn = {k.lower(): v for k, v in headers.items()}.get("x-restli-id")
        return {"ok": True, "test_mode": False, "post_urn": urn}
    return {"ok": False, "test_mode": False, "error": f"LinkedIn said {code}: {resp[:300].decode(errors='replace')}"}
