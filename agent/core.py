"""
Core agent implementation – the heart of GeosclawAI.

The agent runs an agentic loop:
  1. Send the current conversation to the AI provider.
  2. If the model returns tool calls, execute each tool (in parallel when enabled).
  3. Add the tool results back to the conversation.
  4. Repeat until the model stops calling tools or max_iterations is reached.

Phase 2 additions:
  - Exponential-backoff retry on transient provider errors
  - Parallel tool-call execution via asyncio.gather
  - Token budget tracking and warnings
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable

from agent.config import Config, settings as default_settings
from agent.memory import ConversationMemory
from agent.providers.base import BaseProvider, Message, Role, ToolDefinition
from agent.skills.base_skill import BaseSkill
from agent.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Default system prompt
DEFAULT_SYSTEM_PROMPT = """\
You are GeosclawAI, a powerful AI assistant and autonomous agent.

You have access to a suite of tools that let you:
- Read, write, search, and manage files in the workspace
- Execute shell commands to run code, install packages, and automate tasks
- Search the web for up-to-date information
- Fetch web pages and extract their content
- Analyse source code files
- Save and recall important notes across sessions

Guidelines:
- Be thorough and accurate. Verify your work by reading files and running tests.
- Break complex tasks into smaller steps and execute them methodically.
- Always explain what you are doing and why.
- If you encounter an error, diagnose it carefully and try to fix it.
- Prefer making targeted edits over rewriting entire files.
- Ask for clarification when a requirement is ambiguous.
"""


class AgentResponse:
    """Encapsulates a complete agent response including tool calls."""

    def __init__(
        self,
        content: str,
        tool_calls_made: list[dict[str, Any]] | None = None,
        iterations: int = 0,
        total_tokens: int = 0,
    ) -> None:
        self.content = content
        self.tool_calls_made = tool_calls_made or []
        self.iterations = iterations
        self.total_tokens = total_tokens


class Agent:
    """
    The main GeosclawAI agent class.

    Usage::

        agent = Agent(provider=provider, tools=[...])
        response = await agent.run("Write a Python script that prints 'hello world'")
        print(response.content)
    """

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[BaseTool] | None = None,
        memory: ConversationMemory | None = None,
        config: Config | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._provider = provider
        self._tools: dict[str, BaseTool] = {t.name: t for t in (tools or [])}
        self._memory = memory or ConversationMemory(
            system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT
        )
        self._config = config or default_settings

        # If a custom system prompt is given and memory was freshly created, set it
        if system_prompt and not memory:
            self._memory.set_system_prompt(system_prompt)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @property
    def tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    @property
    def memory(self) -> ConversationMemory:
        return self._memory

    def add_tool(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def remove_tool(self, name: str) -> None:
        self._tools.pop(name, None)

    async def run(
        self,
        message: str,
        *,
        on_token: Callable[[str], None] | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> AgentResponse:
        """
        Send *message* to the agent and return an AgentResponse.

        Parameters
        ----------
        message:
            The user message.
        on_token:
            Optional callback invoked for each streamed token (when streaming
            is enabled).
        on_tool_call:
            Optional callback invoked before each tool execution with
            (tool_name, arguments).
        """
        self._memory.add_user(message)

        iterations = 0
        total_tokens = 0
        tool_calls_made: list[dict[str, Any]] = []

        tool_definitions = [t.to_definition() for t in self._tools.values()]

        while iterations < self._config.max_iterations:
            iterations += 1
            messages = self._memory.get_messages(include_system=True)

            response = await _complete_with_retry(
                self._provider,
                messages,
                tools=tool_definitions if tool_definitions else None,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
                max_retries=self._config.max_provider_retries,
                base_delay=self._config.retry_base_delay,
            )

            step_tokens = sum(response.usage.values())
            total_tokens += step_tokens

            # Token budget check
            if self._config.token_budget > 0:
                if total_tokens >= self._config.token_budget:
                    final_content = (
                        f"Token budget of {self._config.token_budget:,} tokens exhausted "
                        f"({total_tokens:,} used). Task may be incomplete."
                    )
                    self._memory.add_assistant(content=final_content)
                    return AgentResponse(
                        content=final_content,
                        tool_calls_made=tool_calls_made,
                        iterations=iterations,
                        total_tokens=total_tokens,
                    )
                warning_threshold = int(
                    self._config.token_budget * self._config.token_budget_warning_threshold
                )
                if total_tokens >= warning_threshold:
                    logger.warning(
                        "Token budget warning: %d / %d tokens used (%.0f%%)",
                        total_tokens,
                        self._config.token_budget,
                        100 * total_tokens / self._config.token_budget,
                    )

            # If there are tool calls, execute them
            if response.tool_calls:
                self._memory.add_assistant(
                    content=response.content,
                    tool_calls=response.tool_calls,
                )

                if self._config.parallel_tool_calls and len(response.tool_calls) > 1:
                    # Execute all tool calls in parallel
                    results = await _execute_tools_parallel(
                        response.tool_calls,
                        self._tools,
                        on_tool_call=on_tool_call,
                    )
                else:
                    # Sequential execution (default when single tool or parallel disabled)
                    results = await _execute_tools_sequential(
                        response.tool_calls,
                        self._tools,
                        on_tool_call=on_tool_call,
                    )

                for tc, result_content in results:
                    tool_calls_made.append(
                        {"tool": tc["function"]["name"], "arguments": _parse_args(tc)}
                    )
                    self._memory.add_tool_result(
                        tool_call_id=tc["id"],
                        content=result_content,
                        name=tc["function"]["name"],
                    )
            else:
                # No tool calls – the model is done
                self._memory.add_assistant(content=response.content)

                if on_token and response.content:
                    on_token(response.content)

                return AgentResponse(
                    content=response.content,
                    tool_calls_made=tool_calls_made,
                    iterations=iterations,
                    total_tokens=total_tokens,
                )

        # Max iterations reached
        final_content = (
            "I reached the maximum number of iterations. "
            "The task may be incomplete. Please review the work done so far."
        )
        self._memory.add_assistant(content=final_content)
        return AgentResponse(
            content=final_content,
            tool_calls_made=tool_calls_made,
            iterations=iterations,
            total_tokens=total_tokens,
        )

    async def stream(
        self,
        message: str,
        *,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> AsyncIterator[str]:
        """
        Like :meth:`run` but yields text tokens as they are generated.
        Tool calls are executed silently in the background.
        """
        self._memory.add_user(message)
        tool_definitions = [t.to_definition() for t in self._tools.values()]

        for _ in range(self._config.max_iterations):
            messages = self._memory.get_messages(include_system=True)

            # First do a non-streaming call to check for tool calls
            response = await _complete_with_retry(
                self._provider,
                messages,
                tools=tool_definitions if tool_definitions else None,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
                max_retries=self._config.max_provider_retries,
                base_delay=self._config.retry_base_delay,
            )

            if response.tool_calls:
                self._memory.add_assistant(
                    content=response.content,
                    tool_calls=response.tool_calls,
                )

                if self._config.parallel_tool_calls and len(response.tool_calls) > 1:
                    results = await _execute_tools_parallel(
                        response.tool_calls,
                        self._tools,
                        on_tool_call=on_tool_call,
                    )
                else:
                    results = await _execute_tools_sequential(
                        response.tool_calls,
                        self._tools,
                        on_tool_call=on_tool_call,
                    )

                for tc, result_content in results:
                    self._memory.add_tool_result(
                        tool_call_id=tc["id"],
                        content=result_content,
                        name=tc["function"]["name"],
                    )
            else:
                # Stream the final answer
                self._memory.add_assistant(content=response.content)
                # Yield the response content in chunks for a streaming feel
                chunk_size = 20
                text = response.content
                for i in range(0, len(text), chunk_size):
                    yield text[i : i + chunk_size]
                    await asyncio.sleep(0)
                return

        yield (
            "\n\nMax iterations reached. The task may be incomplete."
        )

    def register_skill(self, skill: "BaseSkill") -> None:
        """Register all tools from a skill bundle."""
        for tool in skill.get_tools():
            self.add_tool(tool)

    def clear_history(self) -> None:
        """Reset conversation history."""
        self._memory.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args(tc: dict[str, Any]) -> dict[str, Any]:
    """Parse tool-call arguments from JSON string to dict."""
    try:
        return json.loads(tc["function"]["arguments"])
    except (json.JSONDecodeError, KeyError):
        return {}


async def _execute_single_tool(
    tc: dict[str, Any],
    tools: dict[str, BaseTool],
    on_tool_call: Callable[[str, dict[str, Any]], None] | None,
) -> tuple[dict[str, Any], str]:
    """Execute a single tool call and return (tc, result_content)."""
    tool_name = tc["function"]["name"]
    arguments = _parse_args(tc)

    if on_tool_call:
        on_tool_call(tool_name, arguments)

    tool = tools.get(tool_name)
    if tool is None:
        return tc, f"Error: unknown tool '{tool_name}'"
    try:
        result = await tool.execute(**arguments)
        return tc, result.to_message_content()
    except Exception as exc:
        return tc, f"Tool execution error: {exc}"


async def _execute_tools_sequential(
    tool_calls: list[dict[str, Any]],
    tools: dict[str, BaseTool],
    on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
) -> list[tuple[dict[str, Any], str]]:
    """Execute tool calls one at a time, in order."""
    results: list[tuple[dict[str, Any], str]] = []
    for tc in tool_calls:
        results.append(await _execute_single_tool(tc, tools, on_tool_call))
    return results


async def _execute_tools_parallel(
    tool_calls: list[dict[str, Any]],
    tools: dict[str, BaseTool],
    on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
) -> list[tuple[dict[str, Any], str]]:
    """Execute all tool calls concurrently using asyncio.gather."""
    tasks = [_execute_single_tool(tc, tools, on_tool_call) for tc in tool_calls]
    return list(await asyncio.gather(*tasks))


async def _complete_with_retry(
    provider: BaseProvider,
    messages: list[Message],
    *,
    tools: list[ToolDefinition] | None,
    temperature: float,
    max_tokens: int,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """
    Call provider.complete() with exponential-backoff retry on transient errors.

    Retries on:
      - rate-limit errors (429-like)
      - service-unavailable / overload errors (503/529-like)
      - generic connection errors
    """
    from agent.providers.base import ProviderResponse  # avoid circular at top level

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await provider.complete(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            err_str = str(exc).lower()
            # Only retry on transient / rate-limit errors
            is_transient = any(
                keyword in err_str
                for keyword in (
                    "rate limit",
                    "rate_limit",
                    "ratelimit",
                    "too many requests",
                    "overloaded",
                    "service unavailable",
                    "timeout",
                    "connection",
                    "503",
                    "529",
                    "429",
                )
            )
            if not is_transient or attempt >= max_retries:
                raise
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "Provider error (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    # Should never reach here, but satisfy the type checker
    raise last_exc or RuntimeError("provider.complete failed after retries")


def build_default_tools(config: Config | None = None) -> list[BaseTool]:
    """Return a standard set of tools configured for the given settings."""
    cfg = config or default_settings
    from agent.tools.file_tools import (
        ReadFileTool,
        WriteFileTool,
        ListFilesTool,
        SearchFilesTool,
        DeleteFileTool,
        CreateDirectoryTool,
        PatchFileTool,
    )
    from agent.tools.shell_tools import ShellTool
    from agent.tools.web_tools import WebSearchTool, WebFetchTool
    from agent.tools.code_tools import (
        CodeAnalysisTool,
        CodeFormatTool,
        RunPythonTool,
        RunTestsTool,
    )
    from agent.tools.memory_tools import SaveMemoryTool, RecallMemoryTool

    tools: list[BaseTool] = [
        ReadFileTool(),
        WriteFileTool(),
        ListFilesTool(),
        SearchFilesTool(),
        DeleteFileTool(),
        CreateDirectoryTool(),
        PatchFileTool(),
        CodeAnalysisTool(),
        CodeFormatTool(),
        RunPythonTool(),
        RunTestsTool(),
        SaveMemoryTool(),
        RecallMemoryTool(),
    ]

    if cfg.allow_shell:
        tools.append(ShellTool())

    if cfg.enable_web_search:
        tools.append(WebSearchTool())
        tools.append(WebFetchTool())

    return tools


def create_agent(
    provider: BaseProvider | None = None,
    tools: list[BaseTool] | None = None,
    system_prompt: str | None = None,
    config: Config | None = None,
) -> Agent:
    """
    Convenience factory that creates a fully-configured Agent.

    If no *provider* is given the default provider from settings is used.
    """
    cfg = config or default_settings

    if provider is None:
        provider = _make_default_provider(cfg)

    if tools is None:
        tools = build_default_tools(cfg)

    return Agent(
        provider=provider,
        tools=tools,
        system_prompt=system_prompt,
        config=cfg,
    )


def _make_default_provider(cfg: Config) -> BaseProvider:
    """Instantiate the default provider based on configuration."""
    if cfg.default_provider == "anthropic":
        from agent.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=cfg.anthropic_api_key,
            model=cfg.anthropic_model,
        )
    elif cfg.default_provider == "gemini":
        from agent.providers.gemini_provider import GeminiProvider

        return GeminiProvider(
            api_key=cfg.gemini_api_key,
            model=cfg.gemini_model,
        )
    elif cfg.default_provider == "ollama":
        from agent.providers.ollama_provider import OllamaProvider

        return OllamaProvider(
            model=cfg.ollama_model,
            base_url=cfg.ollama_base_url,
        )
    elif cfg.default_provider == "azure_openai":
        from agent.providers.azure_provider import AzureOpenAIProvider

        return AzureOpenAIProvider(
            api_key=cfg.azure_openai_api_key,
            endpoint=cfg.azure_openai_endpoint,
            deployment=cfg.azure_openai_deployment,
            api_version=cfg.azure_openai_api_version,
        )
    else:
        from agent.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=cfg.openai_api_key,
            model=cfg.openai_model,
            base_url=cfg.openai_base_url,
        )
