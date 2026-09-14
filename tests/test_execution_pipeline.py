from aether.agents.agent import Agent
from aether.core.execution import ExecutionMode, ExecutionResult, ExecutionStatus, Task
from aether.core.runtime import Runtime
from aether.providers.base import AIProvider
from aether.providers.mock import MockProvider


class FailingProvider(AIProvider):
    @property
    def capabilities(self):
        from aether.providers.capabilities import ProviderCapabilities
        return ProviderCapabilities()

    def generate(self, messages, tools=None, output_schema=None):
        raise RuntimeError("provider failed")



def test_task_and_result_models_can_be_created():
    task = Task(agent_name="Assistant Agent", instruction="Hello Aether")
    result = ExecutionResult(success=True, output="ok", metadata={"source": "test"})

    assert task.agent_name == "Assistant Agent"
    assert task.instruction == "Hello Aether"
    assert task.id
    assert result.success is True
    assert result.output == "ok"
    assert result.error is None
    assert result.metadata == {"source": "test"}


def test_runtime_executes_task_through_agent_and_provider():
    runtime = Runtime()
    agent = Agent(name="Assistant Agent", provider=MockProvider())
    runtime.register_agent(agent)

    result = runtime.execute(Task(agent_name="Assistant Agent", instruction="Hello Aether"))

    assert result.success is True
    assert result.output == "Mock response: Hello Aether"
    assert result.metadata["agent_name"] == "Assistant Agent"
    assert result.metadata["task_id"]


def test_runtime_returns_failure_for_missing_agent():
    runtime = Runtime()

    result = runtime.execute(Task(agent_name="Unknown Agent", instruction="Hello Aether"))

    assert result.success is False
    assert "not registered" in result.error
    assert result.metadata["agent_name"] == "Unknown Agent"


def test_runtime_returns_failure_when_provider_raises():
    runtime = Runtime()
    agent = Agent(name="Assistant Agent", provider=FailingProvider())
    runtime.register_agent(agent)

    result = runtime.execute(Task(agent_name="Assistant Agent", instruction="Hello Aether"))

    assert result.success is False
    assert result.error == "provider failed"
    assert result.metadata["agent_name"] == "Assistant Agent"


def test_runtime_execute_answer_mode_with_provider():
    provider = MockProvider()
    runtime = Runtime(provider=provider)
    task = Task(instruction="What is Aether?", mode=ExecutionMode.ANSWER)
    result = runtime.execute(task)

    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert "Mock response" in result.output


def test_runtime_execute_answer_mode_diagnostic_fallback():
    runtime = Runtime()  # No provider configured
    task = Task(instruction="Chi sei?", mode=ExecutionMode.ANSWER, workspace_id="test_ws")
    result = runtime.execute(task)

    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert "Aether" in result.output
    assert "test_ws" in result.output


def test_runtime_execute_do_mode(tmp_path):
    from aether.actions.registry import ActionRegistry
    from aether.actions.store import ActionStore
    from aether.actions.executor import ActionExecutor
    from aether.activity.service import ActivityService
    from aether.activity.store import ActivityStore

    act_store = ActionStore(f"sqlite:///{tmp_path}/actions.db")
    activity_svc = ActivityService(ActivityStore(f"sqlite:///{tmp_path}/activity.db"))
    executor = ActionExecutor(
        registry=ActionRegistry(),
        store=act_store,
        activity_service=activity_svc,
        project_path=tmp_path,
    )
    runtime = Runtime(action_executor=executor)

    task = Task(
        instruction="Create a note",
        mode=ExecutionMode.DO,
        action_id="files.create_document",
        action_args={"filename": "note.txt", "content": "Hello Aether runtime"},
        workspace_id="test_ws",
    )
    result = runtime.execute(task)

    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert (tmp_path / "note.txt").exists()
    assert (tmp_path / "note.txt").read_text() == "Hello Aether runtime"
    assert len(result.deliverables) == 1
    assert result.deliverables[0]["name"] == "note.txt"


def test_runtime_execute_act_mode_requires_approval(tmp_path):
    from aether.actions.registry import ActionRegistry
    from aether.actions.store import ActionStore
    from aether.actions.executor import ActionExecutor

    act_store = ActionStore(f"sqlite:///{tmp_path}/actions.db")
    executor = ActionExecutor(
        registry=ActionRegistry(),
        store=act_store,
        project_path=tmp_path,
    )
    runtime = Runtime(action_executor=executor)

    task = Task(
        instruction="Schedule a meeting",
        mode=ExecutionMode.ACT,
        action_id="calendar.create_event",
        action_args={"title": "Team Sync", "start_time": "2026-10-01T10:00:00Z"},
        workspace_id="test_ws",
    )
    result = runtime.execute(task)

    assert result.success is True
    assert result.status == ExecutionStatus.WAITING_FOR_APPROVAL
    assert result.execution_id is not None
    assert "confirm or decline" in result.output


def test_runtime_execute_tool_mode():
    from aether.tools.registry import ToolRegistry
    from aether.tools.base import Tool

    class PingTool(Tool):
        name = "ping"
        description = "Pings"
        def execute(self, arguments, context):
            return "pong: " + arguments.get("msg", "")

    registry = ToolRegistry()
    registry.register(PingTool())
    runtime = Runtime(tool_registry=registry)

    task = Task(
        instruction="Ping",
        mode=ExecutionMode.TOOL,
        action_id="ping",
        action_args={"msg": "hello"},
    )
    result = runtime.execute(task)

    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert result.output == "pong: hello"


def test_resolve_provider_precedence(monkeypatch):
    from aether.providers.resolution import resolve_provider
    from aether.team.config import AgentConfig, TeamConfig
    from aether.providers.manager import ProviderManager

    mgr = ProviderManager()
    mgr.register("openai", MockProvider)
    mgr.register("anthropic", MockProvider)

    # 1. Direct explicit provider
    explicit = MockProvider()
    assert resolve_provider(explicit_provider=explicit) is explicit

    # 2. Agent config override
    agent_cfg = AgentConfig(name="researcher", provider="anthropic", model="claude-3")
    res = resolve_provider(agent_config=agent_cfg, provider_manager=mgr)
    assert res is not None
    assert res.config.model == "claude-3"

    # 3. Inherited Team config
    team_cfg = TeamConfig(default_provider="openai", default_model="gpt-4o")
    res = resolve_provider(team_config=team_cfg, provider_manager=mgr)
    assert res is not None
    assert res.config.model == "gpt-4o"

    # 4. Global environment variable fallback
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-12345")
    res = resolve_provider(provider_manager=mgr)
    assert res is not None
