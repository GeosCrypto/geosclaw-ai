"""
Anthropic provider implementation.
Supports Claude models via the Anthropic Python SDK.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import anthropic

from agent.providers.base import (
    BaseProvider,
    Message,
    ProviderResponse,
    Role,
    ToolDefinition,
)


def _convert_messages(
    messages: list[Message],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Split messages into optional system prompt + anthropic message list."""
    system: str | None = None
    converted: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == Role.SYSTEM:
            system = msg.content
            continue

        if msg.role == Role.TOOL:
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content,
                        }
                    ],
                }
            )
            continue

        entry: dict[str, Any] = {"role": msg.role.value}

        if msg.tool_calls:
            content_blocks: list[dict[str, Any]] = []
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"]),
                    }
                )
            entry["content"] = content_blocks
        else:
            entry["content"] = msg.content

        converted.append(entry)

    return system, converted


def _convert_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


class AnthropicProvider(BaseProvider):
    """Provider implementation for Anthropic Claude models."""

    def __init__(self, api_key: str, model: str, **kwargs: Any) -> None:
        super().__init__(api_key, model, **kwargs)
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        stream: bool = False,
    ) -> ProviderResponse:
        system, converted = _convert_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": converted,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _convert_tools(tools)

        response = await self._client.messages.create(**kwargs)

        text_content = ""
        tool_calls: list[dict[str, Any]] = []

        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input),
                        },
                    }
                )

        return ProviderResponse(
            content=text_content,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "stop",
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    async def stream_complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> AsyncIterator[str]:
        system, converted = _convert_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": converted,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _convert_tools(tools)

        async with self._client.messages.stream(**kwargs) as stream_ctx:
            async for text in stream_ctx.text_stream:
                yield text
