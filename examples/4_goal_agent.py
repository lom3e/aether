import asyncio
from aether import Agent, Goal
from aether.providers import MockProvider

def main():
    # Provide a mock response that simulates a structured plan
    class GoalMockProvider(MockProvider):
        def generate(self, messages, tools=None, output_schema=None):
            from aether.providers import ProviderResponse, Message
            import json
            
            # Simulate a planner JSON response
            mock_plan = {
                "thoughts": "I understand the goal. I should complete it.",
                "action": "finish",
                "arguments": {"final_result": "Goal achieved successfully."}
            }
            
            return ProviderResponse(
                content=json.dumps(mock_plan),
                finish_reason="stop",
                model="mock"
            )

    agent = Agent(name="PlannerBot", provider=GoalMockProvider())
    
    goal = Goal(description="Organize the files in the directory")
    print(f"Goal: {goal.description}")
    
    # Run the achieve loop
    result = agent.achieve(goal)
    
    print(f"Success: {result.success}")
    if result.output:
        print(f"Result: {result.output}")
    if result.error:
        print(f"Error: {result.error}")

if __name__ == "__main__":
    main()
