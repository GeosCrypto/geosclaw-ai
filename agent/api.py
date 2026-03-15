"""
FastAPI REST API for GeosclawAI.

Endpoints:
  POST /chat            – Single-turn or multi-turn chat
  POST /chat/stream     – Streaming chat via Server-Sent Events
  GET  /health          – Health check
  GET  /tools           – List available tools
  DELETE /history/{session_id} – Clear a session
  GET  /sessions        – List active sessions
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent import __version__
from agent.config import settings
from agent.core import Agent, AgentResponse, build_default_tools, create_agent
from agent.memory import ConversationMemory

# ------------------------------------------------------------------ #
# App factory                                                          #
# ------------------------------------------------------------------ #

app = FastAPI(
    title="GeosclawAI",
    description=(
        "A powerful autonomous AI agent with file management, "
        "code analysis, web search, and shell execution capabilities."
    ),
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store  {session_id -> Agent}
_sessions: dict[str, Agent] = {}


# ------------------------------------------------------------------ #
# Auth                                                                 #
# ------------------------------------------------------------------ #

def _check_api_key(x_api_key: str = Header(default="")) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# ------------------------------------------------------------------ #
# Request / response models                                            #
# ------------------------------------------------------------------ #

class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message to send to the agent")
    session_id: str | None = Field(
        default=None,
        description="Session ID for multi-turn conversations. A new session is created if omitted.",
    )
    system_prompt: str | None = Field(
        default=None,
        description="Override the system prompt (only applied when creating a new session)",
    )
    provider: str | None = Field(
        default=None,
        description="AI provider override ('openai' or 'anthropic')",
    )
    model: str | None = Field(
        default=None,
        description="Model override",
    )
    temperature: float | None = Field(
        default=None,
        description="Temperature override (0.0–1.0)",
    )
    enable_tools: bool = Field(
        default=True,
        description="Whether to enable tools for this request",
    )


class ChatResponse(BaseModel):
    session_id: str
    content: str
    tool_calls_made: list[dict[str, Any]] = []
    iterations: int = 0
    total_tokens: int = 0


class ToolInfo(BaseModel):
    name: str
    description: str


class SessionInfo(BaseModel):
    session_id: str
    message_count: int
    system_prompt: str | None


# ------------------------------------------------------------------ #
# Helper                                                               #
# ------------------------------------------------------------------ #

def _get_or_create_session(
    session_id: str | None,
    system_prompt: str | None = None,
    provider: str | None = None,
    enable_tools: bool = True,
) -> tuple[str, Agent]:
    if session_id and session_id in _sessions:
        return session_id, _sessions[session_id]

    # Create new session
    sid = session_id or str(uuid.uuid4())

    # Build provider
    cfg = settings
    effective_provider = provider or cfg.default_provider
    if effective_provider == "anthropic":
        from agent.providers.anthropic_provider import AnthropicProvider

        prov = AnthropicProvider(
            api_key=cfg.anthropic_api_key, model=cfg.anthropic_model
        )
    else:
        from agent.providers.openai_provider import OpenAIProvider

        prov = OpenAIProvider(
            api_key=cfg.openai_api_key,
            model=cfg.openai_model,
            base_url=cfg.openai_base_url,
        )

    tools = build_default_tools(cfg) if enable_tools else []
    agent = Agent(
        provider=prov,
        tools=tools,
        system_prompt=system_prompt,
        config=cfg,
    )
    _sessions[sid] = agent
    return sid, agent


# ------------------------------------------------------------------ #
# Routes                                                               #
# ------------------------------------------------------------------ #

@app.get("/health", tags=["System"])
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "version": __version__}


@app.get(
    "/tools",
    response_model=list[ToolInfo],
    tags=["Tools"],
    dependencies=[Depends(_check_api_key)],
)
async def list_tools() -> list[ToolInfo]:
    """List all available tools."""
    tools = build_default_tools(settings)
    return [ToolInfo(name=t.name, description=t.description) for t in tools]


@app.get(
    "/sessions",
    response_model=list[SessionInfo],
    tags=["Sessions"],
    dependencies=[Depends(_check_api_key)],
)
async def list_sessions() -> list[SessionInfo]:
    """List all active sessions."""
    return [
        SessionInfo(
            session_id=sid,
            message_count=agent.memory.message_count,
            system_prompt=agent.memory.system_prompt,
        )
        for sid, agent in _sessions.items()
    ]


@app.delete(
    "/sessions/{session_id}",
    tags=["Sessions"],
    dependencies=[Depends(_check_api_key)],
)
async def delete_session(session_id: str) -> dict[str, str]:
    """Delete a session and clear its history."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del _sessions[session_id]
    return {"status": "deleted", "session_id": session_id}


@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["Chat"],
    dependencies=[Depends(_check_api_key)],
)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the agent and get a response."""
    sid, agent = _get_or_create_session(
        session_id=request.session_id,
        system_prompt=request.system_prompt,
        provider=request.provider,
        enable_tools=request.enable_tools,
    )

    # Apply per-request overrides
    if request.temperature is not None:
        agent._config.temperature = request.temperature  # type: ignore[attr-defined]

    response: AgentResponse = await agent.run(request.message)

    return ChatResponse(
        session_id=sid,
        content=response.content,
        tool_calls_made=response.tool_calls_made,
        iterations=response.iterations,
        total_tokens=response.total_tokens,
    )


@app.post(
    "/chat/stream",
    tags=["Chat"],
    dependencies=[Depends(_check_api_key)],
)
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """
    Stream the agent's response as Server-Sent Events.

    Each event has the format::

        data: <token>\\n\\n

    A final event signals completion::

        data: [DONE]\\n\\n
    """
    sid, agent = _get_or_create_session(
        session_id=request.session_id,
        system_prompt=request.system_prompt,
        provider=request.provider,
        enable_tools=request.enable_tools,
    )

    async def generate() -> AsyncIterator[str]:
        yield f"data: {{\"session_id\": \"{sid}\"}}\n\n"
        async for token in agent.stream(request.message):
            # Escape newlines in the token for SSE
            safe_token = token.replace("\n", "\\n")
            yield f"data: {safe_token}\n\n"
            await asyncio.sleep(0)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Session-Id": sid,
        },
    )
