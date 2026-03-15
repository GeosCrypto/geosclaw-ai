"""
Conversation memory and history management.
Supports in-memory and file-backed persistence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.config import settings
from agent.providers.base import Message, Role


class ConversationMemory:
    """
    Manages conversation history with optional file-based persistence.

    Features:
    - Sliding window to cap history length
    - File-backed persistence across sessions
    - Thread-safe (single-process)
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        max_messages: int | None = None,
        persist_path: str | None = None,
    ) -> None:
        self._messages: list[Message] = []
        self._system_prompt = system_prompt
        self._max_messages = max_messages or settings.max_history_messages
        self._persist_path = persist_path

        if persist_path and Path(persist_path).exists():
            self._load(persist_path)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def add_user(self, content: str) -> None:
        """Append a user message."""
        self._append(Message(role=Role.USER, content=content))

    def add_assistant(
        self,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Append an assistant message (optionally with tool calls)."""
        self._append(
            Message(role=Role.ASSISTANT, content=content, tool_calls=tool_calls)
        )

    def add_tool_result(self, tool_call_id: str, content: str, name: str) -> None:
        """Append a tool-result message."""
        self._append(
            Message(
                role=Role.TOOL,
                content=content,
                tool_call_id=tool_call_id,
                name=name,
            )
        )

    def get_messages(self, include_system: bool = True) -> list[Message]:
        """Return the full message list, optionally prepending the system prompt."""
        messages = list(self._messages)
        if include_system and self._system_prompt:
            return [Message(role=Role.SYSTEM, content=self._system_prompt)] + messages
        return messages

    def clear(self) -> None:
        """Clear all messages (keeps system prompt)."""
        self._messages.clear()
        if self._persist_path:
            self._save(self._persist_path)

    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt = prompt

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def system_prompt(self) -> str | None:
        return self._system_prompt

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_prompt": self._system_prompt,
            "messages": [m.to_dict() for m in self._messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationMemory":
        obj = cls(system_prompt=data.get("system_prompt"))
        for m in data.get("messages", []):
            role = Role(m["role"])
            obj._messages.append(
                Message(
                    role=role,
                    content=m.get("content", ""),
                    tool_call_id=m.get("tool_call_id"),
                    tool_calls=m.get("tool_calls"),
                    name=m.get("name"),
                )
            )
        return obj

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _append(self, message: Message) -> None:
        self._messages.append(message)
        # Trim to max_messages (keep the most recent)
        if len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages :]
        if self._persist_path:
            self._save(self._persist_path)

    def _save(self, path: str) -> None:
        try:
            p = Path(path)
            p.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass  # Persist failures are non-fatal

    def _load(self, path: str) -> None:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            loaded = ConversationMemory.from_dict(data)
            self._system_prompt = self._system_prompt or loaded._system_prompt
            self._messages = loaded._messages
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass  # Corrupt persistence file – start fresh
