"""One-click OAuth: per-flow loopback listener, PKCE, status/cancel/expiry, persistence. The provider is a local fake token endpoint;
the listener, the state handling, the exchange and the connection store are the real ones."""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from aether.connections import oauth, oauth_flow
from aether.connections.oauth import OAUTH_SPECS, OAuthManager
from aether.connections.oauth_flow import FlowRegistry
from aether.workspace.workspace import Workspace

_REAL: dict = {}


@pytest.fixture(autouse=True)
def _no_bundled_client_ids(monkeypatch):
    """These tests describe an install with no shipped client ids; the real ones must not leak in."""
    import aether.connections.oauth as _oauth

    _REAL["fn"] = _oauth._bundled_clients
    monkeypatch.setattr(_oauth, "_bundled_clients", lambda: {})



class FakeProvider(http.server.BaseHTTPRequestHandler):
    seen: list[dict] = []

    def log_message(self, *a):
        return

    def do_POST(self):  # noqa: N802
        body = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        FakeProvider.seen.append({k: v[0] for k, v in body.items()})
        ok = body.get("code") == ["good-code"]
        data = json.dumps({"access_token": "at-123", "refresh_token": "rt-456", "expires_in": 3600, "token_type": "bearer"} if ok else {"error": "invalid_grant", "error_description": "bad code"}).encode()
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def provider(tmp_path: Path, monkeypatch):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    FakeProvider.seen = []
    monkeypatch.setitem(OAUTH_SPECS, "fakeprov", {
        "name": "Fake", "auth_url": "https://fake.example/authorize", "token_url": f"http://127.0.0.1:{srv.server_address[1]}/token",
        "scopes": ["read"], "default_client_id": None, "env_client_id": ["FAKE_CLIENT_ID"], "env_client_secret": [],
        "setup_url": "", "uses_pkce": True, "requires_secret": False, "exchange": "standard",
    })
    monkeypatch.setenv("FAKE_CLIENT_ID", "client-xyz")
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    ws = Workspace.init(tmp_path / "ws", name="Flow")
    yield ws
    srv.shutdown()
    ws.close()


def _browser(redirect_uri: str, **query) -> tuple[int, str]:
    url = redirect_uri + "?" + urllib.parse.urlencode(query)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _wait(state: str, want: str, t: float = 5.0) -> dict:
    end = time.time() + t
    while time.time() < end:
        st = FlowRegistry.status(state)
        if st and st["status"] == want:
            return st
        time.sleep(0.05)
    return FlowRegistry.status(state) or {}


def _closed(redirect_uri: str) -> bool:
    try:
        urllib.request.urlopen(redirect_uri, timeout=2)
        return False
    except urllib.error.HTTPError:
        return False
    except Exception:  # noqa: BLE001 - connection refused = the listener is gone
        return True


def test_a_full_flow_uses_pkce_a_loopback_redirect_and_stores_the_tokens(provider):
    ws = provider
    flow = FlowRegistry.start(ws, "fakeprov", ws.id)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(flow["auth_url"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == ["client-xyz"] and q["state"] == [flow["state"]]
    assert flow["redirect_uri"].startswith("http://127.0.0.1:") and flow["redirect_uri"].endswith("/callback") and ":8000" not in flow["redirect_uri"]
    assert FlowRegistry.status(flow["state"])["status"] == "pending"
    status, page = _browser(flow["redirect_uri"], code="good-code", state=flow["state"])
    assert status == 200 and "Connected" in page and "good-code" not in page
    st = _wait(flow["state"], "success")
    assert st["status"] == "success" and st["error"] == ""
    sent = FakeProvider.seen[-1]
    assert sent["grant_type"] == "authorization_code" and sent["redirect_uri"] == flow["redirect_uri"]
    digest = base64.urlsafe_b64encode(hashlib.sha256(sent["code_verifier"].encode()).digest()).decode().rstrip("=")
    assert digest == q["code_challenge"][0], "the verifier sent to the provider matches the challenge in the authorization URL"
    conn = ws.connections.get_connection(ws.id, "fakeprov")
    assert conn and conn.status.value == "verified" and conn.auth_metadata.get("access_token") and conn.auth_metadata.get("refresh_token")
    assert _closed(flow["redirect_uri"]), "the listener is gone as soon as the flow ends"
    assert OAuthManager.validate_and_consume_state(flow["state"]) is None, "state is single-use"


def test_denial_wrong_state_and_a_bad_code_are_reported_not_swallowed(provider):
    ws = provider
    denied = FlowRegistry.start(ws, "fakeprov", ws.id)
    status, page = _browser(denied["redirect_uri"], error="access_denied", state=denied["state"])
    assert status == 200 and "cancelled" in page.lower()
    st = _wait(denied["state"], "error")
    assert st["status"] == "error" and st["error"].startswith("denied:")
    assert ws.connections.get_connection(ws.id, "fakeprov") is None

    wrong = FlowRegistry.start(ws, "fakeprov", ws.id)
    status, _ = _browser(wrong["redirect_uri"], code="good-code", state="not-my-state")
    assert status == 400 and FlowRegistry.status(wrong["state"])["status"] == "pending", "a stranger's request cannot end or poison the flow"
    FlowRegistry.cancel(wrong["state"])

    bad = FlowRegistry.start(ws, "fakeprov", ws.id)
    _browser(bad["redirect_uri"], code="nope", state=bad["state"])
    st = _wait(bad["state"], "error")
    assert st["status"] == "error" and st["error"].startswith("exchange_failed:") and "bad code" in st["error"]


def test_cancel_and_expiry_close_the_listener(provider, monkeypatch):
    ws = provider
    f = FlowRegistry.start(ws, "fakeprov", ws.id)
    assert FlowRegistry.cancel(f["state"]) is True
    assert FlowRegistry.status(f["state"])["status"] == "cancelled"
    time.sleep(0.3)
    assert _closed(f["redirect_uri"])
    assert FlowRegistry.cancel("unknown") is False
    monkeypatch.setattr(oauth_flow, "FLOW_TTL_SECONDS", 0)
    g = FlowRegistry.start(ws, "fakeprov", ws.id)
    time.sleep(0.05)
    assert FlowRegistry.status(g["state"])["status"] == "expired"
    assert FlowRegistry.status("never-existed") is None


def test_unknown_provider_and_missing_client_id_fail_clearly(provider, monkeypatch):
    ws = provider
    with pytest.raises(ValueError):
        FlowRegistry.start(ws, "nope", ws.id)
    monkeypatch.delenv("FAKE_CLIENT_ID")
    with pytest.raises(ValueError, match="Client ID"):
        FlowRegistry.start(ws, "fakeprov", ws.id)


def test_bundled_client_ids_make_a_provider_one_click_ready(provider, monkeypatch):
    ws = provider
    before = OAuthManager.get_provider_status("google_calendar", ws.id, store=ws.connections.store)
    assert before["ready_for_user_connect"] is False
    monkeypatch.setattr(oauth, "_bundled_clients", lambda: {"google_calendar": {"client_id": "bundled-id.apps.googleusercontent.com", "client_secret": "x"}})
    after = OAuthManager.get_provider_status("google_calendar", ws.id, store=ws.connections.store)
    assert after["ready_for_user_connect"] is True
    flow = FlowRegistry.start(ws, "google_calendar", ws.id)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(flow["auth_url"]).query)
    assert q["client_id"] == ["bundled-id.apps.googleusercontent.com"] and q["code_challenge_method"] == ["S256"] and q["redirect_uri"][0].startswith("http://127.0.0.1:")
    FlowRegistry.cancel(flow["state"])


class FakeGitHub(http.server.BaseHTTPRequestHandler):
    polls = 0
    mode = "ok"

    def log_message(self, *a):
        return

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        body = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        if self.path == "/device/code":
            self._json({"device_code": "dc-1", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device", "expires_in": 60, "interval": 0})
        elif self.path == "/token":
            assert body["grant_type"] == ["urn:ietf:params:oauth:grant-type:device_code"] and body["device_code"] == ["dc-1"]
            FakeGitHub.polls += 1
            if FakeGitHub.mode == "denied":
                self._json({"error": "access_denied", "error_description": "The user said no"})
            elif FakeGitHub.polls < 3:
                self._json({"error": "authorization_pending"})
            else:
                self._json({"access_token": "gho_fake", "token_type": "bearer", "scope": "repo,read:user"})

    def do_GET(self):  # noqa: N802
        self._json({"login": "matteo-test", "email": ""})


@pytest.fixture
def github(tmp_path: Path, monkeypatch):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    FakeGitHub.polls, FakeGitHub.mode = 0, "ok"
    monkeypatch.setattr(oauth, "GITHUB_DEVICE_CODE_URL", base + "/device/code")
    monkeypatch.setattr(oauth, "GITHUB_USER_URL", base + "/user")
    monkeypatch.setitem(OAUTH_SPECS["github"], "token_url", base + "/token")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "gh-public-client")
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    # GitHub's live verification is its own connector call: the account is already proven by the fake /user above
    from aether.connections import oauth_finish

    monkeypatch.setattr(oauth_finish, "_verify", lambda prov, tokens, ws, ws_id: (True, "ok", tokens["account_name"]))
    ws = Workspace.init(tmp_path / "ws", name="Device")
    yield ws
    srv.shutdown()
    ws.close()


def test_github_device_flow_needs_no_secret_and_no_redirect(github):
    ws = github
    d = oauth_flow.start_github_device_flow(ws, ws.id, poll_floor=0.01)
    assert d["user_code"] == "ABCD-1234" and d["verification_uri"].endswith("/login/device") and d["state"].startswith("dev-")
    st = _wait(d["state"], "success", 10)
    assert st["status"] == "success" and st["account"] == "@matteo-test" and FakeGitHub.polls == 3, "pending answers are polled through, not treated as failure"
    conn = ws.connections.get_connection(ws.id, "github")
    assert conn and conn.status.value == "verified" and conn.auth_metadata.get("token") == "gho_fake" and not conn.auth_metadata.get("client_secret")


def test_github_device_flow_denial_is_reported(github):
    ws = github
    FakeGitHub.mode = "denied"
    d = oauth_flow.start_github_device_flow(ws, ws.id, poll_floor=0.01)
    st = _wait(d["state"], "error", 10)
    assert st["status"] == "error" and st["error"].startswith("denied:") and "said no" in st["error"]
    assert ws.connections.get_connection(ws.id, "github") is None


def test_github_device_flow_without_a_client_id_says_so(github, monkeypatch):
    monkeypatch.delenv("GITHUB_CLIENT_ID")
    with pytest.raises(ValueError, match="client ID"):
        oauth_flow.start_github_device_flow(github, github.id)


def test_bundled_clients_overlay_the_git_ignored_local_file(tmp_path, monkeypatch):
    """Ids are committed; the desktop client secret lives in a git-ignored file that is merged over them at run time."""
    import json

    import aether.connections.oauth as oauth

    (tmp_path / "oauth_clients.json").write_text(json.dumps({"_comment": "x", "google_calendar": {"client_id": "id-1", "client_secret": ""}, "github": {"client_id": "gh-1"}}))
    monkeypatch.setattr(oauth, "__file__", str(tmp_path / "oauth.py"))
    monkeypatch.setattr(oauth, "_bundled_clients", _REAL["fn"])
    assert oauth._bundled_clients()["google_calendar"] == {"client_id": "id-1"}  # no local file: id only, the empty secret is dropped
    (tmp_path / "oauth_clients.local.json").write_text(json.dumps({"google_calendar": {"client_secret": "s-1"}}))
    merged = oauth._bundled_clients()
    assert merged["google_calendar"] == {"client_id": "id-1", "client_secret": "s-1"}
    assert merged["github"] == {"client_id": "gh-1"}
    (tmp_path / "oauth_clients.local.json").write_text("{not json")
    assert oauth._bundled_clients()["google_calendar"] == {"client_id": "id-1"}  # a broken local file never breaks the app
