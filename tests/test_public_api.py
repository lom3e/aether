def test_public_api_exports():
    """Verify that public API symbols can be imported directly."""
    from aether import Agent, Goal, Task, Observation, AetherError
    from aether.tools import Tool, ToolRegistry, CognitiveAgentTool
    from aether.engine import ExecutionEngine, ExecutionResult
    from aether.providers import AIProvider, OllamaProvider, ResilientProvider
    from aether.errors import PlanningError, ExecutionError, ProviderError, RuntimeSafetyError
    
    assert Agent is not None
    assert Goal is not None
    assert Tool is not None
    assert ExecutionEngine is not None
    assert AIProvider is not None
    assert AetherError is not None
