"""Tests for the core agent using a mock provider."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.core import Agent, AgentResponse, build_default_tools
from agent.memory import ConversationMemory
from agent.providers.base import BaseProvider, Message, ProviderResponse, ToolDefinition
from agent.tools.base import BaseTool, ToolResult


# ────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ────────────────────────────────────────────────────────────────────────────

class MockProvider(BaseProvider):
    """A provider that returns pre-configured responses."""

    def __init__(self, responses: list[ProviderResponse]) -> None:
        super().__init__(api_key="mock", model="mock-model")
        self._responses = iter(responses)

    @property
    def provider_name(self) -> str:
        return "mock"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        stream: bool = False,
    ) -> ProviderResponse:
        return next(self._responses)

    async def stream_complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> AsyncIterator[str]:
        response = next(self._responses)
        for char in response.content:
            yield char


class EchoTool(BaseTool):
    """A simple tool that echoes its input."""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo the input text."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        text = kwargs.get("text", "")
        return ToolResult(tool_name=self.name, success=True, output=f"ECHO: {text}")


# ────────────────────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_simple_response():
    """Agent should return the provider's response content."""
    provider = MockProvider(
        [ProviderResponse(content="Hello from agent!", finish_reason="stop")]
    )
    agent = Agent(provider=provider, tools=[])

    response = await agent.run("Hi")
    assert response.content == "Hello from agent!"
    assert response.iterations == 1


@pytest.mark.asyncio
async def test_tool_call_execution():
    """Agent should execute tool calls and return final response."""
    tool_call = {
        "id": "call_001",
        "type": "function",
        "function": {"name": "echo", "arguments": json.dumps({"text": "world"})},
    }
    provider = MockProvider(
        [
            ProviderResponse(
                content="",
                tool_calls=[tool_call],
                finish_reason="tool_use",
            ),
            ProviderResponse(content="Done!", finish_reason="stop"),
        ]
    )
    agent = Agent(provider=provider, tools=[EchoTool()])

    response = await agent.run("Echo world please")
    assert response.content == "Done!"
    assert len(response.tool_calls_made) == 1
    assert response.tool_calls_made[0]["tool"] == "echo"


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    """Calling an unknown tool should record an error without crashing."""
    tool_call = {
        "id": "call_002",
        "type": "function",
        "function": {"name": "nonexistent_tool", "arguments": "{}"},
    }
    provider = MockProvider(
        [
            ProviderResponse(
                content="",
                tool_calls=[tool_call],
                finish_reason="tool_use",
            ),
            ProviderResponse(content="OK", finish_reason="stop"),
        ]
    )
    agent = Agent(provider=provider, tools=[])

    response = await agent.run("do something")
    assert response.content == "OK"


@pytest.mark.asyncio
async def test_on_tool_call_callback():
    """The on_tool_call callback should be invoked for each tool call."""
    tool_call = {
        "id": "call_003",
        "type": "function",
        "function": {"name": "echo", "arguments": json.dumps({"text": "cb"})},
    }
    provider = MockProvider(
        [
            ProviderResponse(content="", tool_calls=[tool_call], finish_reason="tool_use"),
            ProviderResponse(content="Done", finish_reason="stop"),
        ]
    )
    agent = Agent(provider=provider, tools=[EchoTool()])

    called_with = []

    def on_tool_call(name: str, args: dict) -> None:
        called_with.append((name, args))

    await agent.run("echo cb", on_tool_call=on_tool_call)
    assert called_with == [("echo", {"text": "cb"})]


@pytest.mark.asyncio
async def test_clear_history():
    provider = MockProvider(
        [ProviderResponse(content="hi", finish_reason="stop")]
    )
    agent = Agent(provider=provider, tools=[])
    await agent.run("hello")
    assert agent.memory.message_count > 0

    agent.clear_history()
    assert agent.memory.message_count == 0


def test_add_and_remove_tool():
    provider = MockProvider([])
    agent = Agent(provider=provider, tools=[])
    assert len(agent.tools) == 0

    agent.add_tool(EchoTool())
    assert len(agent.tools) == 1

    agent.remove_tool("echo")
    assert len(agent.tools) == 0


@pytest.mark.asyncio
async def test_stream_yields_tokens():
    """stream() should yield text tokens."""
    provider = MockProvider(
        [ProviderResponse(content="Hello streaming world!", finish_reason="stop")]
    )
    agent = Agent(provider=provider, tools=[])

    chunks = []
    async for chunk in agent.stream("test"):
        chunks.append(chunk)

    assert "".join(chunks) == "Hello streaming world!"


def test_build_default_tools():
    """build_default_tools should return a non-empty list."""
    tools = build_default_tools()
    assert len(tools) > 0
    tool_names = [t.name for t in tools]
    assert "read_file" in tool_names
    assert "write_file" in tool_names
