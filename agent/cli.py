"""
Command-line interface for GeosclawAI.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional

import click
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.spinner import Spinner
from rich.text import Text

console = Console()


BANNER = """
[bold cyan]
   ██████╗ ███████╗ ██████╗ ███████╗ ██████╗██╗      █████╗ ██╗    ██╗
  ██╔════╝ ██╔════╝██╔═══██╗██╔════╝██╔════╝██║     ██╔══██╗██║    ██║
  ██║  ███╗█████╗  ██║   ██║███████╗██║     ██║     ███████║██║ █╗ ██║
  ██║   ██║██╔══╝  ██║   ██║╚════██║██║     ██║     ██╔══██║██║███╗██║
  ╚██████╔╝███████╗╚██████╔╝███████║╚██████╗███████╗██║  ██║╚███╔███╔╝
   ╚═════╝ ╚══════╝ ╚═════╝ ╚══════╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
[/bold cyan]
[bold white]          GeosclawAI – Your Autonomous AI Agent[/bold white]
"""


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version="0.1.0", prog_name="geosclaw")
def cli(ctx: click.Context) -> None:
    """GeosclawAI – A powerful autonomous AI agent."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(chat)


@cli.command()
@click.option(
    "--provider",
    "-p",
    type=click.Choice(["anthropic", "openai"]),
    default=None,
    help="AI provider to use (overrides config)",
)
@click.option(
    "--model",
    "-m",
    default=None,
    help="Model name to use (overrides config)",
)
@click.option(
    "--system",
    "-s",
    default=None,
    help="Custom system prompt",
)
@click.option(
    "--workspace",
    "-w",
    default=None,
    help="Workspace directory (default: current directory)",
)
@click.option(
    "--no-tools",
    is_flag=True,
    default=False,
    help="Disable all tools (pure conversation mode)",
)
@click.option(
    "--no-shell",
    is_flag=True,
    default=False,
    help="Disable shell execution tool",
)
@click.option(
    "--save-history",
    "-S",
    is_flag=True,
    default=False,
    help="Persist conversation history to disk",
)
def chat(
    provider: Optional[str],
    model: Optional[str],
    system: Optional[str],
    workspace: Optional[str],
    no_tools: bool,
    no_shell: bool,
    save_history: bool,
) -> None:
    """Start an interactive chat session with the agent."""
    asyncio.run(
        _chat_async(
            provider=provider,
            model=model,
            system=system,
            workspace=workspace,
            no_tools=no_tools,
            no_shell=no_shell,
            save_history=save_history,
        )
    )


async def _chat_async(
    provider: Optional[str],
    model: Optional[str],
    system: Optional[str],
    workspace: Optional[str],
    no_tools: bool,
    no_shell: bool,
    save_history: bool,
) -> None:
    from agent.config import settings
    from agent.core import create_agent, build_default_tools

    # Apply overrides
    if workspace:
        settings.workspace_dir = workspace

    if provider:
        settings.default_provider = provider  # type: ignore[assignment]

    # Build the agent
    if no_tools:
        tools = []
    else:
        tools = build_default_tools(settings)
        if no_shell:
            tools = [t for t in tools if t.name != "run_shell"]

    agent = create_agent(
        tools=tools,
        system_prompt=system,
        config=settings,
    )

    if save_history:
        agent.memory._persist_path = settings.memory_file

    console.print(BANNER)
    console.print(
        Panel(
            f"[green]Provider:[/green] {settings.default_provider}  "
            f"[green]Model:[/green] {_active_model(settings, provider)}  "
            f"[green]Workspace:[/green] {os.path.abspath(settings.workspace_dir)}\n"
            f"[green]Tools:[/green] {', '.join(t.name for t in agent.tools) or 'None'}\n\n"
            "[dim]Type your message and press Enter. "
            "Use /help for commands, /exit to quit.[/dim]",
            title="[bold]GeosclawAI[/bold]",
            border_style="cyan",
        )
    )

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input.strip():
            continue

        # Handle special commands
        if user_input.startswith("/"):
            if await _handle_command(user_input, agent):
                continue
            else:
                break

        console.print()

        # Execute with spinner while waiting
        tool_calls_display: list[str] = []

        def on_tool_call(name: str, args: dict) -> None:
            tool_calls_display.append(name)
            console.print(
                f"  [dim yellow]⚙  Running tool:[/dim yellow] [yellow]{name}[/yellow]"
            )

        with console.status("[bold green]Thinking...[/bold green]", spinner="dots"):
            response = await agent.run(
                user_input,
                on_tool_call=on_tool_call,
            )

        console.print(
            Panel(
                Markdown(response.content),
                title="[bold green]GeosclawAI[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )

        if response.tool_calls_made:
            console.print(
                f"[dim]  {response.iterations} iteration(s) · "
                f"{len(response.tool_calls_made)} tool call(s) · "
                f"{response.total_tokens} tokens[/dim]"
            )


async def _handle_command(command: str, agent: Any) -> bool:
    """Handle /slash commands. Returns True to continue, False to exit."""
    from agent.core import Agent

    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower()

    if cmd in ("/exit", "/quit", "/q"):
        console.print("[dim]Goodbye![/dim]")
        return False

    if cmd in ("/help", "/?"):
        console.print(
            Panel(
                "[cyan]/help[/cyan]        – Show this help message\n"
                "[cyan]/clear[/cyan]       – Clear conversation history\n"
                "[cyan]/history[/cyan]     – Show conversation history\n"
                "[cyan]/tools[/cyan]       – List available tools\n"
                "[cyan]/system <prompt>[/cyan] – Update system prompt\n"
                "[cyan]/exit[/cyan]        – Exit the agent",
                title="Commands",
                border_style="cyan",
            )
        )
        return True

    if cmd == "/clear":
        agent.clear_history()
        console.print("[green]History cleared.[/green]")
        return True

    if cmd == "/history":
        msgs = agent.memory.get_messages(include_system=False)
        if not msgs:
            console.print("[dim]No history.[/dim]")
        else:
            for msg in msgs:
                role_color = "cyan" if msg.role.value == "user" else "green"
                console.print(
                    f"[{role_color}]{msg.role.value.upper()}[/{role_color}]: "
                    f"{msg.content[:200]}{'...' if len(msg.content) > 200 else ''}"
                )
        return True

    if cmd == "/tools":
        tools = agent.tools
        if not tools:
            console.print("[dim]No tools available.[/dim]")
        else:
            lines = [f"[cyan]{t.name}[/cyan]: {t.description}" for t in tools]
            console.print(Panel("\n".join(lines), title="Available Tools"))
        return True

    if cmd == "/system":
        if len(parts) > 1:
            agent.memory.set_system_prompt(parts[1])
            console.print("[green]System prompt updated.[/green]")
        else:
            sp = agent.memory.system_prompt or "(none)"
            console.print(f"Current system prompt:\n{sp}")
        return True

    console.print(f"[yellow]Unknown command: {cmd}. Type /help for help.[/yellow]")
    return True


def _active_model(settings: Any, provider_override: Optional[str]) -> str:
    p = provider_override or settings.default_provider
    if p == "anthropic":
        return settings.anthropic_model
    return settings.openai_model


@cli.command()
@click.argument("message")
@click.option("--provider", "-p", type=click.Choice(["anthropic", "openai"]), default=None)
@click.option("--model", "-m", default=None)
@click.option("--workspace", "-w", default=None)
@click.option("--no-tools", is_flag=True, default=False)
def ask(
    message: str,
    provider: Optional[str],
    model: Optional[str],
    workspace: Optional[str],
    no_tools: bool,
) -> None:
    """Send a single message to the agent and print the response."""
    asyncio.run(_ask_async(message, provider, model, workspace, no_tools))


async def _ask_async(
    message: str,
    provider: Optional[str],
    model: Optional[str],
    workspace: Optional[str],
    no_tools: bool,
) -> None:
    from agent.config import settings
    from agent.core import create_agent, build_default_tools

    if workspace:
        settings.workspace_dir = workspace
    if provider:
        settings.default_provider = provider  # type: ignore[assignment]

    tools = [] if no_tools else build_default_tools(settings)
    agent = create_agent(tools=tools, config=settings)

    def on_tool_call(name: str, args: dict) -> None:
        console.print(f"[dim yellow]⚙  {name}[/dim yellow]", file=sys.stderr)

    with console.status("[bold green]Thinking...[/bold green]", spinner="dots"):
        response = await agent.run(message, on_tool_call=on_tool_call)

    console.print(Markdown(response.content))


@cli.command()
@click.option("--host", default=None, help="Host to bind (default from config)")
@click.option("--port", default=None, type=int, help="Port to bind (default from config)")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload (dev mode)")
def serve(host: Optional[str], port: Optional[int], reload: bool) -> None:
    """Start the GeosclawAI REST API server."""
    import uvicorn
    from agent.config import settings

    h = host or settings.api_host
    p = port or settings.api_port

    console.print(f"[bold green]Starting GeosclawAI API server on http://{h}:{p}[/bold green]")
    uvicorn.run("agent.api:app", host=h, port=p, reload=reload)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
