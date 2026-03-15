"""
Memory tools: allow the agent to save and recall notes across turns.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.config import settings
from agent.tools.base import BaseTool, ToolResult


def _memory_path() -> Path:
    return Path(settings.workspace_dir).resolve() / settings.memory_file


class SaveMemoryTool(BaseTool):
    """Save a note to the agent's persistent memory."""

    @property
    def name(self) -> str:
        return "save_memory"

    @property
    def description(self) -> str:
        return (
            "Save a key-value note to persistent memory so you can recall it later. "
            "Useful for storing important facts, decisions, or context."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Unique identifier for the memory entry",
                },
                "value": {
                    "type": "string",
                    "description": "Content to remember",
                },
            },
            "required": ["key", "value"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        key: str = kwargs.get("key", "")
        value: str = kwargs.get("value", "")

        memory_path = _memory_path()
        try:
            data: dict[str, str] = {}
            if memory_path.exists():
                data = json.loads(memory_path.read_text(encoding="utf-8"))
            data[key] = value
            memory_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=f"Saved memory: '{key}'",
            )
        except (OSError, json.JSONDecodeError) as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )


class RecallMemoryTool(BaseTool):
    """Recall notes from the agent's persistent memory."""

    @property
    def name(self) -> str:
        return "recall_memory"

    @property
    def description(self) -> str:
        return (
            "Recall previously saved notes from persistent memory. "
            "Pass a key to retrieve a specific entry, "
            "or omit the key to list all entries."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key to retrieve (omit to list all keys)",
                }
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        key: str | None = kwargs.get("key")
        memory_path = _memory_path()

        if not memory_path.exists():
            return ToolResult(
                tool_name=self.name,
                success=True,
                output="Memory is empty.",
            )

        try:
            data: dict[str, str] = json.loads(
                memory_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )

        if key:
            if key in data:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    output=f"{key}: {data[key]}",
                )
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=f"No memory entry found for key '{key}'.",
            )

        if not data:
            return ToolResult(
                tool_name=self.name, success=True, output="Memory is empty."
            )

        lines = [f"- {k}: {v}" for k, v in data.items()]
        return ToolResult(
            tool_name=self.name,
            success=True,
            output="Stored memories:\n" + "\n".join(lines),
        )
