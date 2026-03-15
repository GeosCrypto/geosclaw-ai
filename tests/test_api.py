"""Tests for the REST API."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agent.api import app, _sessions
from agent.core import AgentResponse


@pytest.fixture(autouse=True)
def clear_sessions():
    """Ensure sessions are isolated between tests."""
    _sessions.clear()
    yield
    _sessions.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_list_tools(client):
    response = client.get("/tools")
    assert response.status_code == 200
    tools = response.json()
    assert isinstance(tools, list)
    assert len(tools) > 0
    names = [t["name"] for t in tools]
    assert "read_file" in names


def test_list_sessions_empty(client):
    response = client.get("/sessions")
    assert response.status_code == 200
    assert response.json() == []


@patch("agent.api._get_or_create_session")
def test_chat_creates_session(mock_get_session, client):
    """POST /chat should return a session_id and content."""
    from agent.api import Agent

    mock_agent = AsyncMock()
    mock_agent.memory.message_count = 2
    mock_agent.memory.system_prompt = None
    mock_agent._config = AsyncMock()
    mock_agent.run = AsyncMock(
        return_value=AgentResponse(
            content="Hello from mock!",
            tool_calls_made=[],
            iterations=1,
            total_tokens=50,
        )
    )

    mock_get_session.return_value = ("test-session-id", mock_agent)

    response = client.post(
        "/chat",
        json={"message": "Hello", "session_id": "test-session-id"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session-id"
    assert data["content"] == "Hello from mock!"
    assert data["iterations"] == 1


def test_delete_nonexistent_session(client):
    response = client.delete("/sessions/nonexistent-id")
    assert response.status_code == 404


def test_api_key_required_when_set(monkeypatch):
    """When api_key is configured, requests without it should be rejected."""
    from agent import api as api_module
    import agent.config as cfg_module

    original_key = cfg_module.settings.api_key
    cfg_module.settings.api_key = "secret-key"
    api_module.settings = cfg_module.settings

    try:
        c = TestClient(app)
        # Without key
        response = c.get("/tools")
        assert response.status_code == 401

        # With correct key
        response = c.get("/tools", headers={"X-Api-Key": "secret-key"})
        assert response.status_code == 200
    finally:
        cfg_module.settings.api_key = original_key
        api_module.settings = cfg_module.settings
