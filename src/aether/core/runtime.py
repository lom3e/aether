from aether.agents.agent import Agent


class AetherRuntime:
    """
    Main runtime environment for Aether Core.
    """

    def __init__(self):
        self.agents = []

    def register_agent(self, agent: Agent):
        self.agents.append(agent)

    def list_agents(self):
        return self.agents