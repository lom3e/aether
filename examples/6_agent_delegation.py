import json
from aether import Agent, Task
from aether.tools import CognitiveAgentTool
from aether.providers import MockProvider

def main():

    # Mock Provider for Parent that decides to delegate
    class ParentMock(MockProvider):
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
                            tool_name=child_agent.name,
                            arguments={"goal_description": "What is the capital of France?"}
                        )]
                    )
                )
            
            return ProviderResponse(
                content="The researcher found the answer: " + messages[-1].content,
                finish_reason="stop",
                model="mock"
            )
            
    # Mock Provider for Child that solves the delegated goal
    class ChildMock(MockProvider):
        def generate(self, messages, tools=None, output_schema=None):
            from aether.providers import ProviderResponse, Message
            
            # For achieve(), it expects structured plans
            mock_plan = {
                "thoughts": "I will answer the question",
                "action": "finish",
                "arguments": {"final_result": "The capital of France is Paris."}
            }
            return ProviderResponse(
                content=json.dumps(mock_plan),
                finish_reason="stop",
                model="mock"
            )

    # 1. Create Child Agent
    child_agent = Agent(name="Researcher", provider=ChildMock())
    
    # 2. Create Parent Agent
    parent_agent = Agent(name="Manager", provider=ParentMock())
    
    # 3. Connect them using CognitiveAgentTool
    delegation_tool = CognitiveAgentTool(agent=child_agent)
    parent_agent.tools.append(delegation_tool.name)
    parent_agent.tool_registry.register(delegation_tool)
    
    # 4. Execute Parent
    task = Task(instruction="Ask the researcher what the capital of France is.")
    print(f"Parent Task: {task.instruction}")
    
    result = parent_agent.execute(task)
    if result.success:
        print(f"Parent Result: {result.output}")
    else:
        print(f"Parent Failed: {result.error}")

if __name__ == "__main__":
    main()
