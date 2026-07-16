from __future__ import annotations

from dataclasses import dataclass, field

from aether.tools.base import Tool, ToolExecutionContext


@dataclass(slots=True)
class ToolRegistry:
    """
    Minimal registry for tool lookup and execution.
    """

    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")

        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Tool '{name}' is not registered.") from exc

    def execute(
        self,
        name: str,
        input_data: str,
        context: ToolExecutionContext | None = None,
    ) -> str:
        return self.get(name).execute(input_data, context)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())
