from __future__ import annotations

from typing import Callable
from aether.core.communication import AgentMessage


class AgentMessageBus:
    """
    A local, in-process, synchronous message bus for routing messages between agents.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[AgentMessage], AgentMessage | None]] = {}
        self._log: list[AgentMessage] = []

    def register(
        self, agent_name: str, handler: Callable[[AgentMessage], AgentMessage | None]
    ) -> None:
        """
        Register a message handler for a specific agent.
        """
        self._handlers[agent_name] = handler

    def send(self, message: AgentMessage) -> AgentMessage | None:
        """
        Send a message through the bus. Invocates the registered handler synchronously.
        """
        self._log.append(message)
        receiver = message.receiver
        if receiver in self._handlers:
            response = self._handlers[receiver](message)
            if response is not None:
                self._log.append(response)
            return response
        return None

    def get_log(self) -> list[AgentMessage]:
        """
        Return the immutable copy of the message log.
        """
        return list(self._log)
