"""
UI reliability contracts that can be checked without a browser: the coding-status classifier (executed for real with
Node), the absence of hidden provider/model defaults in the UI sources, and the backend answer the UI renders when no
provider is configured. (Browser behaviour is verified separately, by hand/with a real browser.)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request

UI = Path(__file__).resolve().parents[1] / "ui" / "src"
NODE = shutil.which("node")


def classify(cases):
    script = (
        "import { classifyCodingResult, testOutcome, runStillActive } from %s;"
        "const cases = %s;"
        "console.log(JSON.stringify(cases.map(c => ({...classifyCodingResult(c), active: runStillActive(c), t: testOutcome(c.test_passed)}))));"
    ) % (json.dumps((UI / "codingStatus.ts").as_uri()), json.dumps(cases))
    out = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(NODE is None, reason="node is required to execute the TypeScript classifier")
class TestCodingStatusClassifier:
    def test_only_a_verified_completed_run_is_success(self):
        r = classify([
            {"status": "completed", "verified": True, "deliverable_ready": True},
            {"status": "completed", "verification_passed": True},
            {"status": "completed"},                                           # no proof
            {"status": "completed", "verified": False, "verification_passed": False},
        ])
        assert [x["kind"] for x in r] == ["completed", "completed", "unverified", "unverified"]
        assert [x["pillClass"] for x in r] == ["status-completed", "status-completed", "status-unverified", "status-unverified"]
        assert [x["verified"] for x in r] == [True, True, False, False]

    def test_waiting_runs_are_never_green_and_ask_for_the_user(self):
        r = classify([{"status": "waiting_for_interaction", "awaiting": "interaction"},
                      {"status": "waiting_for_approval"}, {"status": "completed", "awaiting": "approval", "run_terminal": False}])
        assert all(x["pillClass"] == "status-waiting" and x["workStatus"] == "needs-you" and not x["verified"] for x in r)
        assert "ATTESA" in r[0]["label"]

    def test_rework_failures_and_active_runs(self):
        r = classify([{"status": "requires_rework"}, {"status": "failed"}, {"status": "timed_out"}, {"status": "cancelled"},
                      {"status": "running"}, {"status": "queued"}, {"status": "completed", "run_terminal": False}])
        assert [x["kind"] for x in r] == ["needs_review", "failed", "failed", "failed", "active", "active", "active"]
        assert r[0]["pillClass"] == "status-review" and not r[0]["verified"]
        assert all(x["pillClass"] != "status-completed" for x in r)
        assert [x["active"] for x in r] == [False, False, False, False, True, True, True]

    def test_unknown_or_missing_state_never_claims_success(self):
        r = classify([{}, {"status": "something-new"}])
        assert all(x["pillClass"] != "status-completed" and x["verified"] is False for x in r)

    def test_test_output_is_neutral_unless_the_run_said_so(self):
        r = classify([{"status": "completed", "test_passed": True}, {"status": "completed", "test_passed": False}, {"status": "completed"}])
        assert [x["t"] for x in r] == ["passed", "failed", "unknown"]


HIDDEN_DEFAULT = re.compile(r"(useState\(\s*['\"](ollama|openai)['\"]\s*\))|(\|\|\s*['\"](ollama|qwen3\.5:9b)['\"])|(\?\?\s*['\"]ollama['\"])")


def test_ui_has_no_hidden_provider_or_model_defaults():
    offenders = []
    for f in sorted(UI.glob("*.tsx")) + sorted(UI.glob("*.ts")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if HIDDEN_DEFAULT.search(line):
                offenders.append(f"{f.name}:{n}: {line.strip()[:110]}")
    assert not offenders, "\n".join(offenders)


def test_provider_selects_offer_groq_and_an_unset_option():
    # WorkspaceModal.tsx was removed with the single personal space; the first-run model card lives in FirstRunModel.tsx.
    for name in ("Teams.tsx", "AutoArchitectModal.tsx", "AgentBuilder.tsx", "Settings.tsx"):
        src = (UI / name).read_text()
        assert 'value="groq"' in src, name
    for name in ("Teams.tsx", "AutoArchitectModal.tsx", "Settings.tsx"):
        assert 'option value=""' in (UI / name).read_text(), name


def test_model_selector_makes_no_request_without_a_provider():
    src = (UI / "ModelSelector.tsx").read_text()
    assert "provider || 'ollama'" not in src
    assert "if (!provider) {" in src


@pytest.mark.asyncio
async def test_settings_endpoint_without_provider_returns_empty_strings_not_a_guess(tmp_path):
    from aether.server.app import app
    from aether.server.routes import get_provider_settings
    from aether.workspace.workspace import Workspace

    app.state.workspace = Workspace.init(tmp_path / "ws", "Settings WS")
    app.state.team = None
    out = await get_provider_settings(Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": app}))
    assert out["provider"] == "" and out["model"] == ""
    assert out["timeout"] > 0 and set(out["configured"]) >= {"openai", "anthropic", "gemini", "groq", "ollama"}


def test_team_level_model_select_has_an_unselected_placeholder():
    # Reproduced in the browser: with no option for "nothing chosen" the first model looked selected while the state was empty.
    src = (UI / "ModelSelector.tsx").read_text()
    assert '<option value="" disabled>' in src and "isTeamLevel && (" in src


@pytest.mark.asyncio
async def test_provider_can_be_chosen_on_a_workspace_without_a_team(tmp_path):
    # Reproduced in the real app: Settings -> Save answered 503 "Complete onboarding" for a workspace that has no team.
    import yaml
    from aether.server.app import app
    from aether.server.routes import ProviderSettings, get_provider_settings, save_provider_settings
    from aether.workspace.workspace import Workspace

    ws = Workspace.init(tmp_path / "ws", "No Team WS")
    app.state.workspace, app.state.team = ws, None
    req = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "app": app})
    assert (await save_provider_settings(req, ProviderSettings(provider="groq", model="qwen/test-model", timeout=30))) == {"status": "ok"}
    persisted = yaml.safe_load(ws.config_path.read_text())["workspace"]
    assert (persisted["default_provider"], persisted["default_model"]) == ("groq", "qwen/test-model")
    out = await get_provider_settings(req)
    assert (out["provider"], out["model"]) == ("groq", "qwen/test-model")


def test_accepting_a_proposal_in_the_classic_home_actually_dispatches_the_work():
    # Reproduced in the browser: "accepted and authorized for execution" but the response's authority was thrown
    # away and nothing ever ran. The accept handler must send the original request again WITH the authority.
    src = (UI / "Home.tsx").read_text()
    handler = src[src.index("const handleApproveProposal"):src.index("const handleRejectProposal")]
    assert "accepted?.authority" in handler and "/api/personal/chat" in handler and "authority," in handler


# --- QA pass 2026-10-14 ---------------------------------------------------------------------------------------

@pytest.mark.skipif(NODE is None, reason="node is required to execute the TypeScript module")
def test_only_a_404_marks_the_stored_session_as_stale():
    script = (
        "import { classifyRestoreResponse, forgetStaleSession, ACTIVE_SESSION_KEY } from %s;"
        "const store = new Map([[ACTIVE_SESSION_KEY, 's-old']]);"
        "const storage = { getItem: k => store.get(k) ?? null, removeItem: k => store.delete(k) };"
        "const out = { codes: [200, 404, 401, 429, 500, 502, null].map(c => classifyRestoreResponse(c)),"
        " forgotNewer: forgetStaleSession(storage, 's-other'), keptAfterNewer: store.has(ACTIVE_SESSION_KEY),"
        " forgot: forgetStaleSession(storage, 's-old'), gone: !store.has(ACTIVE_SESSION_KEY) };"
        "console.log(JSON.stringify(out));"
    ) % json.dumps((UI / "sessionRestore.ts").as_uri())
    out = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["codes"] == ["restored", "stale", "keep", "keep", "keep", "keep", "keep"]
    assert r["forgotNewer"] is False and r["keptAfterNewer"] is True      # a newer id is never wiped
    assert r["forgot"] is True and r["gone"] is True


def _luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _hsl_to_hex(h, s, l):
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return "#%02x%02x%02x" % tuple(round(x * 255) for x in (r, g, b))


def test_sidebar_labels_come_from_the_translation_dictionaries():
    sidebar = (UI / "Sidebar.tsx").read_text()
    for literal in ("Risultati", "Risorse Computer", "Risorse del Computer", "Memoria & Contesto", "Attività Recenti", ">Sistema<"):
        assert literal not in sidebar, literal
    i18n = (UI / "i18n.tsx").read_text()
    en, it = i18n[:i18n.index("\n  it: {")], i18n[i18n.index("\n  it: {"):]
    for key in ("navResults", "navResultsTooltip", "navSystem", "navComputerResources",
                "navComputerResourcesTooltip", "navMemoryContext", "navRecentActivity"):
        assert f"{key}:" in en and f"{key}:" in it, key
        assert f"t('{key}')" in sidebar, key


# --- Google Calendar API: explicit states instead of a 500 -------------------------------------------------------

def _gc_ws(tmp_path):
    from aether.workspace.workspace import Workspace
    return Workspace.init(tmp_path / "ws", "GC WS")


def _gc_request(ws):
    from aether.server.app import app
    app.state.workspace = ws
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": app})


@pytest.mark.asyncio
async def test_google_calendar_not_configured_is_a_404_not_a_500(tmp_path):
    from fastapi import HTTPException
    from aether.server.routes import list_google_calendar_events_route, list_google_calendars_route
    ws = _gc_ws(tmp_path)
    for route in (list_google_calendar_events_route, list_google_calendars_route):
        with pytest.raises(HTTPException) as exc:
            await route(_gc_request(ws))
        assert exc.value.status_code == 404 and "not configured" in exc.value.detail


@pytest.mark.asyncio
async def test_google_calendar_disconnected_is_a_409(tmp_path):
    from fastapi import HTTPException
    from aether.connections.models import Connection, ConnectionStatus
    from aether.server.routes import list_google_calendar_events_route
    ws = _gc_ws(tmp_path)
    ws.connections.save_connection(Connection(id="c1", workspace_id=ws.id, provider="google_calendar", account_name="Google Calendar",
                                              status=ConnectionStatus.DISCONNECTED, auth_metadata={}))
    with pytest.raises(HTTPException) as exc:
        await list_google_calendar_events_route(_gc_request(ws))
    assert exc.value.status_code == 409 and "disconnected" in exc.value.detail


@pytest.mark.asyncio
async def test_a_real_provider_failure_is_a_502_and_never_an_empty_list(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from aether.connections.base import ConnectorAuthError
    from aether.connections.models import Connection, ConnectionStatus
    from aether.server.routes import list_google_calendar_events_route
    ws = _gc_ws(tmp_path)
    ws.connections.save_connection(Connection(id="c1", workspace_id=ws.id, provider="google_calendar", account_name="Google Calendar",
                                              status=ConnectionStatus.VERIFIED, auth_metadata={"access_token": "x"}))

    class Boom:
        def list_events(self, **kw):
            raise ConnectorAuthError("token expired", provider="google_calendar")

    monkeypatch.setattr(ws.connections, "get_google_calendar_connector", lambda workspace_id: Boom())
    with pytest.raises(HTTPException) as exc:
        await list_google_calendar_events_route(_gc_request(ws))
    assert exc.value.status_code == 502 and "token expired" in exc.value.detail
