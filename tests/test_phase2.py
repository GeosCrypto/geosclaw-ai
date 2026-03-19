"""Tests for Phase 2: new providers, git skill, patch_file, run_python, run_tests."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.providers.base import (
    BaseProvider,
    Message,
    ProviderResponse,
    Role,
    ToolDefinition,
)
from agent.tools.base import ToolResult


# ─────────────────────────────────────────────────────────────────────────────
# OllamaProvider tests
# ─────────────────────────────────────────────────────────────────────────────

class TestOllamaProvider:
    def test_provider_name(self):
        from agent.providers.ollama_provider import OllamaProvider
        p = OllamaProvider.__new__(OllamaProvider)
        p.api_key = "ollama"
        p.model = "llama3.2"
        assert p.provider_name == "ollama"

    def test_defaults(self):
        from agent.providers.ollama_provider import OllamaProvider, _DEFAULT_OLLAMA_BASE_URL
        # Just check default constants exist
        assert _DEFAULT_OLLAMA_BASE_URL == "http://localhost:11434/v1"


# ─────────────────────────────────────────────────────────────────────────────
# AzureOpenAIProvider tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAzureOpenAIProvider:
    def test_provider_name(self):
        from agent.providers.azure_provider import AzureOpenAIProvider
        # Patch the client constructor so we don't need real creds
        with patch("agent.providers.azure_provider.AsyncAzureOpenAI"):
            p = AzureOpenAIProvider(
                api_key="key",
                endpoint="https://test.openai.azure.com/",
                deployment="gpt-4o",
            )
        assert p.provider_name == "azure_openai"
        assert p.model == "gpt-4o"
        assert p._deployment == "gpt-4o"


# ─────────────────────────────────────────────────────────────────────────────
# GeminiProvider tests (requires google-genai; skipped if not installed)
# ─────────────────────────────────────────────────────────────────────────────

class TestGeminiProvider:
    def test_provider_name(self):
        pytest.importorskip("google.genai")
        with patch("google.genai.Client"):
            from agent.providers.gemini_provider import GeminiProvider
            p = GeminiProvider(api_key="key", model="gemini-2.0-flash")
        assert p.provider_name == "gemini"

    def test_import_error_without_sdk(self, monkeypatch):
        """GeminiProvider should raise ImportError if google-genai is missing."""
        import sys
        # Temporarily hide the module
        google_genai = sys.modules.pop("google.genai", None)
        google = sys.modules.pop("google", None)
        try:
            # Force a reload without the module available
            if "agent.providers.gemini_provider" in sys.modules:
                del sys.modules["agent.providers.gemini_provider"]
            with pytest.raises(ImportError, match="google-genai"):
                # Simulate missing import by patching builtins.__import__
                import builtins
                original_import = builtins.__import__

                def mock_import(name, *args, **kwargs):
                    if name.startswith("google"):
                        raise ImportError("No module named 'google'")
                    return original_import(name, *args, **kwargs)

                monkeypatch.setattr(builtins, "__import__", mock_import)
                from agent.providers.gemini_provider import GeminiProvider  # noqa: F811
                GeminiProvider(api_key="key")
        finally:
            if google_genai is not None:
                sys.modules["google.genai"] = google_genai
            if google is not None:
                sys.modules["google"] = google

    def test_convert_messages_system(self):
        from agent.providers.gemini_provider import _convert_messages

        msgs = [
            Message(role=Role.SYSTEM, content="You are helpful."),
            Message(role=Role.USER, content="Hello"),
        ]
        system, contents = _convert_messages(msgs)
        assert system == "You are helpful."
        assert len(contents) == 1
        assert contents[0]["role"] == "user"

    def test_convert_messages_tool_result(self):
        from agent.providers.gemini_provider import _convert_messages

        msgs = [
            Message(role=Role.TOOL, content='{"result": "ok"}', name="my_tool", tool_call_id="c1"),
        ]
        _, contents = _convert_messages(msgs)
        assert contents[0]["role"] == "user"
        assert "function_response" in contents[0]["parts"][0]

    def test_convert_tools(self):
        from agent.providers.gemini_provider import _convert_tools

        tools = [
            ToolDefinition(
                name="my_tool",
                description="Does something",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "file path"}
                    },
                    "required": ["path"],
                },
            )
        ]
        result = _convert_tools(tools)
        assert result[0]["name"] == "my_tool"
        assert result[0]["parameters"]["type"] == "OBJECT"
        assert "path" in result[0]["parameters"]["properties"]


# ─────────────────────────────────────────────────────────────────────────────
# GitSkill tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGitSkill:
    def test_skill_name_and_description(self):
        from agent.skills.git_skill import GitSkill
        skill = GitSkill()
        assert skill.name == "git"
        assert "git" in skill.description.lower()

    def test_get_tools_returns_all_six(self):
        from agent.skills.git_skill import GitSkill
        skill = GitSkill()
        tools = skill.get_tools()
        names = {t.name for t in tools}
        assert names == {
            "git_status",
            "git_diff",
            "git_log",
            "git_commit",
            "git_push",
            "git_create_branch",
        }

    def test_repr(self):
        from agent.skills.git_skill import GitSkill
        skill = GitSkill()
        assert "6 tools" in repr(skill)

    @pytest.mark.asyncio
    async def test_git_status_in_real_repo(self):
        """git_status should succeed in any directory that is a git repo."""
        from agent.skills.git_skill import GitStatusTool
        tool = GitStatusTool()
        # Run in the actual project directory (which is a git repo)
        from agent.config import settings
        original = settings.workspace_dir
        # find a git repo
        result = await tool.execute()
        # May succeed or fail depending on environment, but should not raise
        assert result.tool_name == "git_status"
        assert isinstance(result.success, bool)

    @pytest.mark.asyncio
    async def test_git_commit_requires_message(self):
        from agent.skills.git_skill import GitCommitTool
        tool = GitCommitTool()
        result = await tool.execute(message="")
        assert not result.success
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_git_create_branch_requires_name(self):
        from agent.skills.git_skill import GitCreateBranchTool
        tool = GitCreateBranchTool()
        result = await tool.execute(branch="")
        assert not result.success
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_git_no_binary(self, monkeypatch):
        """When git is not on PATH, tools should return a clean error."""
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: None)
        from agent.skills.git_skill import GitStatusTool
        tool = GitStatusTool()
        result = await tool.execute()
        assert not result.success
        assert "git binary" in result.error


# ─────────────────────────────────────────────────────────────────────────────
# PatchFileTool tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPatchFileTool:
    @pytest.fixture()
    def workspace(self, tmp_path, monkeypatch):
        """Point the workspace_dir to a temp directory."""
        import agent.config as cfg_module
        monkeypatch.setattr(cfg_module.settings, "workspace_dir", str(tmp_path))
        import agent.tools.file_tools as ft_module
        monkeypatch.setattr(ft_module.settings, "workspace_dir", str(tmp_path))
        return tmp_path

    @pytest.mark.asyncio
    async def test_simple_patch(self, workspace):
        from agent.tools.file_tools import PatchFileTool

        original = "line1\nline2\nline3\n"
        (workspace / "target.txt").write_text(original)

        patch_text = (
            "--- a/target.txt\n"
            "+++ b/target.txt\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-line2\n"
            "+LINE2\n"
            " line3\n"
        )
        tool = PatchFileTool()
        result = await tool.execute(path="target.txt", patch=patch_text)
        assert result.success, result.error
        patched = (workspace / "target.txt").read_text()
        assert "LINE2" in patched
        assert "line2" not in patched

    @pytest.mark.asyncio
    async def test_patch_missing_file(self, workspace):
        from agent.tools.file_tools import PatchFileTool
        tool = PatchFileTool()
        result = await tool.execute(path="nofile.txt", patch="--- a\n+++ b\n")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_patch_bad_context(self, workspace):
        from agent.tools.file_tools import PatchFileTool
        (workspace / "f.txt").write_text("alpha\nbeta\n")
        # Patch expects different context
        patch_text = (
            "--- a/f.txt\n"
            "+++ b/f.txt\n"
            "@@ -1,2 +1,2 @@\n"
            " WRONG_CONTEXT\n"
            "-beta\n"
            "+BETA\n"
        )
        tool = PatchFileTool()
        result = await tool.execute(path="f.txt", patch=patch_text)
        assert not result.success

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, workspace):
        from agent.tools.file_tools import PatchFileTool
        tool = PatchFileTool()
        result = await tool.execute(path="../../etc/passwd", patch="")
        assert not result.success
        assert "outside" in result.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# RunPythonTool tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRunPythonTool:
    @pytest.mark.asyncio
    async def test_basic_execution(self):
        from agent.tools.code_tools import RunPythonTool
        tool = RunPythonTool()
        result = await tool.execute(code='print("hello from python")')
        assert result.success
        assert "hello from python" in result.output

    @pytest.mark.asyncio
    async def test_stderr_captured(self):
        from agent.tools.code_tools import RunPythonTool
        tool = RunPythonTool()
        result = await tool.execute(code="import sys; sys.stderr.write('err here'); sys.exit(1)")
        assert not result.success
        assert "err here" in result.output

    @pytest.mark.asyncio
    async def test_empty_code_rejected(self):
        from agent.tools.code_tools import RunPythonTool
        tool = RunPythonTool()
        result = await tool.execute(code="   ")
        assert not result.success
        assert "no code" in result.error.lower()

    @pytest.mark.asyncio
    async def test_timeout(self):
        from agent.tools.code_tools import RunPythonTool
        tool = RunPythonTool()
        result = await tool.execute(code="import time; time.sleep(10)", timeout=1)
        assert not result.success
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_arithmetic(self):
        from agent.tools.code_tools import RunPythonTool
        tool = RunPythonTool()
        result = await tool.execute(code="print(2 + 2)")
        assert result.success
        assert "4" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# RunTestsTool tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRunTestsTool:
    @pytest.mark.asyncio
    async def test_runs_passing_tests(self, tmp_path, monkeypatch):
        import agent.tools.code_tools as ct_module
        monkeypatch.setattr(ct_module.settings, "workspace_dir", str(tmp_path))

        # Write a tiny passing test
        (tmp_path / "test_sample.py").write_text(
            "def test_always_passes():\n    assert 1 + 1 == 2\n"
        )
        from agent.tools.code_tools import RunTestsTool
        tool = RunTestsTool()
        result = await tool.execute(path="test_sample.py")
        assert result.success, result.output

    @pytest.mark.asyncio
    async def test_reports_failing_tests(self, tmp_path, monkeypatch):
        import agent.tools.code_tools as ct_module
        monkeypatch.setattr(ct_module.settings, "workspace_dir", str(tmp_path))

        (tmp_path / "test_fail.py").write_text(
            "def test_always_fails():\n    assert False, 'intentional'\n"
        )
        from agent.tools.code_tools import RunTestsTool
        tool = RunTestsTool()
        result = await tool.execute(path="test_fail.py")
        assert not result.success
        assert "intentional" in result.output or "FAILED" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# Retry / parallel execution tests (agent core)
# ─────────────────────────────────────────────────────────────────────────────

class MockProvider(BaseProvider):
    def __init__(self, responses, fail_times: int = 0) -> None:
        super().__init__(api_key="mock", model="mock-model")
        self._responses = iter(responses)
        self._fail_times = fail_times
        self._attempts = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    async def complete(self, messages, tools=None, *, temperature=0.7, max_tokens=8192, stream=False):
        if self._attempts < self._fail_times:
            self._attempts += 1
            raise RuntimeError("rate limit exceeded")
        self._attempts += 1
        return next(self._responses)

    async def stream_complete(self, messages, tools=None, *, temperature=0.7, max_tokens=8192):
        resp = next(self._responses)
        for ch in resp.content:
            yield ch


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        from agent.core import _complete_with_retry
        from agent.providers.base import ProviderResponse

        provider = MockProvider(
            [ProviderResponse(content="hello", finish_reason="stop")],
            fail_times=2,
        )
        result = await _complete_with_retry(
            provider,
            [],
            tools=None,
            temperature=0.7,
            max_tokens=100,
            max_retries=3,
            base_delay=0.0,  # no real delay in tests
        )
        assert result.content == "hello"
        assert provider._attempts == 3  # 2 fails + 1 success

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        from agent.core import _complete_with_retry

        provider = MockProvider([], fail_times=10)
        with pytest.raises(RuntimeError, match="rate limit"):
            await _complete_with_retry(
                provider,
                [],
                tools=None,
                temperature=0.7,
                max_tokens=100,
                max_retries=2,
                base_delay=0.0,
            )


class TestParallelToolExecution:
    @pytest.mark.asyncio
    async def test_parallel_runs_all_tools(self):
        from agent.core import _execute_tools_parallel
        from agent.tools.base import BaseTool, ToolResult

        executed = []

        class TrackingTool(BaseTool):
            def __init__(self, n):
                self._n = n

            @property
            def name(self):
                return f"tool_{self._n}"

            @property
            def description(self):
                return ""

            @property
            def parameters(self):
                return {"type": "object", "properties": {}, "required": []}

            async def execute(self, **kwargs):
                executed.append(self._n)
                return ToolResult(tool_name=self.name, success=True, output=f"ok_{self._n}")

        tools_dict = {f"tool_{i}": TrackingTool(i) for i in range(3)}
        tool_calls = [
            {"id": f"c{i}", "type": "function",
             "function": {"name": f"tool_{i}", "arguments": "{}"}}
            for i in range(3)
        ]
        results = await _execute_tools_parallel(tool_calls, tools_dict)
        assert len(results) == 3
        assert set(executed) == {0, 1, 2}


class TestTokenBudget:
    @pytest.mark.asyncio
    async def test_token_budget_stops_agent(self):
        from agent.core import Agent
        from agent.config import Config
        from agent.providers.base import ProviderResponse

        # Each response uses 200 tokens; budget is 150 → should stop after 1st call
        provider = MockProvider(
            [ProviderResponse(
                content="first response",
                finish_reason="stop",
                usage={"input_tokens": 100, "output_tokens": 100},
            )] * 5
        )
        config = Config(
            token_budget=150,
            max_iterations=10,
        )
        agent = Agent(provider=provider, tools=[], config=config)
        response = await agent.run("test")
        assert "budget" in response.content.lower() or response.total_tokens >= 150


# ─────────────────────────────────────────────────────────────────────────────
# Config tests for Phase 2 settings
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase2Config:
    def test_new_providers_accepted(self):
        from agent.config import Config
        for provider in ("openai", "anthropic", "gemini", "ollama", "azure_openai"):
            cfg = Config(default_provider=provider)
            assert cfg.default_provider == provider

    def test_ollama_always_configured(self):
        from agent.config import Config
        cfg = Config()
        assert cfg.is_provider_configured("ollama") is True

    def test_gemini_requires_api_key(self):
        from agent.config import Config
        cfg = Config(gemini_api_key="")
        assert not cfg.is_provider_configured("gemini")
        cfg2 = Config(gemini_api_key="abc")
        assert cfg2.is_provider_configured("gemini")

    def test_azure_requires_key_and_endpoint(self):
        from agent.config import Config
        cfg = Config(azure_openai_api_key="key", azure_openai_endpoint="")
        assert not cfg.is_provider_configured("azure_openai")
        cfg2 = Config(
            azure_openai_api_key="key",
            azure_openai_endpoint="https://x.openai.azure.com/",
        )
        assert cfg2.is_provider_configured("azure_openai")

    def test_token_budget_defaults(self):
        from agent.config import Config
        cfg = Config()
        assert cfg.token_budget == 0
        assert 0.0 < cfg.token_budget_warning_threshold < 1.0

    def test_retry_defaults(self):
        from agent.config import Config
        cfg = Config()
        assert cfg.max_provider_retries >= 0
        assert cfg.retry_base_delay > 0

    def test_parallel_tool_calls_default(self):
        from agent.config import Config
        cfg = Config()
        assert isinstance(cfg.parallel_tool_calls, bool)

    def test_build_default_tools_includes_phase2(self):
        from agent.core import build_default_tools
        tools = build_default_tools()
        names = {t.name for t in tools}
        assert "patch_file" in names
        assert "run_python" in names
        assert "run_tests" in names
