"""Skills tell the truth about access: one permission vocabulary, effect 'deny' enforced, readiness from real connections,
enabling a skill that needs a connection is refused until it is connected, and skill secrets never land in the team file."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from aether.connections.models import Connection, ConnectionStatus
from aether.errors import SkillPermissionDeniedError
from aether.server import routes
from aether.server.app import app, startup_event
from aether.skills.builtin import get_builtin_skills
from aether.skills.catalog import MASK, PERMISSIONS, REQUIREMENTS, is_secret_field, readiness
from aether.skills.policy import SkillPermissionPolicy
from aether.skills.skill import SkillPermission


@pytest.fixture
def booted(tmp_path: Path, monkeypatch):
    from aether.core.paths import set_aether_data_dir

    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("AETHER_WORKSPACE", raising=False)
    monkeypatch.delenv("AETHER_NO_AUTO_WORKSPACE", raising=False)
    monkeypatch.chdir(tmp_path)
    set_aether_data_dir(tmp_path / "data")
    before = {k: getattr(app.state, k, None) for k in ("workspace", "workspace_root", "team", "active_team_name")}
    asyncio.run(startup_event())
    yield app.state.workspace, app.state.team
    app.state.workspace.close()
    for k, v in before.items():
        setattr(app.state, k, v)


def _req(method="GET", path="/api/skills") -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": [], "app": app})


def test_every_builtin_permission_is_in_the_catalog_and_gets_a_risk():
    for s in get_builtin_skills():
        for p in (s.metadata or {}).get("permissions", []):
            assert p in PERMISSIONS, f"{s.name} declares '{p}' outside the vocabulary"
    assert set(REQUIREMENTS) <= {s.name for s in get_builtin_skills()}


def test_a_deny_effect_is_enforced_not_ignored():
    policy = SkillPermissionPolicy.allow_all()
    policy.check([SkillPermission(namespace="files", action="read")])
    with pytest.raises(SkillPermissionDeniedError):
        policy.check([SkillPermission(namespace="shell", action="run", effect="deny")])


def test_readiness_states():
    assert readiness("web_search", lambda p: None) is None
    assert readiness("github_tools", lambda p: None)["state"] == "not_connected"
    assert readiness("github_tools", lambda p: "verified")["state"] == "ready"
    assert readiness("github_tools", lambda p: "verification_failed")["state"] == "needs_reauth"
    assert readiness("gmail_integration", lambda p: "verified")["state"] == "unavailable", "no Gmail connector exists yet: never pretend"


def test_skills_list_comes_from_the_backend_with_readiness(booted):
    ws, _ = booted
    skills = {s.name: s for s in asyncio.run(routes.list_available_skills(_req()))}
    assert [d["id"] for d in skills["filesystem_tools"].permission_details] == ["files.read", "files.write"]
    assert skills["terminal_sandbox"].permission_details[0]["risk"] == "sensitive"
    assert skills["github_tools"].requires == {"connection": "github", "state": "not_connected"}
    assert skills["gmail_integration"].requires["state"] == "unavailable" and skills["web_search"].requires is None
    ws.connections.save_connection(Connection(id="conn-gh", workspace_id=ws.id, provider="github", account_name="@me", status=ConnectionStatus.VERIFIED, auth_metadata={"token": "t"}))
    again = {s.name: s for s in asyncio.run(routes.list_available_skills(_req()))}
    assert again["github_tools"].requires["state"] == "ready"


def test_enabling_a_skill_needs_its_connection_and_then_uses_the_real_skill(booted):
    ws, team = booted
    agent = team.config.agents[0].name
    with pytest.raises(HTTPException) as e:
        asyncio.run(routes.assign_skill_to_agent_route(_req("POST"), "github_tools", routes.SkillAssignPayload(agent_name=agent, enabled=True)))
    assert e.value.status_code == 409 and e.value.detail["code"] == "connection_required" and e.value.detail["connection"] == "github"
    assert "github_tools" not in (team.config.get_agent(agent).skills or [])
    ws.connections.save_connection(Connection(id="conn-gh", workspace_id=ws.id, provider="github", account_name="@me", status=ConnectionStatus.VERIFIED, auth_metadata={"token": "t"}))
    out = asyncio.run(routes.assign_skill_to_agent_route(_req("POST"), "github_tools", routes.SkillAssignPayload(agent_name=agent, enabled=True)))
    assert "github_tools" in out["skills"]
    live = next(a for a in team.agents() if a.name == agent)
    real = next(s for s in live.skills if s.name == "github_tools")
    assert real.instructions, "the agent gets the real skill, not an empty stub"
    # a skill that needs nothing still enables freely
    assert "web_search" in asyncio.run(routes.assign_skill_to_agent_route(_req("POST"), "web_search", routes.SkillAssignPayload(agent_name=agent, enabled=True)))["skills"]


def test_skill_secrets_go_to_the_secret_store_not_the_team_file(booted):
    ws, team = booted
    assert is_secret_field("api_key") and is_secret_field("bot_token") and not is_secret_field("channel")
    out = asyncio.run(routes.save_skill_config_route(_req("POST"), "slack_notifications", routes.SkillConfigPayload(config={"bot_token": "xoxb-very-secret", "channel": "#general"})))
    assert out["config"] == {"bot_token": MASK, "channel": "#general"}
    assert team.config.metadata["skill_configs"]["slack_notifications"]["bot_token"] == MASK
    assert ws.secret_store.get_secret("skill_config:slack_notifications:bot_token") == "xoxb-very-secret"
    again = asyncio.run(routes.save_skill_config_route(_req("POST"), "slack_notifications", routes.SkillConfigPayload(config={"bot_token": MASK, "channel": "#ops"})))
    assert ws.secret_store.get_secret("skill_config:slack_notifications:bot_token") == "xoxb-very-secret", "saving the mask back never overwrites the secret"
    assert again["config"]["channel"] == "#ops"
    for f in Path(ws.root).rglob("*.yaml"):
        assert "xoxb-very-secret" not in f.read_text(), f"{f.name} must not hold the secret"
