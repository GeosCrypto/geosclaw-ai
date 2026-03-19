"""
Base interface for AI providers.
All provider implementations must conform to this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncIterator

from pydantic import BaseModel


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    """A single conversation message."""

    role: Role
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d


class ToolDefinition(BaseModel):
    """JSON-schema definition of a callable tool."""

    name: str
    description: str
    parameters: dict[str, Any]


class ProviderResponse(BaseModel):
    """Structured response from an AI provider."""

    content: str
    tool_calls: list[dict[str, Any]] = []
    finish_reason: str = "stop"
    usage: dict[str, int] = {}


class BaseProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, api_key: str, model: str, **kwargs: Any) -> None:
        self.api_key = api_key
        self.model = model
        self.kwargs = kwargs

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        stream: bool = False,
    ) -> ProviderResponse:
        """Send messages and return a response."""

    @abstractmethod
    async def stream_complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> AsyncIterator[str]:
        """Stream completion tokens one by one."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""
