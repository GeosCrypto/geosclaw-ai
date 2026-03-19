"""
Shell execution tool.
Runs commands in a subprocess with timeout and output capture.
"""
from __future__ import annotations

import asyncio
import os
import shlex
from typing import Any

from agent.config import settings
from agent.tools.base import BaseTool, ToolResult


class ShellTool(BaseTool):
    """Execute a shell command and return its output."""

    @property
    def name(self) -> str:
        return "run_shell"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command in the workspace directory. "
            "Returns stdout, stderr, and the exit code. "
            "Use this to run tests, install packages, compile code, etc."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default from config)",
                },
                "cwd": {
                    "type": "string",
                    "description": (
                        "Working directory relative to workspace "
                        "(default: workspace root)"
                    ),
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not settings.allow_shell:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="Shell execution is disabled in the current configuration.",
            )

        command: str = kwargs.get("command", "")
        timeout: int = int(kwargs.get("timeout", settings.shell_timeout))
        cwd_rel: str = kwargs.get("cwd", ".")

        workspace = os.path.abspath(settings.workspace_dir)
        cwd = os.path.normpath(os.path.join(workspace, cwd_rel))

        # Prevent path traversal in cwd
        if not cwd.startswith(workspace):
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"cwd '{cwd_rel}' is outside the workspace.",
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=5)
                except asyncio.TimeoutError:
                    pass  # Process cleanup timed out – ignore
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout}s: {command}",
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            returncode = proc.returncode or 0

            output_parts = []
            if stdout:
                output_parts.append(f"STDOUT:\n{stdout}")
            if stderr:
                output_parts.append(f"STDERR:\n{stderr}")
            output_parts.append(f"Exit code: {returncode}")

            return ToolResult(
                tool_name=self.name,
                success=(returncode == 0),
                output="\n".join(output_parts),
                error=None if returncode == 0 else f"Command exited with code {returncode}",
            )
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )
