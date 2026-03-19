"""
Ollama provider implementation.
Ollama exposes an OpenAI-compatible API at http://localhost:11434/v1 by default.
No API key is required for local Ollama instances.

Usage::
    from agent.providers.ollama_provider import OllamaProvider
    provider = OllamaProvider(model="llama3.2")
    # or with a custom host:
    provider = OllamaProvider(model="mistral", base_url="http://remote-host:11434/v1")
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from agent.providers.base import Message, ProviderResponse, ToolDefinition
from agent.providers.openai_provider import OpenAIProvider

_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"


class OllamaProvider(OpenAIProvider):
    """
    Provider for locally-running Ollama models.

    Ollama exposes an OpenAI-compatible REST API, so this provider inherits
    all logic from OpenAIProvider and simply changes the base URL and
    skips API-key validation.
    """

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = _DEFAULT_OLLAMA_BASE_URL,
        api_key: str = "ollama",  # Ollama ignores this value
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key=api_key, model=model, base_url=base_url, **kwargs)

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        stream: bool = False,
    ) -> ProviderResponse:
        # Ollama may not support tool calling for all models; fall back
        # gracefully by attempting tool-call completion and retrying plain
        # if a connection/protocol error is raised.
        try:
            return await super().complete(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
            )
        except Exception as exc:
            # If the model doesn't support tools, retry without them
            if tools and "tool" in str(exc).lower():
                return await super().complete(
                    messages,
                    tools=None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                )
            raise

    async def stream_complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> AsyncIterator[str]:
        async for token in super().stream_complete(
            messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield token
