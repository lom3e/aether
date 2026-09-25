"""
Test Suite for Macro Step 12: Ecosystem and Marketplace Foundation
(Workforces, Skills, Tools, Connectors, Workflow Templates, Security & Permission Summaries).

Verifies end-to-end:
1. EcosystemStore SQLite persistence (marketplace.db, zero simulation).
2. Curated package catalog auto-seeding across all 5 package types.
3. SecuritySummary & Permission risk level assessment.
4. Physical package installation (Workforce, Skill, Workflow Template) into workspace.
5. Physical package uninstallation and artifact cleanup.
6. ActionExecutor execution of marketplace.list, marketplace.inspect, marketplace.install, marketplace.uninstall.
7. Personal Companion natural language intent recognition.
8. FastAPI route handlers: list, get, security, install, uninstall.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from starlette.datastructures import State
from starlette.requests import Request

from aether.actions.executor import ActionExecutor, ActionSafetyPolicy
from aether.actions.models import ActionExecutionStatus
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.ecosystem.models import (
    InstalledPackage,
    PackageManifest,
    PackagePermission,
    PackageType,
    RiskLevel,
    SecuritySummary,
)
from aether.ecosystem.store import EcosystemStore
from aether.personal.models import IntentTier
from aether.personal.service import PersonalAgentService
from aether.server.routes import (
    InstallPackagePayload,
    get_marketplace_package_route,
    get_marketplace_package_security_route,
    install_marketplace_package_route,
    list_marketplace_packages_route,
    uninstall_marketplace_package_route,
)
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_ws(tmp_path: Path) -> Workspace:
    ws = Workspace.get_or_init(tmp_path, name="ecosystem_test_ws")
    return ws


# ---------------------------------------------------------------------------
# 1. EcosystemStore Persistence & Auto-Seeding
# ---------------------------------------------------------------------------

def test_ecosystem_store_auto_seeding_and_crud(temp_ws: Workspace):
    store = temp_ws.ecosystem
    assert isinstance(store, EcosystemStore)
    assert Path(temp_ws.ecosystem_db_path).exists()

    # Verify seeded packages exist
    all_pkgs = store.list_packages()
    assert len(all_pkgs) >= 7

    types = {p["type"] for p in all_pkgs}
    assert PackageType.WORKFORCE.value in types
    assert PackageType.SKILL.value in types
    assert PackageType.TOOL.value in types
    assert PackageType.CONNECTOR.value in types
    assert PackageType.WORKFLOW_TEMPLATE.value in types

    # Filter by type
    workforces = store.list_packages(pkg_type="workforce")
    assert len(workforces) >= 2
    assert all(w["type"] == "workforce" for w in workforces)

    # Filter by category
    sec_pkgs = store.list_packages(category="security")
    assert len(sec_pkgs) >= 2

    # Filter by search
    k8s_pkgs = store.list_packages(search="kubernetes")
    assert len(k8s_pkgs) >= 1
    assert "docker-k8s" in k8s_pkgs[0]["id"]


# ---------------------------------------------------------------------------
# 2. Security Summary & Permissions Inspection
# ---------------------------------------------------------------------------

def test_security_summary_inspection(temp_ws: Workspace):
    store = temp_ws.ecosystem
    sec_pkg = store.get_package("workforce-secops-defense")
    assert sec_pkg is not None
    assert sec_pkg.security_summary.risk_level in (RiskLevel.MEDIUM, RiskLevel.LOW)
    assert len(sec_pkg.security_summary.permissions) >= 1
    assert any("filesystem:read" in p.name for p in sec_pkg.security_summary.permissions)
    assert "nvd.nist.gov" in sec_pkg.security_summary.network_domains

    summary = store.get_security_summary("workforce-secops-defense")
    assert summary is not None
    assert summary.risk_level == sec_pkg.security_summary.risk_level


# ---------------------------------------------------------------------------
# 3. Package Installation & Uninstallation Engine
# ---------------------------------------------------------------------------

def test_package_installation_and_cleanup(temp_ws: Workspace):
    store = temp_ws.ecosystem

    # 1. Install Skill Package
    assert not store.is_installed("skill-docker-k8s", temp_ws.name)
    installed_skill = store.install_package("skill-docker-k8s", temp_ws)
    assert installed_skill.package_id == "skill-docker-k8s"
    assert store.is_installed("skill-docker-k8s", temp_ws.name)

    # Check physical file creation
    skill_file = temp_ws.root / ".aether" / "skills" / "docker-k8s" / "SKILL.md"
    assert skill_file.exists()
    assert "Kubernetes & Docker Skill" in skill_file.read_text(encoding="utf-8")

    # 2. Install Workflow Template Package
    installed_wf = store.install_package("workflow-continuous-security", temp_ws)
    assert installed_wf.package_id == "workflow-continuous-security"
    assert store.is_installed("workflow-continuous-security", temp_ws.name)

    # Check that workflow was persisted in workspace.workflows
    wf = temp_ws.workflows.get_workflow("wf_workflow_continuous_security", workspace_id=temp_ws.name)
    assert wf is not None
    assert len(wf.graph.nodes) >= 3

    # 3. List installed
    installed_list = store.list_installed(temp_ws.name)
    assert len(installed_list) >= 2
    installed_ids = {p.package_id for p in installed_list}
    assert "skill-docker-k8s" in installed_ids
    assert "workflow-continuous-security" in installed_ids

    # 4. Uninstall Skill Package
    uninstalled = store.uninstall_package("skill-docker-k8s", temp_ws)
    assert uninstalled is True
    assert not store.is_installed("skill-docker-k8s", temp_ws.name)
    assert not skill_file.exists()

    # 5. Uninstall Workflow Package
    uninstalled_wf = store.uninstall_package("workflow-continuous-security", temp_ws)
    assert uninstalled_wf is True
    assert not store.is_installed("workflow-continuous-security", temp_ws.name)
    assert temp_ws.workflows.get_workflow("wf_workflow_continuous_security", workspace_id=temp_ws.name) is None


# ---------------------------------------------------------------------------
# 4. ActionExecutor Marketplace Actions
# ---------------------------------------------------------------------------

def test_action_executor_marketplace_actions(temp_ws: Workspace):
    registry = ActionRegistry()
    store = ActionStore(temp_ws.root / ".aether" / "actions.db")
    safety = ActionSafetyPolicy()
    executor = ActionExecutor(registry=registry, store=store, project_path=temp_ws.root, safety_policy=safety)

    # 1. marketplace.list
    res_list = executor.execute("marketplace.list", temp_ws.name, {})
    assert res_list.status == ActionExecutionStatus.SUCCESS
    assert res_list.output_data["count"] >= 7
    assert len(res_list.output_data["packages"]) >= 7

    # 2. marketplace.inspect
    res_inspect = executor.execute("marketplace.inspect", temp_ws.name, {"package_id": "workforce-fullstack-dev"})
    assert res_inspect.status == ActionExecutionStatus.SUCCESS
    assert res_inspect.output_data["package"]["id"] == "workforce-fullstack-dev"
    assert "security_summary" in res_inspect.output_data

    # 3. marketplace.install
    res_install = executor.execute(
        "marketplace.install",
        temp_ws.name,
        {"package_id": "tool-sql-introspect"},
        auto_approve=True,
    )
    assert res_install.status == ActionExecutionStatus.SUCCESS
    assert res_install.output_data["package_id"] == "tool-sql-introspect"
    assert res_install.output_data["installed"] is True
    assert temp_ws.ecosystem.is_installed("tool-sql-introspect", temp_ws.name)

    # 4. marketplace.uninstall
    res_uninstall = executor.execute(
        "marketplace.uninstall",
        temp_ws.name,
        {"package_id": "tool-sql-introspect"},
        auto_approve=True,
    )
    assert res_uninstall.status == ActionExecutionStatus.SUCCESS
    assert res_uninstall.output_data["package_id"] == "tool-sql-introspect"
    assert res_uninstall.output_data["uninstalled"] is True
    assert not temp_ws.ecosystem.is_installed("tool-sql-introspect", temp_ws.name)


# ---------------------------------------------------------------------------
# 5. Personal Companion Intent Recognition
# ---------------------------------------------------------------------------

def test_personal_companion_marketplace_intent(temp_ws: Workspace):
    service = PersonalAgentService(
        store=MagicMock(),
        action_executor=MagicMock(),
        activity_service=MagicMock(),
        workspace=temp_ws,
    )

    # 1. List marketplace packages
    intent_list = service.classify_intent("mostra il catalogo marketplace di aether")
    assert intent_list.tier == IntentTier.ANSWER
    assert intent_list.action_id == "marketplace.list"

    # 2. Inspect package
    intent_inspect = service.classify_intent("mostra sicurezza pacchetto workforce-secops-defense")
    assert intent_inspect.tier == IntentTier.ANSWER
    assert intent_inspect.action_id == "marketplace.inspect"
    assert intent_inspect.action_args["package_id"] == "workforce-secops-defense"

    # 3. Install package
    intent_install = service.classify_intent("installa pacchetto skill-docker-k8s nel workspace")
    assert intent_install.tier == IntentTier.ACT
    assert intent_install.action_id == "marketplace.install"
    assert intent_install.action_args["package_id"] == "skill-docker-k8s"

    # 4. Uninstall package
    intent_uninstall = service.classify_intent("disinstalla pacchetto skill-docker-k8s")
    assert intent_uninstall.tier == IntentTier.ACT
    assert intent_uninstall.action_id == "marketplace.uninstall"
    assert intent_uninstall.action_args["package_id"] == "skill-docker-k8s"

    service.close()


# ---------------------------------------------------------------------------
# 6. FastAPI Routes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fastapi_marketplace_routes(temp_ws: Workspace):
    mock_req = MagicMock(spec=Request)
    mock_req.app = MagicMock()
    mock_req.app.state = State()
    mock_req.app.state.workspace = temp_ws

    # 1. GET /api/marketplace/packages
    pkgs = await list_marketplace_packages_route(mock_req, workspace_id=temp_ws.name)
    assert len(pkgs) >= 7

    # 2. GET /api/marketplace/packages/{package_id}
    pkg = await get_marketplace_package_route(mock_req, package_id="connector-slack-ops")
    assert pkg["id"] == "connector-slack-ops"
    assert pkg["is_installed"] is False

    # 3. GET /api/marketplace/packages/{package_id}/security
    sec = await get_marketplace_package_security_route(mock_req, package_id="connector-slack-ops")
    assert "risk_level" in sec
    assert "permissions" in sec

    # 4. POST /api/marketplace/packages/{package_id}/install
    inst = await install_marketplace_package_route(mock_req, package_id="connector-slack-ops")
    assert inst["package_id"] == "connector-slack-ops"
    assert inst["enabled"] is True

    # Check status updated
    pkg_updated = await get_marketplace_package_route(mock_req, package_id="connector-slack-ops")
    assert pkg_updated["is_installed"] is True

    # 5. POST /api/marketplace/packages/{package_id}/uninstall
    uninst = await uninstall_marketplace_package_route(mock_req, package_id="connector-slack-ops")
    assert uninst["uninstalled"] is True

    pkg_after = await get_marketplace_package_route(mock_req, package_id="connector-slack-ops")
    assert pkg_after["is_installed"] is False
