"""Tests for the memory system."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.memory import ConversationMemory
from agent.providers.base import Role


def test_add_and_retrieve_messages():
    mem = ConversationMemory(system_prompt="You are helpful.")
    mem.add_user("Hello")
    mem.add_assistant("Hi there!")

    messages = mem.get_messages(include_system=True)
    assert messages[0].role == Role.SYSTEM
    assert messages[1].role == Role.USER
    assert messages[2].role == Role.ASSISTANT
    assert messages[1].content == "Hello"
    assert messages[2].content == "Hi there!"


def test_message_count():
    mem = ConversationMemory()
    assert mem.message_count == 0
    mem.add_user("one")
    assert mem.message_count == 1
    mem.add_assistant("two")
    assert mem.message_count == 2


def test_clear():
    mem = ConversationMemory(system_prompt="sys")
    mem.add_user("u")
    mem.add_assistant("a")
    mem.clear()
    assert mem.message_count == 0
    # System prompt should be preserved
    assert mem.system_prompt == "sys"


def test_max_messages():
    mem = ConversationMemory(max_messages=4)
    for i in range(10):
        mem.add_user(f"msg {i}")
    assert mem.message_count == 4
    # Should keep the most recent messages
    msgs = mem.get_messages(include_system=False)
    assert msgs[0].content == "msg 6"


def test_tool_result_message():
    mem = ConversationMemory()
    mem.add_tool_result(tool_call_id="call_123", content="result text", name="read_file")
    msgs = mem.get_messages(include_system=False)
    assert len(msgs) == 1
    assert msgs[0].role == Role.TOOL
    assert msgs[0].tool_call_id == "call_123"


def test_persist_and_load(tmp_path):
    persist_file = str(tmp_path / "memory.json")
    mem = ConversationMemory(system_prompt="persist", persist_path=persist_file)
    mem.add_user("stored message")

    # Load from the same file
    mem2 = ConversationMemory(persist_path=persist_file)
    assert mem2.message_count == 1
    msgs = mem2.get_messages(include_system=False)
    assert msgs[0].content == "stored message"


def test_to_dict_and_from_dict():
    mem = ConversationMemory(system_prompt="sys")
    mem.add_user("hello")
    mem.add_assistant("world")

    d = mem.to_dict()
    restored = ConversationMemory.from_dict(d)

    assert restored.message_count == 2
    msgs = restored.get_messages(include_system=False)
    assert msgs[0].content == "hello"
    assert msgs[1].content == "world"
