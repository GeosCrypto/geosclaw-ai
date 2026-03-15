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
