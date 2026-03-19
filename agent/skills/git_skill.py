"""
Git skill – a collection of tools for common Git operations.

All git commands are run in the configured workspace directory.
These tools wrap the system `git` binary via subprocess; git must
be installed and available on PATH.

Usage::

    from agent.skills.git_skill import GitSkill
    agent.register_skill(GitSkill())
"""
from __future__ import annotations

import asyncio
import shutil
from typing import Any

from agent.config import settings
from agent.skills.base_skill import BaseSkill
from agent.tools.base import BaseTool, ToolResult


# ─────────────────────────────────────────────────────────────────────────────
# Shared helper
# ─────────────────────────────────────────────────────────────────────────────

async def _run_git(*args: str, cwd: str | None = None) -> ToolResult:
    """Run a git command and return a ToolResult."""
    if not shutil.which("git"):
        return ToolResult(
            tool_name="git",
            success=False,
            output="",
            error="git binary not found on PATH.",
        )
    workdir = cwd or settings.workspace_dir
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()
        if proc.returncode == 0:
            return ToolResult(tool_name="git", success=True, output=out or "(no output)")
        return ToolResult(
            tool_name="git",
            success=False,
            output=out,
            error=err or f"git exited with code {proc.returncode}",
        )
    except asyncio.TimeoutError:
        return ToolResult(
            tool_name="git",
            success=False,
            output="",
            error="git command timed out after 30 seconds.",
        )
    except OSError as exc:
        return ToolResult(tool_name="git", success=False, output="", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Individual git tools
# ─────────────────────────────────────────────────────────────────────────────

class GitStatusTool(BaseTool):
    """Show the working tree status."""

    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return "Show the working tree status (staged, unstaged, untracked files)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> ToolResult:
        result = await _run_git("status", "--short", "--branch")
        result.tool_name = self.name
        return result


class GitDiffTool(BaseTool):
    """Show changes between commits, working tree, or staged changes."""

    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return (
            "Show git diff. Use staged=true for staged changes. "
            "Optionally specify a file path."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "description": "Show staged (cached) diff instead of unstaged",
                    "default": False,
                },
                "path": {
                    "type": "string",
                    "description": "Limit diff to a specific file path (optional)",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        args = ["diff"]
        if kwargs.get("staged", False):
            args.append("--cached")
        path = kwargs.get("path", "")
        if path:
            args.extend(["--", path])
        result = await _run_git(*args)
        result.tool_name = self.name
        return result


class GitLogTool(BaseTool):
    """Show commit history."""

    @property
    def name(self) -> str:
        return "git_log"

    @property
    def description(self) -> str:
        return "Show the commit history (most recent commits first)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of commits to show (default: 10)",
                    "default": 10,
                },
                "oneline": {
                    "type": "boolean",
                    "description": "Show compact one-line format",
                    "default": True,
                },
                "path": {
                    "type": "string",
                    "description": "Limit history to commits touching this path (optional)",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        count = int(kwargs.get("count", 10))
        args = ["log", f"-{count}"]
        if kwargs.get("oneline", True):
            args.append("--oneline")
        path = kwargs.get("path", "")
        if path:
            args.extend(["--", path])
        result = await _run_git(*args)
        result.tool_name = self.name
        return result


class GitCommitTool(BaseTool):
    """Stage all changes and create a commit."""

    @property
    def name(self) -> str:
        return "git_commit"

    @property
    def description(self) -> str:
        return (
            "Stage all modified/new files (git add -A) and create a commit "
            "with the given message."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message",
                },
                "add_all": {
                    "type": "boolean",
                    "description": "Stage all changes before committing (default: true)",
                    "default": True,
                },
            },
            "required": ["message"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        message: str = kwargs.get("message", "")
        if not message:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="Commit message is required.",
            )

        if kwargs.get("add_all", True):
            add_result = await _run_git("add", "-A")
            if not add_result.success:
                add_result.tool_name = self.name
                return add_result

        result = await _run_git("commit", "-m", message)
        result.tool_name = self.name
        return result


class GitPushTool(BaseTool):
    """Push commits to the remote repository."""

    @property
    def name(self) -> str:
        return "git_push"

    @property
    def description(self) -> str:
        return "Push the current branch to the remote repository."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "remote": {
                    "type": "string",
                    "description": "Remote name (default: origin)",
                    "default": "origin",
                },
                "branch": {
                    "type": "string",
                    "description": "Branch to push (default: current branch)",
                },
                "set_upstream": {
                    "type": "boolean",
                    "description": "Set upstream tracking (-u flag)",
                    "default": False,
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        remote = kwargs.get("remote", "origin")
        branch = kwargs.get("branch", "")
        set_upstream = kwargs.get("set_upstream", False)

        args = ["push"]
        if set_upstream:
            args.append("-u")
        args.append(remote)
        if branch:
            args.append(branch)

        result = await _run_git(*args)
        result.tool_name = self.name
        return result


class GitCreateBranchTool(BaseTool):
    """Create and optionally check out a new branch."""

    @property
    def name(self) -> str:
        return "git_create_branch"

    @property
    def description(self) -> str:
        return "Create a new git branch, optionally checking it out immediately."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "branch": {
                    "type": "string",
                    "description": "Name for the new branch",
                },
                "checkout": {
                    "type": "boolean",
                    "description": "Check out the new branch after creating it (default: true)",
                    "default": True,
                },
                "from_ref": {
                    "type": "string",
                    "description": "Starting point (commit, tag, or branch) for the new branch",
                },
            },
            "required": ["branch"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        branch: str = kwargs.get("branch", "")
        if not branch:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="Branch name is required.",
            )

        checkout = kwargs.get("checkout", True)
        from_ref = kwargs.get("from_ref", "")

        if checkout:
            args = ["checkout", "-b", branch]
        else:
            args = ["branch", branch]

        if from_ref:
            args.append(from_ref)

        result = await _run_git(*args)
        result.tool_name = self.name
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Skill bundle
# ─────────────────────────────────────────────────────────────────────────────

class GitSkill(BaseSkill):
    """
    Git skill – provides tools for common Git operations.

    Tools provided:
    - git_status     : show working tree status
    - git_diff       : show unstaged or staged changes
    - git_log        : show commit history
    - git_commit     : stage all and commit
    - git_push       : push to remote
    - git_create_branch : create a new branch
    """

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return "Git operations: status, diff, log, commit, push, branch."

    def get_tools(self) -> list[BaseTool]:
        return [
            GitStatusTool(),
            GitDiffTool(),
            GitLogTool(),
            GitCommitTool(),
            GitPushTool(),
            GitCreateBranchTool(),
        ]
