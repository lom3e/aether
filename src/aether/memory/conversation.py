from __future__ import annotations

import json
from typing import Any

from aether.core.execution import Message
from aether.memory.base import BaseMemoryStore


def estimate_message_tokens(msg: Message) -> int:
    """
    Estimate the number of tokens for a message using a simple characters/4 heuristic.
    """
    tokens = len(msg.content) // 4 + 4
    if msg.tool_calls:
        for tc in msg.tool_calls:
            tokens += len(tc.tool_name) // 4 + 4
            if tc.arguments:
                tokens += len(json.dumps(tc.arguments)) // 4 + 4
    return tokens


class ConversationMemory(BaseMemoryStore):
    """
    Manages short-term conversation message history per session.
    """

    def __init__(self) -> None:
        self._conversations: dict[str, list[Message]] = {}

    def get_messages(self, session_id: str) -> list[Message]:
        """
        Retrieve message history for a session.
        """
        return self._conversations.get(session_id, [])

    def add_message(self, session_id: str, message: Message) -> None:
        """
        Add a message to the history of a session.
        """
        if session_id not in self._conversations:
            self._conversations[session_id] = []
        self._conversations[session_id].append(message)

    def set_messages(self, session_id: str, messages: list[Message]) -> None:
        """
        Set or overwrite message history for a session.
        """
        self._conversations[session_id] = list(messages)

    def clear(self, session_id: str) -> None:
        """
        Clear message history for a session.
        """
        self._conversations.pop(session_id, None)

    def truncate_context(self, messages: list[Message], max_tokens: int) -> list[Message]:
        """
        Truncate message list to fit within max_tokens.
        Always preserves the initial system prompt (if index 0 is system) and the last message (current turn).
        """
        if not messages:
            return []

        total_tokens = sum(estimate_message_tokens(m) for m in messages)
        if total_tokens <= max_tokens:
            return messages

        system_msg = messages[0] if messages[0].role == "system" else None
        last_msg = messages[-1]

        current_tokens = 0
        if system_msg:
            current_tokens += estimate_message_tokens(system_msg)

        if len(messages) > 1 or not system_msg:
            current_tokens += estimate_message_tokens(last_msg)

        # If base messages alone exceed or hit the limit, return just them
        if current_tokens >= max_tokens:
            res = []
            if system_msg:
                res.append(system_msg)
            if len(messages) > 1 or not system_msg:
                res.append(last_msg)
            return res

        start_idx = len(messages) - 2
        end_idx = 1 if system_msg else 0

        middle_messages = []
        for idx in range(start_idx, end_idx - 1, -1):
            msg = messages[idx]
            msg_tokens = estimate_message_tokens(msg)
            if current_tokens + msg_tokens <= max_tokens:
                middle_messages.append((idx, msg))
                current_tokens += msg_tokens
            else:
                break

        # Re-assemble chronologically
        result = []
        if system_msg:
            result.append(system_msg)

        middle_messages.sort(key=lambda x: x[0])
        for _, msg in middle_messages:
            result.append(msg)

        if len(messages) > 1 or not system_msg:
            result.append(last_msg)

        return result
