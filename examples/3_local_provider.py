import os
from aether import Agent, Task
from aether.providers import OllamaProvider

def main():
    # Example using Ollama (assuming you have ollama running locally with the llama3 model)
    # Since this is an example, we use a try-except to handle cases where Ollama is not running.
    from aether.providers import ProviderConfig
    provider = OllamaProvider(ProviderConfig(model="llama3.2"))
    
    agent = Agent(name="LocalBot", provider=provider)
    
    task = Task(instruction="Why is the sky blue? Answer in one short sentence.")
    print(f"Task: {task.instruction}")
    
    try:
        print("Sending request to local Ollama instance...")
        result = agent.execute(task)
        if result.success:
            print(f"Response: {result.output}")
        else:
            print(f"Failed: {result.error}")
    except Exception as e:
        print(f"Could not connect to Ollama. Make sure it is running locally. Error: {e}")

if __name__ == "__main__":
    main()
