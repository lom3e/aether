"""
Tests for Workforce activity persistence and conversation unread state.
"""
from aether.workspace.workspace import Workspace


def test_workforce_activity_persistence(tmp_path):
    ws_dir = tmp_path / "activity-ws"
    ws = Workspace.init(ws_dir, name="Activity Test Workspace")

    conv = ws.conversations.create(title="Product Strategy", conv_id="conv_act_123")
    assert conv["id"] == "conv_act_123"

    # Add user message
    ws.conversations.add_message(conv_id="conv_act_123", role="user", content="Research competitors")

    # Add activity events
    act1 = ws.conversations.add_activity(
        conv_id="conv_act_123",
        agent="research-manager",
        activity_type="agent_started",
        message="Planning work",
        metadata={"instruction": "Research market trends"}
    )
    assert act1["agent"] == "research-manager"

    act2 = ws.conversations.add_activity(
        conv_id="conv_act_123",
        agent="researcher",
        activity_type="tool_called",
        message="Searching knowledge base",
        metadata={"tool_name": "search_knowledge", "query": "competitor analysis"}
    )
    assert act2["agent"] == "researcher"

    act3 = ws.conversations.add_activity(
        conv_id="conv_act_123",
        agent="researcher",
        activity_type="tool_completed",
        message="Found 5 documents",
        metadata={"tool_name": "search_knowledge"}
    )

    # Reopen conversation and verify activities are persisted
    reopened = ws.conversations.get("conv_act_123")
    assert reopened is not None
    assert "activities" in reopened
    assert len(reopened["activities"]) == 3
    assert reopened["activities"][0]["agent"] == "research-manager"
    assert reopened["activities"][1]["metadata"]["tool_name"] == "search_knowledge"
    assert reopened["activities"][2]["type"] == "tool_completed"


def test_unread_state_lifecycle(tmp_path):
    ws_dir = tmp_path / "unread-ws"
    ws = Workspace.init(ws_dir, name="Unread Test Workspace")

    conv = ws.conversations.create(title="Market Overview", conv_id="conv_unread_123")
    assert conv["unread"] is False

    # User message keeps unread = False
    ws.conversations.add_message(conv_id="conv_unread_123", role="user", content="Hello")
    assert ws.conversations.get("conv_unread_123")["unread"] is False

    # Assistant message marks unread = True
    ws.conversations.add_message(conv_id="conv_unread_123", role="assistant", content="Here is the report.")
    c_after_bot = ws.conversations.get("conv_unread_123")
    assert c_after_bot["unread"] is True

    # List also reports unread = True
    conv_list = ws.conversations.list()
    assert len(conv_list) == 1
    assert conv_list[0]["unread"] is True

    # When user opens/reads conversation -> mark_read
    ws.conversations.mark_read("conv_unread_123")
    c_after_read = ws.conversations.get("conv_unread_123")
    assert c_after_read["unread"] is False
