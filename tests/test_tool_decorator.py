"""Tests for the @tool decorator (aether.tools.decorator)."""
from __future__ import annotations

import json
from typing import Optional

import pytest

from aether import tool
from aether.tools.base import Tool, ToolExecutionContext
from aether.tools.decorator import FunctionTool, _build_schema
from aether.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Basic decorator usage
# ---------------------------------------------------------------------------

class TestToolDecoratorBasic:
    def test_returns_function_tool_instance(self):
        @tool
        def my_tool(query: str) -> str:
            return f"result: {query}"

        assert isinstance(my_tool, FunctionTool)
        assert isinstance(my_tool, Tool)

    def test_default_name_from_function(self):
        @tool
        def search_web(query: str) -> str:
            return "result"

        assert search_web.name == "search_web"

    def test_name_from_decorator_arg(self):
        @tool(name="custom_name")
        def my_fn(q: str) -> str:
            return q

        assert my_fn.name == "custom_name"

    def test_description_from_decorator_arg(self):
        @tool(description="Search the web")
        def search(query: str) -> str:
            return query

        assert search.description == "Search the web"

    def test_description_falls_back_to_docstring(self):
        @tool
        def greet(name: str) -> str:
            """Say hello to someone."""
            return f"Hello {name}"

        assert greet.description == "Say hello to someone."

    def test_empty_description_when_no_docstring(self):
        @tool
        def no_doc(x: str) -> str:
            return x

        assert no_doc.description == ""

    def test_with_parentheses_no_args(self):
        @tool()
        def fn(x: str) -> str:
            return x

        assert isinstance(fn, FunctionTool)


# ---------------------------------------------------------------------------
# JSON Schema generation
# ---------------------------------------------------------------------------

class TestSchemaGeneration:
    def test_single_string_param(self):
        @tool(description="A tool")
        def fn(query: str) -> str:
            return query

        schema = fn.to_json_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "fn"
        assert schema["function"]["description"] == "A tool"
        props = schema["function"]["parameters"]["properties"]
        assert "query" in props
        assert props["query"]["type"] == "string"
        assert schema["function"]["parameters"]["required"] == ["query"]

    def test_multiple_typed_params(self):
        @tool
        def calculate(a: int, b: float, label: str) -> str:
            return str(a + b)

        props = calculate.to_json_schema()["function"]["parameters"]["properties"]
        assert props["a"]["type"] == "integer"
        assert props["b"]["type"] == "number"
        assert props["label"]["type"] == "string"

    def test_optional_param_not_in_required(self):
        @tool
        def fn(required: str, optional: int = 5) -> str:
            return required

        schema = fn.to_json_schema()["function"]["parameters"]
        assert "required" in schema["required"]
        assert "optional" not in schema["required"]

    def test_bool_param_type(self):
        @tool
        def flag_tool(enabled: bool) -> str:
            return str(enabled)

        props = flag_tool.to_json_schema()["function"]["parameters"]["properties"]
        assert props["enabled"]["type"] == "boolean"

    def test_context_param_excluded_from_schema(self):
        """The 'context' parameter is injected by the runtime and must not appear in schema."""
        @tool
        def with_context(query: str, context: ToolExecutionContext | None = None) -> str:
            return query

        props = with_context.to_json_schema()["function"]["parameters"]["properties"]
        assert "query" in props
        assert "context" not in props

    def test_no_params_tool(self):
        @tool(description="No params")
        def ping() -> str:
            return "pong"

        schema = ping.to_json_schema()["function"]["parameters"]
        assert schema["properties"] == {}
        assert schema["required"] == []

    def test_unknown_type_falls_back_to_string(self):
        from dataclasses import dataclass

        @dataclass
        class Custom:
            value: int

        @tool
        def custom_type_tool(obj: Custom) -> str:
            return str(obj)

        props = custom_type_tool.to_json_schema()["function"]["parameters"]["properties"]
        assert props["obj"]["type"] == "string"


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class TestFunctionToolExecution:
    def test_execute_with_json_string(self):
        @tool
        def add(a: int, b: int) -> str:
            return str(a + b)

        result = add.execute(json.dumps({"a": 3, "b": 4}))
        assert result == "7"

    def test_execute_single_param_fallback(self):
        """When input_data is not valid JSON and fn has 1 param, use raw input_data."""
        @tool
        def echo(message: str) -> str:
            return message

        result = echo.execute("hello world")
        assert result == "hello world"

    def test_execute_returns_string(self):
        @tool
        def get_number() -> str:
            return "42"

        result = get_number.execute("{}")
        assert isinstance(result, str)

    def test_execute_none_return_becomes_empty_string(self):
        @tool
        def noop(x: str) -> None:
            pass  # returns None implicitly

        result = noop.execute(json.dumps({"x": "test"}))
        assert result == ""

    def test_execute_with_context_injected(self):
        received_context = []

        @tool
        def ctx_tool(query: str, context: ToolExecutionContext | None = None) -> str:
            received_context.append(context)
            return query

        ctx = ToolExecutionContext(agent_name="test-agent")
        result = ctx_tool.execute(json.dumps({"query": "hello"}), context=ctx)
        assert result == "hello"
        assert received_context[0] is ctx

    def test_execute_interrupt_propagates(self):
        from aether.core.interrupts import RequireApproval

        @tool(description="Dangerous action")
        def dangerous(target: str) -> str:
            raise RequireApproval(f"Are you sure about {target}?")

        with pytest.raises(RequireApproval):
            dangerous.execute(json.dumps({"target": "important-file"}))


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestToolRegistryIntegration:
    def test_register_and_retrieve(self):
        @tool(description="A registered tool")
        def my_tool(x: str) -> str:
            return x

        registry = ToolRegistry()
        registry.register(my_tool)

        retrieved = registry.get("my_tool")
        assert retrieved is my_tool

    def test_execute_via_registry(self):
        @tool
        def upper(text: str) -> str:
            return text.upper()

        registry = ToolRegistry()
        registry.register(upper)

        result = registry.execute("upper", json.dumps({"text": "hello"}))
        assert result == "HELLO"

    def test_schema_available_via_registry(self):
        @tool(description="Greet")
        def greet(name: str) -> str:
            return f"Hello {name}"

        registry = ToolRegistry()
        registry.register(greet)

        schema = registry.get("greet").to_json_schema()
        assert schema["function"]["name"] == "greet"


# ---------------------------------------------------------------------------
# Repr
# ---------------------------------------------------------------------------

class TestFunctionToolRepr:
    def test_repr(self):
        @tool
        def my_tool(x: str) -> str:
            return x

        assert "my_tool" in repr(my_tool)
