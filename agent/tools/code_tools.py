"""
Code analysis and formatting tools.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.config import settings
from agent.tools.base import BaseTool, ToolResult
from agent.tools.file_tools import _safe_path


class CodeAnalysisTool(BaseTool):
    """Analyse a code file: count lines, identify language, list definitions."""

    @property
    def name(self) -> str:
        return "analyze_code"

    @property
    def description(self) -> str:
        return (
            "Analyse a source code file. "
            "Returns language, line count, function/class definitions, imports, "
            "and a complexity summary."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the source file",
                }
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import re

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

        if not file_path.is_file():
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"File not found: {raw_path}",
            )

        size_kb = file_path.stat().st_size / 1024
        if size_kb > settings.max_file_size_kb:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"File too large ({size_kb:.1f} KB).",
            )

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )

        lines = content.splitlines()
        language = _detect_language(file_path)

        # Extract definitions
        functions: list[str] = []
        classes: list[str] = []
        imports: list[str] = []

        for line in lines:
            stripped = line.strip()
            if language == "Python":
                if re.match(r"^def\s+\w+", stripped):
                    match = re.match(r"^def\s+(\w+)", stripped)
                    if match:
                        functions.append(match.group(1))
                elif re.match(r"^class\s+\w+", stripped):
                    match = re.match(r"^class\s+(\w+)", stripped)
                    if match:
                        classes.append(match.group(1))
                elif stripped.startswith(("import ", "from ")):
                    imports.append(stripped)
            elif language in ("JavaScript", "TypeScript"):
                if re.match(r"^(export\s+)?(async\s+)?function\s+\w+", stripped):
                    match = re.search(r"function\s+(\w+)", stripped)
                    if match:
                        functions.append(match.group(1))
                elif re.match(r"^(export\s+)?(default\s+)?class\s+\w+", stripped):
                    match = re.search(r"class\s+(\w+)", stripped)
                    if match:
                        classes.append(match.group(1))
                elif re.match(r"^(import|const\s+\w+\s*=\s*require)", stripped):
                    imports.append(stripped)

        summary_parts = [
            f"Language: {language}",
            f"Lines: {len(lines)}",
            f"Characters: {len(content)}",
        ]
        if classes:
            summary_parts.append(f"Classes ({len(classes)}): {', '.join(classes)}")
        if functions:
            summary_parts.append(
                f"Functions ({len(functions)}): {', '.join(functions[:20])}"
                + (" ..." if len(functions) > 20 else "")
            )
        if imports:
            summary_parts.append(f"Imports ({len(imports)}): first 5 shown")
            summary_parts.extend(f"  {imp}" for imp in imports[:5])

        return ToolResult(
            tool_name=self.name,
            success=True,
            output="\n".join(summary_parts),
        )


def _detect_language(path: Path) -> str:
    ext_map = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".jsx": "JavaScript",
        ".java": "Java",
        ".go": "Go",
        ".rs": "Rust",
        ".cpp": "C++",
        ".c": "C",
        ".cs": "C#",
        ".rb": "Ruby",
        ".php": "PHP",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".sh": "Shell",
        ".bash": "Shell",
        ".html": "HTML",
        ".css": "CSS",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".md": "Markdown",
        ".sql": "SQL",
    }
    return ext_map.get(path.suffix.lower(), "Unknown")


class CodeFormatTool(BaseTool):
    """Format a Python file using Black (if available)."""

    @property
    def name(self) -> str:
        return "format_code"

    @property
    def description(self) -> str:
        return (
            "Format a Python source file using Black. "
            "Returns the formatted code as a string."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the Python file to format",
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

        if not file_path.is_file():
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"File not found: {raw_path}",
            )

        try:
            import black

            content = file_path.read_text(encoding="utf-8")
            mode = black.Mode()
            formatted = black.format_str(content, mode=mode)
            file_path.write_text(formatted, encoding="utf-8")
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=f"Formatted {raw_path} successfully.",
            )
        except ImportError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="Black is not installed. Run: pip install black",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )


class RunPythonTool(BaseTool):
    """Execute a Python code snippet and return stdout/stderr."""

    @property
    def name(self) -> str:
        return "run_python"

    @property
    def description(self) -> str:
        return (
            "Execute a Python code snippet in a subprocess and return its output. "
            "Useful for calculations, data processing, or testing small code snippets."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds (default: 30)",
                    "default": 30,
                },
            },
            "required": ["code"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import asyncio
        import sys

        code: str = kwargs.get("code", "")
        timeout: int = int(kwargs.get("timeout", 30))

        if not code.strip():
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="No code provided.",
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=settings.workspace_dir,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    output="",
                    error=f"Code execution timed out after {timeout}s.",
                )

            out = stdout.decode(errors="replace")
            err = stderr.decode(errors="replace")
            combined = ""
            if out:
                combined += out
            if err:
                combined += ("\n" if combined else "") + "[stderr]\n" + err

            return ToolResult(
                tool_name=self.name,
                success=(proc.returncode == 0),
                output=combined.strip() or "(no output)",
                error=None if proc.returncode == 0 else f"Exited with code {proc.returncode}",
            )
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )


class RunTestsTool(BaseTool):
    """Run the project's test suite using pytest and return results."""

    @property
    def name(self) -> str:
        return "run_tests"

    @property
    def description(self) -> str:
        return (
            "Run pytest in the workspace (or a specific path) and return a "
            "structured summary of test results including pass/fail counts and "
            "failure details."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to test file/directory (default: workspace root)",
                    "default": "",
                },
                "args": {
                    "type": "string",
                    "description": "Extra pytest arguments (e.g. '-v -k test_foo')",
                    "default": "",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Overall timeout in seconds (default: 120)",
                    "default": 120,
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import asyncio
        import shlex
        import shutil
        import sys

        test_path: str = kwargs.get("path", "")
        extra_args: str = kwargs.get("args", "")
        timeout: int = int(kwargs.get("timeout", 120))

        if not shutil.which("pytest") and not _has_pytest():
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="pytest is not installed. Run: pip install pytest",
            )

        cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q"]
        if test_path:
            cmd.append(test_path)
        if extra_args:
            cmd.extend(shlex.split(extra_args))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=settings.workspace_dir,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    output="",
                    error=f"Test run timed out after {timeout}s.",
                )

            out = stdout.decode(errors="replace")
            err = stderr.decode(errors="replace")
            combined = out
            if err.strip():
                combined += "\n[stderr]\n" + err

            return ToolResult(
                tool_name=self.name,
                success=(proc.returncode == 0),
                output=combined.strip() or "(no output)",
                error=None if proc.returncode == 0 else f"Tests failed (exit code {proc.returncode})",
            )
        except OSError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )


def _has_pytest() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("pytest") is not None
    except Exception:
        return False
