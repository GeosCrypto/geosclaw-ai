"""Tests for the memory (persistent) tools."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOSCLAW_WORKSPACE_DIR", str(tmp_path))
    import importlib
    import agent.config as cfg_module
    cfg_module.settings = cfg_module.Config()
    import agent.tools.memory_tools as mt
    mt.settings = cfg_module.settings
    return tmp_path


@pytest.mark.asyncio
async def test_save_and_recall(tmp_workspace):
    from agent.tools.memory_tools import SaveMemoryTool, RecallMemoryTool

    saver = SaveMemoryTool()
    recaller = RecallMemoryTool()

    result = await saver.execute(key="project", value="GeosclawAI")
    assert result.success

    result = await recaller.execute(key="project")
    assert result.success
    assert "GeosclawAI" in result.output


@pytest.mark.asyncio
async def test_recall_all(tmp_workspace):
    from agent.tools.memory_tools import SaveMemoryTool, RecallMemoryTool

    saver = SaveMemoryTool()
    recaller = RecallMemoryTool()

    await saver.execute(key="a", value="alpha")
    await saver.execute(key="b", value="beta")

    result = await recaller.execute()
    assert result.success
    assert "alpha" in result.output
    assert "beta" in result.output


@pytest.mark.asyncio
async def test_recall_missing_key(tmp_workspace):
    from agent.tools.memory_tools import SaveMemoryTool, RecallMemoryTool

    saver = SaveMemoryTool()
    recaller = RecallMemoryTool()

    # Save something so the memory file exists, then look for a missing key
    await saver.execute(key="existing", value="value")
    result = await recaller.execute(key="nonexistent")
    assert result.success
    assert "No memory entry" in result.output


@pytest.mark.asyncio
async def test_recall_empty_memory(tmp_workspace):
    from agent.tools.memory_tools import RecallMemoryTool

    recaller = RecallMemoryTool()
    result = await recaller.execute()
    assert result.success
    assert "empty" in result.output.lower()
