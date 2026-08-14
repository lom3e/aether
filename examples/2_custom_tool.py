import json
from aether import Agent, Task
from aether.tools import Tool, ToolExecutionContext
from aether.providers import MockProvider

class WeatherTool(Tool):
    """A custom tool to get the current weather."""

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "Get the current weather for a specific city."

    def to_json_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "The city to get weather for"}
                    },
                    "required": ["city"]
                }
            }
        }

    def execute(self, arguments: str, context: ToolExecutionContext) -> str:
        try:
            args = json.loads(arguments)
            city = args.get("city", "Unknown")
            return f"The weather in {city} is sunny and 22°C."
        except Exception as e:
            return f"Error: {e}"

def main():
    # We use a custom MockProvider that pretends to call our tool
    class ToolCallerMock(MockProvider):
        def generate(self, messages, tools=None, output_schema=None):
            from aether.providers import ProviderResponse, Message
            import uuid

            from aether.core.execution import ToolCall

            # If it's the first turn, return a tool call
            if len(messages) < 3:
                return ProviderResponse(
                    content="",
                    finish_reason="tool_calls",
                    model="mock",
                    message=Message(
                        role="assistant",
                        content="",
                        tool_calls=[ToolCall(
                            call_id=f"call_{uuid.uuid4().hex[:8]}",
                            tool_name="get_weather",
                            arguments={"city": "Rome"}
                        )]
                    )
                )
            # Second turn, return final answer based on the tool result
            return ProviderResponse(
                content="The weather in Rome is sunny and 22°C.",
                finish_reason="stop",
                model="mock"
            )

    provider = ToolCallerMock()

    agent = Agent(name="WeatherBot", provider=provider)
    # Register the tool
    agent.tools.append("get_weather")
    # Add to execution engine registry
    agent.tool_registry.register(WeatherTool())

    task = Task(instruction="What is the weather in Rome?")
    print(f"Task: {task.instruction}")

    result = agent.execute(task)
    if result.success:
        print(f"Result: {result.output}")
    else:
        print(f"Failed: {result.error}")

if __name__ == "__main__":
    main()
