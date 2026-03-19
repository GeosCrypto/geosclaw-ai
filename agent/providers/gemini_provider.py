"""
Google Gemini provider implementation.
Supports Gemini models via the google-genai Python SDK.

Install the SDK:
    pip install google-genai>=1.0.0
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

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
    """
    Split a message list into (system_instruction, gemini_contents).
    Gemini uses a flat list of {'role': ..., 'parts': [...]} dicts.
    Tool results use role='user' with a function_response part.
    """
    system_instruction: str | None = None
    contents: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == Role.SYSTEM:
            system_instruction = msg.content
            continue

        if msg.role == Role.TOOL:
            # Tool result → function_response part
            try:
                response_data = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                response_data = {"result": msg.content}
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": msg.name or "unknown_tool",
                                "response": response_data,
                            }
                        }
                    ],
                }
            )
            continue

        if msg.role == Role.ASSISTANT and msg.tool_calls:
            # Tool call request → function_call parts
            parts: list[dict[str, Any]] = []
            if msg.content:
                parts.append({"text": msg.content})
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}
                parts.append(
                    {
                        "function_call": {
                            "name": tc["function"]["name"],
                            "args": args,
                        }
                    }
                )
            contents.append({"role": "model", "parts": parts})
            continue

        role = "model" if msg.role == Role.ASSISTANT else "user"
        contents.append({"role": role, "parts": [{"text": msg.content}]})

    return system_instruction, contents


def _convert_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert ToolDefinition list to Gemini function declarations."""
    declarations = []
    for t in tools:
        # Build properties dict compatible with Gemini Schema
        raw_props = t.parameters.get("properties", {})
        required = t.parameters.get("required", [])
        props: dict[str, Any] = {}
        for prop_name, prop_schema in raw_props.items():
            prop_type = prop_schema.get("type", "string").upper()
            entry: dict[str, Any] = {"type": prop_type}
            if "description" in prop_schema:
                entry["description"] = prop_schema["description"]
            if "enum" in prop_schema:
                entry["enum"] = prop_schema["enum"]
            props[prop_name] = entry

        declaration: dict[str, Any] = {
            "name": t.name,
            "description": t.description,
        }
        if props:
            declaration["parameters"] = {
                "type": "OBJECT",
                "properties": props,
            }
            if required:
                declaration["parameters"]["required"] = required

        declarations.append(declaration)
    return declarations


def _parse_response(response: Any) -> ProviderResponse:
    """Extract content and tool calls from a Gemini response."""
    text_content = ""
    tool_calls: list[dict[str, Any]] = []

    candidate = response.candidates[0] if response.candidates else None
    if candidate is None:
        return ProviderResponse(content="", finish_reason="stop", usage={})

    for part in candidate.content.parts:
        # Parts may be text or function_call objects
        if hasattr(part, "text") and part.text:
            text_content += part.text
        if hasattr(part, "function_call") and part.function_call:
            fc = part.function_call
            tool_calls.append(
                {
                    "id": f"gemini_{fc.name}_{len(tool_calls)}",
                    "type": "function",
                    "function": {
                        "name": fc.name,
                        "arguments": json.dumps(dict(fc.args)),
                    },
                }
            )

    finish_reason = "stop"
    if candidate.finish_reason:
        reason_str = str(candidate.finish_reason)
        if "STOP" in reason_str:
            finish_reason = "stop"
        elif "MAX_TOKENS" in reason_str:
            finish_reason = "length"
        elif "TOOL_USE" in reason_str or tool_calls:
            finish_reason = "tool_use"

    usage: dict[str, int] = {}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        meta = response.usage_metadata
        usage = {
            "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
            "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
        }

    return ProviderResponse(
        content=text_content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        usage=usage,
    )


class GeminiProvider(BaseProvider):
    """Provider implementation for Google Gemini models."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash", **kwargs: Any) -> None:
        super().__init__(api_key, model, **kwargs)
        try:
            from google import genai  # type: ignore[import]

            self._client = genai.Client(api_key=api_key)
        except ImportError as exc:
            raise ImportError(
                "google-genai is required for GeminiProvider. "
                "Install it with: pip install google-genai>=1.0.0"
            ) from exc

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        stream: bool = False,
    ) -> ProviderResponse:
        from google.genai import types as genai_types  # type: ignore[import]

        system_instruction, contents = _convert_messages(messages)

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if tools:
            tool_declarations = _convert_tools(tools)
            config_kwargs["tools"] = [
                genai_types.Tool(
                    function_declarations=[
                        genai_types.FunctionDeclaration(**decl)
                        for decl in tool_declarations
                    ]
                )
            ]

        config = genai_types.GenerateContentConfig(**config_kwargs)

        response = await self._client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )
        return _parse_response(response)

    async def stream_complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> AsyncIterator[str]:
        from google.genai import types as genai_types  # type: ignore[import]

        system_instruction, contents = _convert_messages(messages)

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        config = genai_types.GenerateContentConfig(**config_kwargs)

        async for chunk in await self._client.aio.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=config,
        ):
            if chunk.candidates:
                for part in chunk.candidates[0].content.parts:
                    if hasattr(part, "text") and part.text:
                        yield part.text
