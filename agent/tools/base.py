"""
Base class and result type for all tools.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from agent.providers.base import ToolDefinition


class ToolResult(BaseModel):
    """Result returned by a tool execution."""

    tool_name: str
    success: bool
    output: str
    error: str | None = None

    def to_message_content(self) -> str:
        if self.success:
            return self.output
        return f"Error: {self.error}"


class BaseTool(ABC):
    """Abstract base for all agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name used in function calls."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Description shown to the model."""

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for the tool's parameters."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool and return a result."""

    def to_definition(self) -> ToolDefinition:
        """Convert this tool to a provider-agnostic ToolDefinition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )
