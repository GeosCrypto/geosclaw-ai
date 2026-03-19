"""
Web tools: search and fetch web pages.
"""
from __future__ import annotations

from typing import Any

import httpx

from agent.config import settings
from agent.tools.base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    """Search the web using DuckDuckGo."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for information using DuckDuckGo. "
            "Returns a list of search results with titles, URLs, and snippets."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 5,
                },
                "region": {
                    "type": "string",
                    "description": "Region for search results (e.g. 'us-en')",
                    "default": "wt-wt",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not settings.enable_web_search:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="Web search is disabled in the current configuration.",
            )

        query: str = kwargs.get("query", "")
        max_results: int = int(kwargs.get("max_results", settings.max_search_results))
        region: str = kwargs.get("region", "wt-wt")

        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, region=region, max_results=max_results):
                    results.append(r)

            if not results:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    output="No search results found.",
                )

            lines = []
            for i, r in enumerate(results, 1):
                lines.append(
                    f"{i}. {r.get('title', 'No title')}\n"
                    f"   URL: {r.get('href', '')}\n"
                    f"   {r.get('body', '')}"
                )
            return ToolResult(
                tool_name=self.name,
                success=True,
                output="\n\n".join(lines),
            )
        except ImportError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="duckduckgo-search package not installed.",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Search failed: {exc}",
            )


class WebFetchTool(BaseTool):
    """Fetch the content of a web page."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch the text content of a web page. "
            "Useful for reading documentation, articles, or any web content."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds",
                    "default": 15,
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return",
                    "default": 8000,
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        url: str = kwargs.get("url", "")
        timeout: int = int(kwargs.get("timeout", 15))
        max_length: int = int(kwargs.get("max_length", 8000))

        # Basic URL validation
        if not url.startswith(("http://", "https://")):
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="URL must start with http:// or https://",
            )

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "GeosclawAI/0.1 (AI research agent)"},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                text = response.text

                # Strip HTML tags minimally
                if "html" in content_type:
                    import re

                    text = re.sub(r"<script[\s\S]*?</\s*script(\s[^>]*)?>", "", text, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r"<style[\s\S]*?</\s*style(\s[^>]*)?>", "", text, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r"<[^>]+>", " ", text)
                    text = re.sub(r"\s+", " ", text).strip()

                if len(text) > max_length:
                    text = text[:max_length] + "\n\n[Content truncated]"

                return ToolResult(tool_name=self.name, success=True, output=text)
        except httpx.HTTPStatusError as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}",
            )
        except httpx.RequestError as exc:
            return ToolResult(
                tool_name=self.name, success=False, output="", error=str(exc)
            )
