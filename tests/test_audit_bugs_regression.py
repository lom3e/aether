"""
Regression tests for the 3 confirmed functional audit bugs:
1. Bug 1: Knowledge multipart upload parses real HTTP multipart form data (request.form()).
2. Bug 2: Conversation team assignment can be updated, persisted in SQLite, and loaded in sockets.
3. Bug 3: FunctionTool.execute accepts Python dictionary arguments directly without requiring a JSON string.
"""
from pathlib import Path
import pytest
from starlette.requests import Request

from aether.workspace.workspace import Workspace
from aether.presets.applier import PresetApplier
from aether.server.app import app
from aether.server.routes import upload_knowledge, update_conversation, UpdateConversationPayload
from aether.tools.decorator import tool


# ---------------------------------------------------------------------------
# BUG 1 REGRESSION: Knowledge multipart upload via real HTTP multipart request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bug1_knowledge_multipart_upload_real_http_stream(tmp_path: Path):
    """Real HTTP multipart/form-data request to /api/knowledge/upload extracts files and ingests them."""
    ws = Workspace.get_or_init(tmp_path, "Bug 1 Test Workspace")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)
    app.state.workspace = ws
    app.state.team = ws.load_team()
    app.state.active_team_name = None

    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="scope"\r\n\r\n'
        "workspace\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="playbook.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "Incident response playbook: When server goes down, restart system service.\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    async def receive():
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/knowledge/upload",
        "headers": [
            (b"content-type", f"multipart/form-data; boundary={boundary}".encode("latin1")),
            (b"content-length", str(len(body)).encode("latin1")),
        ],
        "app": app,
    }

    req = Request(scope, receive=receive)

    # Calling upload_knowledge without passing files parameter (as FastAPI does for real HTTP requests)
    res = await upload_knowledge(request=req)

    assert res["status"] in ("ok", "partial")
    assert res["total"] == 1
    assert res["succeeded"] == 1
    assert len(res["documents"]) == 1
    assert res["documents"][0]["filename"] == "playbook.txt"

    # Verify document exists in KnowledgeStore
    docs = app.state.team.knowledge.list_documents()
    assert any(d["filename"] == "playbook.txt" for d in docs)
    found_doc = next(d for d in docs if d["filename"] == "playbook.txt")
    chunks = app.state.team.knowledge.get_by_source(found_doc["id"])
    assert len(chunks) > 0
    assert "Incident response playbook" in chunks[0].content


# ---------------------------------------------------------------------------
# BUG 2 REGRESSION: Conversation team assignment updated, persisted & used
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bug2_conversation_team_assignment_update_and_persistence(tmp_path: Path):
    """PATCH /api/conversations/{id} updates and persists team_name, and sockets loads the assigned team."""
    ws = Workspace.get_or_init(tmp_path, "Bug 2 Test Workspace")
    PresetApplier().apply_preset("starter-workforce", ws, set_as_default=True)
    # Also create a second team yaml in teams_dir
    team_b_yaml = """team:
  name: "Operations Team"
  provider: "openai"
  model: "gpt-4o"
agents:
  - name: "ops_lead"
    role: "Operations Lead"
    instructions: "Handle ops."
"""
    (ws.teams_dir / "Operations Team.yaml").write_text(team_b_yaml)

    app.state.workspace = ws
    app.state.team = ws.load_team()
    app.state.active_team_name = "default"

    # 1. Create a conversation
    conv = ws.conversations.create(title="Deploy Release", team_name=None)
    conv_id = conv["id"]
    assert conv.get("team_name") is None

    # 2. Update conversation team via update_conversation route
    req = Request({"type": "http", "app": app})
    update_payload = UpdateConversationPayload(team_name="Operations Team")
    updated = await update_conversation(request=req, conv_id=conv_id, data=update_payload)

    assert updated["team_name"] == "Operations Team"

    # 3. Retrieve from SQLite store directly to verify persistence
    persisted = ws.conversations.get(conv_id)
    assert persisted["team_name"] == "Operations Team"

    # 4. Verify conversation listing contains the updated team_name
    all_convs = ws.conversations.list()
    matching = next((c for c in all_convs if c["id"] == conv_id), None)
    assert matching is not None
    assert matching["team_name"] == "Operations Team"

    # 5. Verify sockets team resolution prefers conv["team_name"]
    conv_resolved = ws.conversations.get(conv_id)
    assert conv_resolved["team_name"] == "Operations Team"
    loaded_team = ws.load_team(conv_resolved["team_name"])
    assert loaded_team.config.name == "Operations Team"
    assert any(a.name == "ops_lead" for a in loaded_team.agents())


# ---------------------------------------------------------------------------
# BUG 3 REGRESSION: FunctionTool.execute accepts Python dict arguments
# ---------------------------------------------------------------------------

def test_bug3_function_tool_execute_with_dict_and_json():
    """FunctionTool.execute accepts Python dictionary without TypeError."""
    @tool
    def calculate_metrics(alpha: int, beta: int, factor: float = 1.0) -> float:
        """Calculate score from metrics."""
        return (alpha + beta) * factor

    # 1. Execute with Python dictionary
    dict_result = calculate_metrics.execute({"alpha": 10, "beta": 20, "factor": 2.5})
    assert dict_result == "75.0"

    # 2. Execute with JSON string (backward compatibility)
    json_result = calculate_metrics.execute('{"alpha": 10, "beta": 20, "factor": 2.5}')
    assert json_result == "75.0"

    # 3. Execute with dictionary without optional argument
    dict_default_result = calculate_metrics.execute({"alpha": 5, "beta": 15})
    assert dict_default_result == "20.0"
