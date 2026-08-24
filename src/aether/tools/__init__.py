from __future__ import annotations

from aether.tools.base import Tool, ToolExecutionContext
from aether.tools.registry import ToolRegistry
from aether.tools.cognitive_agent_tool import CognitiveAgentTool
from aether.tools.decorator import tool, FunctionTool
from aether.tools.filesystem import create_filesystem_tools
from aether.tools.web_search import (
    create_web_search_tool,
    WebSearchResult,
    BaseWebSearchBackend,
    DuckDuckGoSearchBackend,
    MockWebSearchBackend,
)

__all__ = [
    "Tool",
    "ToolExecutionContext",
    "ToolRegistry",
    "CognitiveAgentTool",
    "tool",
    "FunctionTool",
    "create_filesystem_tools",
    "create_web_search_tool",
    "WebSearchResult",
    "BaseWebSearchBackend",
    "DuckDuckGoSearchBackend",
    "MockWebSearchBackend",
]
