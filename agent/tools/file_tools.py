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


class PatchFileTool(BaseTool):
    """Apply a unified diff (patch) to a file in the workspace."""

    @property
    def name(self) -> str:
        return "patch_file"

    @property
    def description(self) -> str:
        return (
            "Apply a unified diff patch to a file. "
            "The patch must be in unified diff format (as produced by `git diff` or `diff -u`). "
            "Returns the updated file content on success."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file to patch",
                },
                "patch": {
                    "type": "string",
                    "description": "Unified diff patch string",
                },
            },
            "required": ["path", "patch"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path: str = kwargs.get("path", "")
        patch_text: str = kwargs.get("patch", "")

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
            original = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )

        try:
            patched = _apply_unified_diff(original, patch_text)
        except ValueError as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Failed to apply patch: {exc}",
            )

        try:
            file_path.write_text(patched, encoding="utf-8")
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )

        return ToolResult(
            tool_name=self.name,
            success=True,
            output=f"Patched {raw_path} successfully.",
        )


def _apply_unified_diff(original: str, patch_text: str) -> str:
    """
    Apply a unified diff patch to *original* text.
    Returns the patched text or raises ValueError on failure.
    """
    import re

    orig_lines = original.splitlines(keepends=True)
    result_lines: list[str] = list(orig_lines)
    offset = 0  # cumulative line offset from previous hunks

    hunk_re = re.compile(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",
        re.MULTILINE,
    )

    # Split patch into individual hunks
    patch_lines = patch_text.splitlines(keepends=True)
    hunk_starts: list[int] = []
    for i, line in enumerate(patch_lines):
        if hunk_re.match(line):
            hunk_starts.append(i)

    if not hunk_starts:
        # No hunk headers – nothing to apply
        return original

    for hi, hstart in enumerate(hunk_starts):
        hend = hunk_starts[hi + 1] if hi + 1 < len(hunk_starts) else len(patch_lines)
        hunk_block = patch_lines[hstart:hend]
        header = hunk_block[0]
        m = hunk_re.match(header)
        if not m:
            continue

        orig_start = int(m.group(1)) - 1  # 0-based
        orig_count = int(m.group(2)) if m.group(2) is not None else 1

        # Build expected context + removals and the replacement
        context_and_removes: list[str] = []
        additions: list[str] = []
        for line in hunk_block[1:]:
            if line.startswith("-"):
                context_and_removes.append(line[1:])
            elif line.startswith("+"):
                additions.append(line[1:])
            elif line.startswith(" "):
                context_and_removes.append(line[1:])
                additions.append(line[1:])
            elif line.startswith("\\"):
                pass  # "\ No newline at end of file"

        insert_at = orig_start + offset
        # Validate that the existing lines match what the patch expects
        existing = result_lines[insert_at : insert_at + len(context_and_removes)]
        expected = context_and_removes
        if existing != expected:
            # Try a fuzzy match: find the block nearby (±5 lines)
            found = False
            for delta in range(1, 6):
                for sign in (+delta, -delta):
                    candidate = result_lines[
                        insert_at + sign : insert_at + sign + len(context_and_removes)
                    ]
                    if candidate == expected:
                        insert_at += sign
                        found = True
                        break
                if found:
                    break
            if not found:
                raise ValueError(
                    f"Hunk context does not match at line {orig_start + 1}. "
                    "Patch may be out of date."
                )

        # Replace the context_and_removes block with the additions block
        result_lines[insert_at : insert_at + len(context_and_removes)] = additions
        offset += len(additions) - len(context_and_removes)

    return "".join(result_lines)


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
