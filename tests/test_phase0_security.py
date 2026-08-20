"""
Tests for PRE-04: Local Runtime Security (Session Token, WebSocket Auth, CORS & Origin Validation).
"""
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from aether.server.app import app, session_token_middleware
from aether.server.sockets import websocket_endpoint, _ALLOWED_ORIGIN_REGEX
from aether.workspace.workspace import Workspace
from aether.presets.applier import PresetApplier


class MockSecurityWebSocket:
    def __init__(self, app_instance, headers=None, query_params=None):
        self.app = app_instance
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.sent = []
        self.closed = False
        self.close_code = None

    async def accept(self):
        pass

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=1000):
        self.closed = True
        self.close_code = code

    async def receive_text(self):
        raise Exception("Closed")


@pytest.mark.asyncio
async def test_session_token_rest_middleware_auth():
    """Middleware enforces valid token for /api/* while exempting /api/health."""
    app.state.session_token = "secret-token-xyz-123"

    async def dummy_call_next(request):
        return JSONResponse({"status": "ok"})

    # 1. Health check is exempt
    req_health = Request({
        "type": "http",
        "app": app,
        "path": "/api/health",
        "method": "GET",
        "headers": [],
    })
    res_health = await session_token_middleware(req_health, dummy_call_next)
    assert res_health.status_code == 200

    # 2. Other endpoint without token -> 401
    req_unauth = Request({
        "type": "http",
        "app": app,
        "path": "/api/workspace",
        "method": "GET",
        "headers": [],
    })
    res_unauth = await session_token_middleware(req_unauth, dummy_call_next)
    assert res_unauth.status_code == 401

    # 3. Other endpoint with wrong token -> 401
    req_bad = Request({
        "type": "http",
        "app": app,
        "path": "/api/workspace",
        "method": "GET",
        "headers": [(b"x-aether-session-token", b"wrong-token")],
    })
    res_bad = await session_token_middleware(req_bad, dummy_call_next)
    assert res_bad.status_code == 401

    # 4. Other endpoint with valid X-Aether-Session-Token -> 200
    req_valid_header = Request({
        "type": "http",
        "app": app,
        "path": "/api/workspace",
        "method": "GET",
        "headers": [(b"x-aether-session-token", b"secret-token-xyz-123")],
    })
    res_valid_header = await session_token_middleware(req_valid_header, dummy_call_next)
    assert res_valid_header.status_code == 200

    # 5. Other endpoint with valid Authorization: Bearer <token> -> 200
    req_valid_bearer = Request({
        "type": "http",
        "app": app,
        "path": "/api/workspace",
        "method": "GET",
        "headers": [(b"authorization", b"Bearer secret-token-xyz-123")],
    })
    res_valid_bearer = await session_token_middleware(req_valid_bearer, dummy_call_next)
    assert res_valid_bearer.status_code == 200

    # Cleanup
    app.state.session_token = None


def test_allowed_origin_regex():
    """Verify origin regex allows localhost, 127.0.0.1, and tauri schemes, blocking external domains."""
    valid_origins = [
        "http://localhost",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://localhost:49152",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:54321",
        "tauri://localhost",
        "https://tauri.localhost",
        "app://localhost",
    ]
    invalid_origins = [
        "https://evil.com",
        "http://malicious.org",
        "http://attacker.local",
        "http://192.168.1.50:8000",
        "https://google.com",
    ]

    for origin in valid_origins:
        assert _ALLOWED_ORIGIN_REGEX.match(origin) is not None, f"Expected {origin} to be valid"

    for origin in invalid_origins:
        assert _ALLOWED_ORIGIN_REGEX.match(origin) is None, f"Expected {origin} to be invalid"


@pytest.mark.asyncio
async def test_websocket_token_and_origin_security(tmp_path):
    """WebSocket endpoint validates session token and origin."""
    ws_dir = tmp_path / "ws-sec-ws"
    ws = Workspace.init(ws_dir, name="WS Sec Workspace")
    PresetApplier().apply_preset("starter-workforce", ws)

    app.state.workspace = ws
    app.state.workspace_root = ws.root
    app.state.team = ws.load_team()
    app.state.active_team_name = "default"
    app.state.session_token = "ws-secret-token-999"

    # 1. Connection without token receives error and code 1008
    mock_no_token = MockSecurityWebSocket(app)
    await websocket_endpoint(mock_no_token)
    assert mock_no_token.closed is True
    assert mock_no_token.close_code == 1008
    assert len(mock_no_token.sent) > 0
    assert "Unauthorized" in mock_no_token.sent[0]["message"]

    # 2. Connection with wrong token receives error and code 1008
    mock_bad_token = MockSecurityWebSocket(app, query_params={"token": "wrong-token"})
    await websocket_endpoint(mock_bad_token)
    assert mock_bad_token.closed is True
    assert mock_bad_token.close_code == 1008
    assert "Unauthorized" in mock_bad_token.sent[0]["message"]

    # 3. Connection with invalid origin is rejected with code 1008
    mock_bad_origin = MockSecurityWebSocket(
        app,
        headers={"origin": "https://malicious-site.com"},
        query_params={"token": "ws-secret-token-999"},
    )
    await websocket_endpoint(mock_bad_origin)
    assert mock_bad_origin.closed is True
    assert mock_bad_origin.close_code == 1008
    assert "Forbidden" in mock_bad_origin.sent[0]["message"]

    # Cleanup
    app.state.session_token = None
