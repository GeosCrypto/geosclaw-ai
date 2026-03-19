"""
OpenAI provider implementation.
Supports GPT-4o and other OpenAI models.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from agent.providers.base import (
    BaseProvider,
    Message,
    ProviderResponse,
    Role,
    ToolDefinition,
)


def _convert_messages(messages: list[Message]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for msg in messages:
        entry: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
        if msg.name:
            entry["name"] = msg.name
        if msg.tool_call_id:
            entry["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            entry["tool_calls"] = msg.tool_calls
        converted.append(entry)
    return converted


def _convert_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


class OpenAIProvider(BaseProvider):
    """Provider implementation for OpenAI GPT models."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, model, **kwargs)
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    @property
    def provider_name(self) -> str:
        return "openai"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        stream: bool = False,
    ) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": _convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = _convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        tool_calls: list[dict[str, Any]] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                )

        return ProviderResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
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
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": _convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = _convert_tools(tools)

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
