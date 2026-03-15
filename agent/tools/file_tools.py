"""
File system tools: read, write, list, search, delete, mkdir.
All paths are resolved relative to the configured workspace directory and
are validated to prevent path-traversal attacks.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent.config import settings
from agent.tools.base import BaseTool, ToolResult


def _safe_path(raw: str) -> Path:
    """
    Resolve *raw* against the workspace dir and raise if the result
    escapes the workspace (path-traversal guard).
    """
    workspace = Path(settings.workspace_dir).resolve()
    target = (workspace / raw).resolve()
    # Ensure the resolved path is inside the workspace
    target.relative_to(workspace)
    return target


class ReadFileTool(BaseTool):
    """Read the contents of a file."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the full contents of a file. "
            "Returns the file content as a string."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file (within workspace)",
                }
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path: str = kwargs.get("path", "")
        try:
            file_path = _safe_path(raw_path)
        except ValueError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Path '{raw_path}' is outside the workspace.",
            )

        if not file_path.exists():
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"File not found: {raw_path}",
            )
        if not file_path.is_file():
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Path is not a file: {raw_path}",
            )

        size_kb = file_path.stat().st_size / 1024
        if size_kb > settings.max_file_size_kb:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=(
                    f"File too large ({size_kb:.1f} KB). "
                    f"Limit is {settings.max_file_size_kb} KB."
                ),
            )

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            return ToolResult(tool_name=self.name, success=True, output=content)
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )


class WriteFileTool(BaseTool):
    """Write content to a file (creating it if necessary)."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. "
            "Creates the file (and any parent directories) if they don't exist. "
            "Overwrites existing content unless append=true."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write",
                },
                "append": {
                    "type": "boolean",
                    "description": "Append to existing file instead of overwriting",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path: str = kwargs.get("path", "")
        content: str = kwargs.get("content", "")
        append: bool = kwargs.get("append", False)

        try:
            file_path = _safe_path(raw_path)
        except ValueError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Path '{raw_path}' is outside the workspace.",
            )

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with file_path.open(mode, encoding="utf-8") as fh:
                fh.write(content)
            action = "Appended to" if append else "Wrote"
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=f"{action} {raw_path} ({len(content)} chars)",
            )
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )


class ListFilesTool(BaseTool):
    """List files and directories in a directory."""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return "List files and directories at the given path."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to list (default: workspace root)",
                    "default": ".",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List files recursively",
                    "default": False,
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path: str = kwargs.get("path", ".")
        recursive: bool = kwargs.get("recursive", False)

        try:
            dir_path = _safe_path(raw_path)
        except ValueError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Path '{raw_path}' is outside the workspace.",
            )

        if not dir_path.exists():
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Directory not found: {raw_path}",
            )

        try:
            workspace = Path(settings.workspace_dir).resolve()
            if recursive:
                entries = sorted(dir_path.rglob("*"))
            else:
                entries = sorted(dir_path.iterdir())

            lines = []
            for entry in entries:
                rel = entry.relative_to(workspace)
                tag = "/" if entry.is_dir() else ""
                lines.append(f"{rel}{tag}")

            return ToolResult(
                tool_name=self.name,
                success=True,
                output="\n".join(lines) if lines else "(empty directory)",
            )
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )


class SearchFilesTool(BaseTool):
    """Search for a pattern (text or regex) across files in the workspace."""

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return (
            "Search for a text pattern inside files. "
            "Returns matching file paths and lines."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text or regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: workspace root)",
                    "default": ".",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.py')",
                    "default": "*",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Case-sensitive search",
                    "default": True,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 50,
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import re

        pattern: str = kwargs.get("pattern", "")
        raw_path: str = kwargs.get("path", ".")
        file_pattern: str = kwargs.get("file_pattern", "*")
        case_sensitive: bool = kwargs.get("case_sensitive", True)
        max_results: int = int(kwargs.get("max_results", 50))

        try:
            search_dir = _safe_path(raw_path)
        except ValueError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Path '{raw_path}' is outside the workspace.",
            )

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(pattern, flags)
        except re.error as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Invalid regex: {exc}",
            )

        workspace = Path(settings.workspace_dir).resolve()
        results: list[str] = []

        for file_path in search_dir.rglob(file_pattern):
            if not file_path.is_file():
                continue
            size_kb = file_path.stat().st_size / 1024
            if size_kb > settings.max_file_size_kb:
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
                for lineno, line in enumerate(text.splitlines(), 1):
                    if compiled.search(line):
                        rel = file_path.relative_to(workspace)
                        results.append(f"{rel}:{lineno}: {line.strip()}")
                        if len(results) >= max_results:
                            break
            except OSError:
                continue
            if len(results) >= max_results:
                break

        if not results:
            return ToolResult(
                tool_name=self.name,
                success=True,
                output="No matches found.",
            )
        return ToolResult(
            tool_name=self.name,
            success=True,
            output="\n".join(results),
        )


class DeleteFileTool(BaseTool):
    """Delete a file from the workspace."""

    @property
    def name(self) -> str:
        return "delete_file"

    @property
    def description(self) -> str:
        return "Delete a file from the workspace."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file to delete",
                }
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path: str = kwargs.get("path", "")
        try:
            file_path = _safe_path(raw_path)
        except ValueError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Path '{raw_path}' is outside the workspace.",
            )

        if not file_path.exists():
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"File not found: {raw_path}",
            )

        try:
            file_path.unlink()
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=f"Deleted {raw_path}",
            )
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )


class CreateDirectoryTool(BaseTool):
    """Create a directory (and any necessary parents)."""

    @property
    def name(self) -> str:
        return "create_directory"

    @property
    def description(self) -> str:
        return "Create a directory (and any necessary parent directories)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the directory to create",
                }
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path: str = kwargs.get("path", "")
        try:
            dir_path = _safe_path(raw_path)
        except ValueError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Path '{raw_path}' is outside the workspace.",
            )

        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=f"Created directory {raw_path}",
            )
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )
