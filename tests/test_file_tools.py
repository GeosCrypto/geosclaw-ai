"""Tests for the file tools."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Override workspace to a temp dir before importing tools
@pytest.fixture(autouse=True)
def tmp_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOSCLAW_WORKSPACE_DIR", str(tmp_path))
    # Re-import settings so the workspace is picked up
    import importlib
    import agent.config as cfg_module
    cfg_module.settings = cfg_module.Config()
    # Patch tools to use updated settings
    import agent.tools.file_tools as ft
    ft.settings = cfg_module.settings
    return tmp_path


@pytest.mark.asyncio
async def test_write_and_read_file(tmp_workspace):
    from agent.tools.file_tools import WriteFileTool, ReadFileTool

    writer = WriteFileTool()
    reader = ReadFileTool()

    result = await writer.execute(path="hello.txt", content="Hello, world!")
    assert result.success
    assert "hello.txt" in result.output

    result = await reader.execute(path="hello.txt")
    assert result.success
    assert result.output == "Hello, world!"


@pytest.mark.asyncio
async def test_write_append(tmp_workspace):
    from agent.tools.file_tools import WriteFileTool, ReadFileTool

    writer = WriteFileTool()
    reader = ReadFileTool()

    await writer.execute(path="log.txt", content="line1\n")
    await writer.execute(path="log.txt", content="line2\n", append=True)

    result = await reader.execute(path="log.txt")
    assert result.success
    assert "line1" in result.output
    assert "line2" in result.output


@pytest.mark.asyncio
async def test_read_nonexistent_file(tmp_workspace):
    from agent.tools.file_tools import ReadFileTool

    reader = ReadFileTool()
    result = await reader.execute(path="does_not_exist.txt")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_list_files(tmp_workspace):
    from agent.tools.file_tools import WriteFileTool, ListFilesTool

    writer = WriteFileTool()
    lister = ListFilesTool()

    await writer.execute(path="a.txt", content="a")
    await writer.execute(path="b.txt", content="b")

    result = await lister.execute(path=".")
    assert result.success
    assert "a.txt" in result.output
    assert "b.txt" in result.output


@pytest.mark.asyncio
async def test_search_files(tmp_workspace):
    from agent.tools.file_tools import WriteFileTool, SearchFilesTool

    writer = WriteFileTool()
    searcher = SearchFilesTool()

    await writer.execute(path="code.py", content="def hello():\n    print('hello')\n")

    result = await searcher.execute(pattern="def hello")
    assert result.success
    assert "code.py" in result.output


@pytest.mark.asyncio
async def test_delete_file(tmp_workspace):
    from agent.tools.file_tools import WriteFileTool, DeleteFileTool, ReadFileTool

    writer = WriteFileTool()
    deleter = DeleteFileTool()
    reader = ReadFileTool()

    await writer.execute(path="temp.txt", content="temp")
    result = await deleter.execute(path="temp.txt")
    assert result.success

    read_result = await reader.execute(path="temp.txt")
    assert not read_result.success


@pytest.mark.asyncio
async def test_create_directory(tmp_workspace):
    from agent.tools.file_tools import CreateDirectoryTool

    creator = CreateDirectoryTool()
    result = await creator.execute(path="subdir/nested")
    assert result.success
    assert (tmp_workspace / "subdir" / "nested").is_dir()


@pytest.mark.asyncio
async def test_path_traversal_blocked(tmp_workspace):
    from agent.tools.file_tools import ReadFileTool

    reader = ReadFileTool()
    result = await reader.execute(path="../../etc/passwd")
    assert not result.success
    assert "outside" in (result.error or "").lower()
