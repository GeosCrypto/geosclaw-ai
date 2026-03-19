"""Tests for the shell tool."""
from __future__ import annotations

import pytest

from agent.tools.shell_tools import ShellTool


@pytest.mark.asyncio
async def test_echo_command():
    tool = ShellTool()
    result = await tool.execute(command="echo hello")
    assert result.success
    assert "hello" in result.output


@pytest.mark.asyncio
async def test_failing_command():
    tool = ShellTool()
    result = await tool.execute(command="exit 1")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_timeout():
    tool = ShellTool()
    result = await tool.execute(command="sleep 100", timeout=1)
    assert not result.success
    assert "timed out" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_shell_disabled(monkeypatch):
    import agent.tools.shell_tools as st
    import agent.config as cfg_module

    original = cfg_module.settings.allow_shell
    cfg_module.settings.allow_shell = False
    st.settings = cfg_module.settings

    try:
        tool = ShellTool()
        result = await tool.execute(command="echo hi")
        assert not result.success
        assert "disabled" in (result.error or "").lower()
    finally:
        cfg_module.settings.allow_shell = original
        st.settings = cfg_module.settings
