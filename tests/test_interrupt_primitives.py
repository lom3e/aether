import pytest
from aether.core.interrupts import AgentInterrupt, RequireApproval, RequireInput

def test_base_interrupt():
    interrupt = AgentInterrupt("Test interrupt", context={"foo": "bar"})
    assert interrupt.id is not None
    assert isinstance(interrupt.id, str)
    assert interrupt.message == "Test interrupt"
    assert interrupt.context == {"foo": "bar"}
    assert interrupt.type == "AgentInterrupt"

def test_require_approval():
    interrupt = RequireApproval("Needs approval")
    assert interrupt.type == "RequireApproval"
    assert interrupt.message == "Needs approval"

def test_require_input():
    interrupt = RequireInput("Needs input", key="api_key", context={"reason": "auth"})
    assert interrupt.type == "RequireInput"
    assert interrupt.message == "Needs input"
    assert interrupt.key == "api_key"
    assert interrupt.context["input_key"] == "api_key"
    assert interrupt.context["reason"] == "auth"
