"""
Azure OpenAI provider implementation.
Uses the openai package's AsyncAzureOpenAI client.

Required environment variables / config fields:
    GEOSCLAW_AZURE_OPENAI_API_KEY      — Azure OpenAI resource key
    GEOSCLAW_AZURE_OPENAI_ENDPOINT     — e.g. https://<resource>.openai.azure.com/
    GEOSCLAW_AZURE_OPENAI_DEPLOYMENT   — deployment/model name, e.g. gpt-4o
    GEOSCLAW_AZURE_OPENAI_API_VERSION  — e.g. 2024-08-01-preview (default)

Usage::
    from agent.providers.azure_provider import AzureOpenAIProvider
    provider = AzureOpenAIProvider(
        api_key="<key>",
        endpoint="https://<resource>.openai.azure.com/",
        deployment="gpt-4o",
    )
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from openai import AsyncAzureOpenAI

from agent.providers.base import (
    BaseProvider,
    Message,
    ProviderResponse,
    ToolDefinition,
)
from agent.providers.openai_provider import _convert_messages, _convert_tools


class AzureOpenAIProvider(BaseProvider):
    """Provider implementation for Azure-hosted OpenAI models."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str = "2024-08-01-preview",
        **kwargs: Any,
    ) -> None:
        # model == deployment name for Azure
        super().__init__(api_key=api_key, model=deployment, **kwargs)
        self._deployment = deployment
        self._client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

    @property
    def provider_name(self) -> str:
        return "azure_openai"

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
            "model": self._deployment,
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
            "model": self._deployment,
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
