from aether.core.execution import Message, ToolCall, ToolResult


def test_tool_call_and_result_dataclasses() -> None:
    call = ToolCall(
        call_id="call_123",
        tool_name="Calculator",
        arguments={"expression": "2 + 2"},
    )
    assert call.call_id == "call_123"
    assert call.tool_name == "Calculator"
    assert call.arguments == {"expression": "2 + 2"}

    res = ToolResult(
        call_id="call_123",
        output="4",
        success=True,
    )
    assert res.call_id == "call_123"
    assert res.output == "4"
    assert res.error is None
    assert res.success is True


def test_message_to_dict_with_tool_calls() -> None:
    call = ToolCall(
        call_id="call_123",
        tool_name="Calculator",
        arguments={"expression": "2 + 2"},
    )
    msg = Message(
        role="assistant",
        content="Thinking...",
        tool_calls=[call],
    )
    d = msg.to_dict()
    assert d["role"] == "assistant"
    assert d["content"] == "Thinking..."
    assert "tool_calls" in d
    assert len(d["tool_calls"]) == 1
    assert d["tool_calls"][0]["id"] == "call_123"
    assert d["tool_calls"][0]["type"] == "function"
    assert d["tool_calls"][0]["function"]["name"] == "Calculator"
    assert "2 + 2" in d["tool_calls"][0]["function"]["arguments"]


def test_message_to_dict_with_tool_call_id() -> None:
    msg = Message(
        role="tool",
        content="4",
        tool_call_id="call_123",
    )
    d = msg.to_dict()
    assert d["role"] == "tool"
    assert d["content"] == "4"
    assert d["tool_call_id"] == "call_123"
