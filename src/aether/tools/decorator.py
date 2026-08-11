"""
@tool decorator for Aether.

Allows defining agent tools from plain Python functions using type hints,
without manual JSON Schema boilerplate.

Usage::

    from aether import tool

    @tool(description="Search the web for information")
    def web_search(query: str, max_results: int = 5) -> str:
        return search(query, max_results)

    # The decorated function becomes a Tool instance:
    agent.tool_registry.register(web_search)

Tools that require human approval can raise AgentInterrupt directly::

    from aether.core.interrupts import RequireApproval

    @tool(description="Send an email")
    def send_email(to: str, subject: str, body: str) -> str:
        raise RequireApproval(f"Send email to {to}?", context={"to": to})
"""
from __future__ import annotations

import inspect
import json
from typing import Any, Callable, get_type_hints

from aether.tools.base import Tool, ToolExecutionContext

# ---------------------------------------------------------------------------
# Type mapping — Python annotations → JSON Schema types
# ---------------------------------------------------------------------------

_PY_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _py_type_to_json(annotation: Any) -> str:
    """Convert a Python type annotation to a JSON Schema type string."""
    # Handle Optional[X] → unwrap to X (NoneType partner)
    origin = getattr(annotation, "__origin__", None)
    if origin is type(None):
        return "string"

    # typing.Union / Optional
    if origin is not None:
        args = getattr(annotation, "__args__", ())
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _py_type_to_json(non_none[0])

    return _PY_TO_JSON.get(annotation, "string")


# ---------------------------------------------------------------------------
# Schema builder
# ---------------------------------------------------------------------------

def _build_schema(func: Callable, tool_name: str, tool_description: str) -> dict[str, Any]:
    """Build a JSON Schema dict from a function signature + type hints."""
    sig = inspect.signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        # Skip 'context' — it's the ToolExecutionContext injected by the runtime
        if param_name in ("context", "self"):
            continue

        annotation = hints.get(param_name, str)
        json_type = _py_type_to_json(annotation)

        param_schema: dict[str, Any] = {"type": json_type}

        # Inject description from docstring parameter section if present
        # (basic support — no sphinx/numpy/google parsing needed for MVP)

        properties[param_name] = param_schema

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# ---------------------------------------------------------------------------
# FunctionTool — internal wrapper class
# ---------------------------------------------------------------------------

class FunctionTool(Tool):
    """
    A Tool constructed from a plain Python function via the @tool decorator.

    Not intended to be instantiated directly — use @tool instead.
    """

    def __init__(
        self,
        func: Callable,
        tool_name: str,
        tool_description: str,
        schema: dict[str, Any],
    ) -> None:
        self.name = tool_name
        self.description = tool_description
        self._func = func
        self._schema = schema
        # Preserve original function metadata
        self.__doc__ = func.__doc__
        self.__module__ = getattr(func, "__module__", None)
        self.__qualname__ = getattr(func, "__qualname__", tool_name)

    def to_json_schema(self) -> dict[str, Any]:
        return self._schema

    def execute(
        self,
        input_data: str,
        context: ToolExecutionContext | None = None,
    ) -> str:
        """
        Execute the wrapped function.

        ``input_data`` is expected to be a JSON string mapping parameter
        names to values (the format used by the LLM tool-call convention).
        Falls back to passing ``input_data`` as the sole argument if the
        function accepts only one parameter and parsing fails.
        """
        sig = inspect.signature(self._func)
        params = [
            p for p in sig.parameters
            if p not in ("context", "self")
        ]

        # Try to parse input_data as JSON dict first
        try:
            kwargs: dict[str, Any] = json.loads(input_data)
        except (json.JSONDecodeError, TypeError):
            kwargs = {}

        # If the function has a single param and we got an empty dict,
        # pass input_data as the positional argument
        if not kwargs and len(params) == 1:
            kwargs = {params[0]: input_data}

        # Inject context if the function declares it
        if "context" in sig.parameters:
            kwargs["context"] = context

        result = self._func(**kwargs)
        return str(result) if result is not None else ""

    def __repr__(self) -> str:
        return f"FunctionTool(name={self.name!r})"


# ---------------------------------------------------------------------------
# Public decorator
# ---------------------------------------------------------------------------

def tool(
    func: Callable | None = None,
    *,
    description: str = "",
    name: str = "",
) -> FunctionTool | Callable[[Callable], FunctionTool]:
    """
    Decorator that transforms a plain Python function into an Aether :class:`Tool`.

    Can be used with or without arguments::

        @tool
        def my_tool(x: int) -> str: ...

        @tool(description="My tool", name="custom_name")
        def my_tool(x: int) -> str: ...

    Parameters
    ----------
    func:
        The function to wrap (when used without parentheses).
    description:
        Human-readable description of what the tool does.
        Falls back to the function's docstring if not provided.
    name:
        Override the tool name. Defaults to ``func.__name__``.

    Returns
    -------
    FunctionTool
        A :class:`Tool`-compatible instance ready to register in a
        :class:`~aether.tools.registry.ToolRegistry`.
    """
    def _make(f: Callable) -> FunctionTool:
        tool_name = name or f.__name__
        tool_description = description or (inspect.getdoc(f) or "")
        schema = _build_schema(f, tool_name, tool_description)
        return FunctionTool(f, tool_name, tool_description, schema)

    # @tool  (no parentheses)
    if func is not None:
        return _make(func)

    # @tool(...)  (with parentheses)
    return _make
