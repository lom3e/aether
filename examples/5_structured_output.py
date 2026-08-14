import json
from aether import Agent, Task
from aether.tools import Tool, ToolExecutionContext
from aether.providers import MockProvider

class DataExtractorTool(Tool):
    """Tool that returns structured dictionary data, demonstrating type preservation."""

    @property
    def name(self) -> str:
        return "extract_data"

    @property
    def description(self) -> str:
        return "Extract structured data"

    def to_json_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }

    def execute(self, arguments: str, context: ToolExecutionContext) -> dict:
        # Returning a dictionary, not a string
        return {
            "users": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ],
            "count": 2
        }

def main():
    class StructuredMock(MockProvider):
        def generate(self, messages, tools=None, output_schema=None):
            from aether.providers import ProviderResponse, Message
            import uuid

            from aether.core.execution import ToolCall
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
                            tool_name="extract_data",
                            arguments={"raw_text": "Sample data string"}
                        )]
                    )
                )

            # Print what the agent received back to verify it's structural
            last_msg = messages[-1].content
            return ProviderResponse(
                content=f"Observation received:\n{last_msg}",
                finish_reason="stop",
                model="mock"
            )

    agent = Agent(name="DataBot", provider=StructuredMock())
    agent.tools.append("extract_data")
    agent.tool_registry.register(DataExtractorTool())

    result = agent.execute(Task(instruction="Extract the data."))
    if result.success:
        print(result.output)
    else:
        print(f"Failed: {result.error}")

if __name__ == "__main__":
    main()
