"""
Tests for Phase 8: Chat Projects & Conversation Organization.

Validates:
1. Creation of Project model.
2. Persistence of Project in SQLite database.
3. Renaming of Project.
4. Deletion of Project without deleting conversations (conversations unlink to project_id=None).
5. Pin / Unpin conversation lifecycle and order ranking.
6. Assignment of conversation to Project.
7. Removal of conversation from Project.
8. Workspace isolation of Projects.
9. Workspace isolation of conversations and Project assignments.
10. Backward compatibility with legacy conversations database (automatic column migration).
11. Full REST API endpoints (Projects and Conversations pin/project).
12. Persistence after workspace restart / reload.
"""
import sqlite3
import pytest
from pathlib import Path
from starlette.requests import Request
from fastapi import HTTPException

from aether.workspace.workspace import Workspace
from aether.conversations.store import ConversationStore
from aether.server.app import app
from aether.server.routes import (
    list_projects,
    create_project,
    get_project,
    update_project,
    delete_project,
    CreateProjectPayload,
    UpdateProjectPayload,
    list_conversations,
    create_conversation,
    get_conversation,
    update_conversation,
    pin_conversation_endpoint,
    assign_conversation_project,
    CreateConversationPayload,
    PinConversationPayload,
    AssignProjectPayload,
)


from aether.presets.applier import PresetApplier

@pytest.fixture
def workspace_a(tmp_path):
    ws_dir = tmp_path / "workspace_a"
    ws = Workspace.init(ws_dir, name="Workspace A")
    PresetApplier().apply_preset("starter-workforce", ws)
    return ws


@pytest.fixture
def workspace_b(tmp_path):
    ws_dir = tmp_path / "workspace_b"
    ws = Workspace.init(ws_dir, name="Workspace B")
    PresetApplier().apply_preset("starter-workforce", ws)
    return ws


def test_project_crud_and_persistence(workspace_a):
    """Create, retrieve, rename, and persist project within workspace."""
    store = workspace_a.conversations

    # 1. Create project
    proj = store.create_project(name="Alpha Project")
    assert proj["name"] == "Alpha Project"
    pid = proj["id"]

    # 2. Get project
    fetched = store.get_project(pid)
    assert fetched is not None
    assert fetched["id"] == pid
    assert fetched["name"] == "Alpha Project"
    assert fetched["conversation_count"] == 0

    # 3. Rename project
    updated = store.update_project(pid, name="Alpha Project v2")
    assert updated is not None
    assert updated["name"] == "Alpha Project v2"

    # 4. List projects
    projs = store.list_projects()
    assert len(projs) == 1
    assert projs[0]["name"] == "Alpha Project v2"

    # 5. Persistence across new store instance
    reloaded_store = ConversationStore(workspace_a.conversations_db_path)
    reloaded_proj = reloaded_store.get_project(pid)
    assert reloaded_proj is not None
    assert reloaded_proj["name"] == "Alpha Project v2"


def test_conversation_pin_unpin_and_ranking(workspace_a):
    """Conversations can be pinned and unpinned, and list() sorts pinned conversations first."""
    store = workspace_a.conversations

    c1 = store.create(title="Normal Task 1")
    c2 = store.create(title="Normal Task 2")
    c3 = store.create(title="Important Task", pinned=True)

    # c3 is pinned, should be ranked first
    convs = store.list()
    assert convs[0]["id"] == c3["id"]
    assert convs[0]["pinned"] is True

    # Pin c1
    store.pin(c1["id"], pinned=True)
    c1_fetched = store.get(c1["id"])
    assert c1_fetched["pinned"] is True

    # Unpin c3
    store.pin(c3["id"], pinned=False)
    c3_fetched = store.get(c3["id"])
    assert c3_fetched["pinned"] is False


def test_assign_and_remove_conversation_from_project(workspace_a):
    """Assigning conversation to project and removing it preserves conversation integrity."""
    store = workspace_a.conversations
    proj = store.create_project(name="Backend Refactor")
    pid = proj["id"]

    conv = store.create(title="Database optimization", project_id=pid)
    assert conv["project_id"] == pid

    # Project metadata reflects conversation
    proj_data = store.get_project(pid)
    assert proj_data["conversation_count"] == 1
    assert proj_data["conversations"][0]["id"] == conv["id"]

    # Filter conversations by project_id
    filtered = store.list(project_id=pid)
    assert len(filtered) == 1
    assert filtered[0]["id"] == conv["id"]

    # Remove from project
    store.assign_to_project(conv["id"], project_id=None)
    updated_conv = store.get(conv["id"])
    assert updated_conv["project_id"] is None

    # Project count decreases
    proj_data_after = store.get_project(pid)
    assert proj_data_after["conversation_count"] == 0


def test_delete_project_preserves_conversations(workspace_a):
    """Deleting a project does NOT delete its conversations; they revert to project_id=None."""
    store = workspace_a.conversations
    proj = store.create_project(name="Temporary Project")
    pid = proj["id"]

    c1 = store.create(title="Task 1", project_id=pid)
    c2 = store.create(title="Task 2", project_id=pid)

    assert store.get_project(pid)["conversation_count"] == 2

    # Delete project
    deleted = store.delete_project(pid)
    assert deleted is True
    assert store.get_project(pid) is None

    # Conversations still exist with project_id = None
    c1_after = store.get(c1["id"])
    c2_after = store.get(c2["id"])
    assert c1_after is not None
    assert c1_after["project_id"] is None
    assert c2_after is not None
    assert c2_after["project_id"] is None


def test_workspace_isolation_projects_and_conversations(workspace_a, workspace_b):
    """Projects and conversations are isolated per workspace."""
    store_a = workspace_a.conversations
    store_b = workspace_b.conversations

    proj_a = store_a.create_project(name="Project in Workspace A")
    conv_a = store_a.create(title="Conv in A", project_id=proj_a["id"])

    # Workspace B has zero projects and zero conversations
    assert len(store_b.list_projects()) == 0
    assert len(store_b.list()) == 0
    assert store_b.get_project(proj_a["id"]) is None

    # Cannot assign a conversation in Workspace B to a project from Workspace A
    with pytest.raises(ValueError, match="does not exist"):
        store_b.create(title="Conv in B", project_id=proj_a["id"])


def test_backward_compatibility_legacy_database_migration(tmp_path):
    """Existing SQLite databases without pinned or project_id columns are migrated automatically."""
    legacy_db = tmp_path / "legacy_convs.db"

    # Create old-style schema without pinned, project_id, unread
    with sqlite3.connect(legacy_db) as conn:
        conn.execute(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                team_name TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_message TEXT,
                agents TEXT DEFAULT '[]'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO conversations (id, title, status, created_at, updated_at, last_message, agents)
            VALUES ('old-1', 'Legacy Task', 'active', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 'Hello', '[]')
            """
        )

    # Initialize ConversationStore on legacy DB -> triggers auto migrations
    store = ConversationStore(legacy_db)

    # Legacy conversation has pinned=False and project_id=None
    conv = store.get("old-1")
    assert conv is not None
    assert conv["title"] == "Legacy Task"
    assert conv["pinned"] is False
    assert conv["project_id"] is None

    # Can now pin and assign projects normally
    proj = store.create_project(name="Migration Project")
    store.assign_to_project("old-1", proj["id"])
    store.pin("old-1", pinned=True)

    updated = store.get("old-1")
    assert updated["pinned"] is True
    assert updated["project_id"] == proj["id"]


@pytest.mark.asyncio
async def test_rest_api_projects_and_conversation_organization(workspace_a):
    """Test full REST API lifecycle for Projects and conversation organization."""
    app.state.workspace = workspace_a
    app.state.team = workspace_a.load_team()
    app.state.session_token = None

    req = Request({"type": "http", "app": app, "headers": [], "path": "/api/projects", "method": "GET"})

    # 1. GET /projects initial empty
    projs = await list_projects(req)
    assert len(projs) == 0

    # 2. POST /projects
    p_created = await create_project(req, CreateProjectPayload(name="API Project"))
    pid = p_created["id"]
    assert p_created["name"] == "API Project"

    # 3. GET /projects/{id}
    p_get = await get_project(req, pid)
    assert p_get["name"] == "API Project"
    assert p_get["conversation_count"] == 0

    # 4. POST /conversations with project_id and pinned
    conv = await create_conversation(
        req,
        CreateConversationPayload(title="API Organized Task", pinned=True, project_id=pid)
    )
    cid = conv["id"]
    assert conv["pinned"] is True
    assert conv["project_id"] == pid

    # 5. GET /projects/{id} reflects new conversation
    p_after_conv = await get_project(req, pid)
    assert p_after_conv["conversation_count"] == 1

    # 6. POST /conversations/{id}/pin toggle
    unpinned_conv = await pin_conversation_endpoint(req, cid, PinConversationPayload(pinned=False))
    assert unpinned_conv["pinned"] is False

    # 7. POST /conversations/{id}/project unassign
    unassigned = await assign_conversation_project(req, cid, AssignProjectPayload(project_id=None))
    assert unassigned["project_id"] is None

    # 8. PATCH /projects/{id} rename
    renamed = await update_project(req, pid, UpdateProjectPayload(name="API Project Renamed"))
    assert renamed["name"] == "API Project Renamed"

    # 9. DELETE /projects/{id}
    del_res = await delete_project(req, pid)
    assert del_res["status"] == "ok"

    # 10. Conversation remains
    surviving_conv = await get_conversation(req, cid)
    assert surviving_conv is not None
    assert surviving_conv["project_id"] is None
