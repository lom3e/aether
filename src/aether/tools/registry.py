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

    @staticmethod
    def _normalize(name: str) -> str:
        return name.lower().replace(" ", "_").replace("-", "_").strip()

    def get(self, name: str) -> Tool:
        # 1. Exact match
        if name in self._tools:
            return self._tools[name]

        target_norm = self._normalize(name)
        target_norm_no_prefix = target_norm.removeprefix("delegate_to_")

        # 2. Normalized equality and function_name check
        for k, tool in self._tools.items():
            k_norm = self._normalize(k)
            k_norm_no_prefix = k_norm.removeprefix("delegate_to_")
            fn_name = getattr(tool, "function_name", None)
            fn_norm = self._normalize(fn_name) if fn_name else None

            if k_norm == target_norm:
                return tool
            if fn_norm and fn_norm == target_norm:
                return tool
            if k_norm_no_prefix == target_norm_no_prefix:
                return tool

        raise KeyError(f"Tool '{name}' is not registered.")

    def execute(
        self,
        name: str,
        input_data: str,
        context: ToolExecutionContext | None = None,
    ) -> str:
        return self.get(name).execute(input_data, context)

    def has(self, name: str) -> bool:
        if name in self._tools:
            return True
        try:
            self.get(name)
            return True
        except KeyError:
            return False

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    list = list_tools
