"""
Core agent implementation – the heart of GeosclawAI.

The agent runs an agentic loop:
  1. Send the current conversation to the AI provider.
  2. If the model returns tool calls, execute each tool.
  3. Add the tool results back to the conversation.
  4. Repeat until the model stops calling tools or max_iterations is reached.
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

            response = await self._provider.complete(
                messages,
                tools=tool_definitions if tool_definitions else None,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            )

            total_tokens += sum(response.usage.values())

            # If there are tool calls, execute them
            if response.tool_calls:
                self._memory.add_assistant(
                    content=response.content,
                    tool_calls=response.tool_calls,
                )

                for tc in response.tool_calls:
                    tool_name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]
                    call_id = tc["id"]

                    try:
                        arguments = json.loads(raw_args)
                    except json.JSONDecodeError:
                        arguments = {}

                    tool_calls_made.append(
                        {"tool": tool_name, "arguments": arguments}
                    )

                    if on_tool_call:
                        on_tool_call(tool_name, arguments)

                    tool = self._tools.get(tool_name)
                    if tool is None:
                        result_content = f"Error: unknown tool '{tool_name}'"
                    else:
                        try:
                            result = await tool.execute(**arguments)
                            result_content = result.to_message_content()
                        except Exception as exc:
                            result_content = f"Tool execution error: {exc}"

                    self._memory.add_tool_result(
                        tool_call_id=call_id,
                        content=result_content,
                        name=tool_name,
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
            response = await self._provider.complete(
                messages,
                tools=tool_definitions if tool_definitions else None,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            )

            if response.tool_calls:
                self._memory.add_assistant(
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
                for tc in response.tool_calls:
                    tool_name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]
                    call_id = tc["id"]
                    try:
                        arguments = json.loads(raw_args)
                    except json.JSONDecodeError:
                        arguments = {}

                    if on_tool_call:
                        on_tool_call(tool_name, arguments)

                    tool = self._tools.get(tool_name)
                    if tool is None:
                        result_content = f"Error: unknown tool '{tool_name}'"
                    else:
                        try:
                            result = await tool.execute(**arguments)
                            result_content = result.to_message_content()
                        except Exception as exc:
                            result_content = f"Tool execution error: {exc}"

                    self._memory.add_tool_result(
                        tool_call_id=call_id,
                        content=result_content,
                        name=tool_name,
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
    )
    from agent.tools.shell_tools import ShellTool
    from agent.tools.web_tools import WebSearchTool, WebFetchTool
    from agent.tools.code_tools import CodeAnalysisTool, CodeFormatTool
    from agent.tools.memory_tools import SaveMemoryTool, RecallMemoryTool

    tools: list[BaseTool] = [
        ReadFileTool(),
        WriteFileTool(),
        ListFilesTool(),
        SearchFilesTool(),
        DeleteFileTool(),
        CreateDirectoryTool(),
        CodeAnalysisTool(),
        CodeFormatTool(),
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
    else:
        from agent.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=cfg.openai_api_key,
            model=cfg.openai_model,
            base_url=cfg.openai_base_url,
        )
