
from aether import Agent, Task
from aether.providers import MockProvider

def main():
    # 1. Create a provider (we use MockProvider for demonstration)
    provider = MockProvider()
    
    # 2. Create the Agent
    agent = Agent(name="Assistant", provider=provider)
    
    # 3. Create a Task
    task = Task(instruction="Hello, can you help me?")
    
    # 4. Execute the task
    print(f"Executing task: {task.instruction}")
    result = agent.execute(task)
    
    if result.success:
        print(f"Agent response: {result.output}")
    else:
        print(f"Execution failed: {result.error}")

if __name__ == "__main__":
    main()
