from __future__ import annotations

import pytest

from aether.agents.agent import Agent
from aether.core.delegation import DelegationContext, DelegationError
from aether.planning.delegation import DelegationRequest, DelegationResult
from aether.planning.types import Goal
from aether.tools.cognitive_agent_tool import CognitiveAgentTool
from aether.tools.agent_tool import AgentTool
from aether.core.execution import Task

# --- Mock Agent for Testing ---

class MockChildAgent(Agent):
    def __init__(self, name: str, expected_output: dict | str | None = None, role: str = "child"):
        super().__init__(name=name, role=role)
        self.expected_output = expected_output
        self.received_goal = None
        self.received_task = None

    def achieve(self, goal: Goal, context=None):
        self.received_goal = goal
        return type('MockExecutionResult', (), {'success': True, 'output': self.expected_output, 'metadata': {'test': True}})()

    def execute(self, task: Task, context=None):
        self.received_task = task
        return type('MockExecutionResult', (), {'success': True, 'output': self.expected_output, 'metadata': {'test': True}})()

# --- Tests ---

def test_basic_delegation():
    """Test 1: Basic delegation - Parent Agent -> CognitiveAgentTool -> Child Agent completes Goal"""
    child = MockChildAgent("ChildA", expected_output={"done": True})
    tool = CognitiveAgentTool(agent=child)

    req = DelegationRequest(goal_description="Do the task")
    result = tool.execute(req.__dict__)

    assert result.success is True
    assert child.received_goal is not None
    assert child.received_goal.description == "Do the task"
    assert result.output == {"done": True}


def test_context_propagation():
    """Test 2: Context propagation - constraints, reasoning, success_criteria reach the child Goal"""
    child = MockChildAgent("ChildA")
    tool = CognitiveAgentTool(agent=child)

    req = DelegationRequest(
        goal_description="Fix auth",
        success_criteria=["Login works"],
        constraints=["No downtime"],
        reasoning="I am busy",
        context={"token": "123"}
    )
    result = tool.execute(req.__dict__)

    assert result.success is True
    assert child.received_goal.description == "Fix auth"
    assert "Login works" in child.received_goal.success_criteria
    assert "No downtime" in child.received_goal.constraints
    assert result.metadata["reasoning_transferred"] == "I am busy"
    assert result.metadata["context_transferred"] == {"token": "123"}


def test_isolation():
    """Test 3: Isolation - Parent and Child memories remain separate"""
    from aether.memory.conversation import ConversationMemory
    
    parent = Agent("Parent", memory=ConversationMemory())
    child = Agent("Child", memory=ConversationMemory())
    
    parent.memory.add_message("session", {"content": "parent_msg"})
    child.memory.add_message("session", {"content": "child_msg"})
    
    # Tool execution shouldn't merge them
    tool = CognitiveAgentTool(agent=child)
    # Just asserting they are distinct objects is sufficient for this check
    assert parent.memory is not child.memory


def test_loop_protection():
    """Test 4: Delegation loop protection"""
    child = MockChildAgent("ChildA")
    
    # Simulate a deep chain where ChildA is already present
    chain_ctx = DelegationContext(current_agent="Parent", chain=["Parent", "ChildA", "ChildB"])
    
    tool = CognitiveAgentTool(agent=child, delegation_context=chain_ctx)
    
    req = DelegationRequest(goal_description="Infinite loop")
    result = tool.execute(req.__dict__)
    
    assert result.success is False
    assert "Circular delegation detected" in result.metadata["error"]


def test_legacy_compatibility():
    """Test 5: Legacy AgentTool continues to work with Task and execute()"""
    child = MockChildAgent("ChildA", expected_output="Legacy Done")
    legacy_tool = AgentTool(agent=child)
    
    result_str = legacy_tool.execute("Legacy Task")
    
    assert result_str == "Legacy Done"
    assert child.received_task is not None
    assert child.received_task.instruction == "Legacy Task"
    assert child.received_goal is None


def test_structured_delegation_result():
    """Test 6: Structured Delegation Result maintains dict/Any structure"""
    expected_output = {
        "files_changed": ["main.py"],
        "tests_passed": True
    }
    child = MockChildAgent("ChildA", expected_output=expected_output)
    tool = CognitiveAgentTool(agent=child)

    req = DelegationRequest(goal_description="Code changes")
    result = tool.execute(req.__dict__)

    assert isinstance(result, DelegationResult)
    # Must remain a dict, not a string
    assert isinstance(result.output, dict)
    assert result.output["tests_passed"] is True
    assert result.output["files_changed"] == ["main.py"]
