"""One-click OAuth for the desktop app: a short-lived loopback listener per flow (RFC 8252), a status you can poll, and cancel.

The browser comes back to `http://127.0.0.1:<random free port>/callback`, a tiny server that lives only for this flow. It works for any
provider that accepts loopback redirects (Google desktop clients, GitHub) and does not depend on the main API's ephemeral port.
The page the browser shows is plain and static; the app learns the outcome by polling `FlowRegistry.status(state)`.
"""
from __future__ import annotations

import html
import http.server
import logging
import socket
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from aether.connections.oauth import OAUTH_SPECS, OAuthManager
from aether.connections import oauth as oauth_mod
from aether.connections.oauth_finish import FinishResult, finish_oauth, finish_with_tokens

logger = logging.getLogger(__name__)

FLOW_TTL_SECONDS = 180

_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Aether</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0b0b0d;color:#f4f4f5;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
main{{max-width:420px;text-align:center;padding:0 24px}}h1{{font-size:20px;font-weight:600;margin:0 0 8px}}p{{color:#a1a1aa;line-height:1.5;margin:0}}
.dot{{width:10px;height:10px;border-radius:50%;background:{color};margin:0 auto 18px}}</style></head><body><main><div class="dot"></div><h1>{title}</h1><p>{body}</p></main></body></html>"""


@dataclass
class Flow:
    state: str
    provider: str
    workspace_id: str
    created_at: float
    status: str = "pending"  # pending | success | error | expired | cancelled
    account: str = ""
    error: str = ""
    server: Any = None
    thread: Any = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class FlowRegistry:
    _flows: dict[str, Flow] = {}
    _guard = threading.Lock()

    @classmethod
    def status(cls, state: str) -> dict[str, Any] | None:
        with cls._guard:
            f = cls._flows.get(state)
        if f is None:
            return None
        if f.status == "pending" and time.time() - f.created_at > FLOW_TTL_SECONDS:
            cls._close(f, "expired", "The authorization took too long.")
        return {"state": f.state, "provider": f.provider, "status": f.status, "account": f.account, "error": f.error}

    @classmethod
    def cancel(cls, state: str) -> bool:
        with cls._guard:
            f = cls._flows.get(state)
        if f is None:
            return False
        cls._close(f, "cancelled", "")
        return True

    @classmethod
    def _close(cls, f: Flow, status: str, error: str, account: str = "") -> None:
        with f.lock:
            if f.status != "pending":
                return
            f.status, f.error, f.account = status, error, account
        OAuthManager._states.pop(f.state, None)
        srv = f.server
        if srv is not None:
            threading.Thread(target=srv.shutdown, daemon=True).start()

    @classmethod
    def _gc(cls) -> None:
        cutoff = time.time() - 900
        with cls._guard:
            for s in [s for s, f in cls._flows.items() if f.created_at < cutoff]:
                cls._flows.pop(s, None)

    @classmethod
    def start(cls, ws: Any, provider: str, workspace_id: str) -> dict[str, Any]:
        """Starts the listener, builds the authorization URL and returns {state, auth_url, redirect_uri}."""
        cls._gc()
        if provider not in OAUTH_SPECS:
            raise ValueError(f"Provider '{provider}' does not support OAuth authorization.")
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        redirect_uri = f"http://127.0.0.1:{port}/callback"
        auth_url, state, redirect_uri = OAuthManager.create_auth_flow(
            provider=provider, workspace_id=workspace_id, redirect_uri=redirect_uri,
            store=ws.connections.store if ws is not None else None,
        )
        flow = Flow(state=state, provider=provider, workspace_id=workspace_id, created_at=time.time())

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:  # silence: query strings carry the code
                return

            def _send(self, code: int, title: str, body: str, color: str) -> None:
                data = _PAGE.format(title=html.escape(title), body=html.escape(body), color=color).encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                url = urllib.parse.urlparse(self.path)
                if url.path != "/callback":
                    self._send(404, "Not found", "", "#71717a")
                    return
                q = urllib.parse.parse_qs(url.query)
                got_state = (q.get("state") or [""])[0]
                if got_state != flow.state:
                    self._send(400, "Invalid request", "This authorization does not belong to Aether. You can close this tab.", "#ef4444")
                    return
                if "error" in q:
                    reason = (q.get("error_description") or q.get("error") or ["denied"])[0]
                    cls._close(flow, "error", f"denied:{reason}")
                    self._send(200, "Authorization cancelled", "Nothing was connected. You can close this tab and return to Aether.", "#a1a1aa")
                    return
                code = (q.get("code") or [""])[0]
                state_data = OAuthManager.validate_and_consume_state(got_state)
                if not code or state_data is None:
                    cls._close(flow, "error", "invalid_state")
                    self._send(400, "Session expired", "Start the connection again from Aether.", "#ef4444")
                    return
                res: FinishResult = finish_oauth(ws, provider, code, state_data)
                if res.ok:
                    cls._close(flow, "success", "", res.account_name)
                    self._send(200, "Connected", f"{res.account_name or 'Your account'} is connected. You can close this tab and return to Aether.", "#10b981")
                else:
                    cls._close(flow, "error", f"{res.code}:{res.message}"[:300])
                    self._send(200, "Could not connect", "Aether could not complete the connection. Return to Aether for details.", "#ef4444")

        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        server.daemon_threads = True
        flow.server = server
        flow.thread = threading.Thread(target=server.serve_forever, daemon=True)
        flow.thread.start()
        with cls._guard:
            cls._flows[state] = flow

        def reaper() -> None:  # the listener never outlives the flow's time limit
            time.sleep(FLOW_TTL_SECONDS + 2)
            cls.status(state)

        threading.Thread(target=reaper, daemon=True).start()
        return {"state": state, "auth_url": auth_url, "redirect_uri": redirect_uri}


def _form_post(url: str, payload: dict[str, str]) -> dict[str, Any]:
    import json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=urllib.parse.urlencode(payload).encode(), method="POST",
                                 headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Aether/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return {"error": f"http_{e.code}"}


def start_github_device_flow(ws: Any, workspace_id: str, *, poll_floor: float = 1.0) -> dict[str, Any]:
    """GitHub device flow: the user types a short code at github.com/login/device; no secret and no redirect are needed (public client id only)."""
    cid, _ = OAuthManager.resolve_credentials("github", workspace_id, ws.connections.store if ws is not None else None)
    if not cid:
        raise ValueError("A GitHub client ID is required: connect GitHub from Advanced or ship a client id with the app.")
    scope = " ".join(OAUTH_SPECS["github"]["scopes"])
    d = _form_post(oauth_mod.GITHUB_DEVICE_CODE_URL, {"client_id": cid, "scope": scope})
    if "device_code" not in d:
        raise ValueError(f"GitHub did not start the device flow: {d.get('error_description') or d.get('error') or 'unknown error'}")
    state = "dev-" + secrets_token()
    flow = Flow(state=state, provider="github", workspace_id=workspace_id, created_at=time.time())
    with FlowRegistry._guard:
        FlowRegistry._flows[state] = flow
    interval = max(float(d.get("interval", 5)), poll_floor)
    deadline = time.time() + min(float(d.get("expires_in", 900)), 900)

    def poll() -> None:
        wait = interval
        while time.time() < deadline and flow.status == "pending":
            time.sleep(wait)
            if flow.status != "pending":
                return
            r = _form_post(OAUTH_SPECS["github"]["token_url"], {"client_id": cid, "device_code": d["device_code"], "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
            err = r.get("error")
            if r.get("access_token"):
                tokens = oauth_mod.github_tokens(r["access_token"], cid, "", r.get("scope", ""), r.get("token_type", "bearer"))
                res = finish_with_tokens(ws, "github", tokens, workspace_id)
                FlowRegistry._close(flow, "success" if res.ok else "error", "" if res.ok else f"{res.code}:{res.message}"[:300], res.account_name)
                return
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                wait += 5
                continue
            FlowRegistry._close(flow, "error", f"denied:{r.get('error_description') or err}" if err == "access_denied" else f"{err}")
            return
        FlowRegistry._close(flow, "expired", "The code expired.")

    threading.Thread(target=poll, daemon=True).start()
    return {"state": state, "user_code": d["user_code"], "verification_uri": d.get("verification_uri", "https://github.com/login/device"), "expires_in": d.get("expires_in", 900)}


def secrets_token() -> str:
    import secrets

    return secrets.token_urlsafe(24)
