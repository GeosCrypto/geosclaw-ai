"""
Example: Code assistant – ask the agent to write and test Python code.

This demonstrates how the agent uses file and shell tools to complete tasks.
"""
import asyncio
import os
import tempfile

from agent.config import settings
from agent.core import create_agent


async def main():
    # Use a temp directory as the workspace
    with tempfile.TemporaryDirectory() as workspace:
        settings.workspace_dir = workspace

        agent = create_agent(
            system_prompt=(
                "You are an expert Python developer. "
                "Write clean, tested, well-documented code."
            ),
        )

        task = (
            "Write a Python function called `fibonacci(n)` that returns "
            "the nth Fibonacci number using memoization. "
            "Save it to fibonacci.py, then write a test file test_fibonacci.py "
            "and run the tests."
        )

        print(f"Task: {task}\n")
        print("─" * 60)

        def on_tool_call(name, args):
            print(f"  ⚙  [{name}] {list(args.keys())}")

        response = await agent.run(task, on_tool_call=on_tool_call)

        print("\n─" * 60)
        print("Agent response:")
        print(response.content)
        print(f"\n[{response.iterations} iteration(s), {len(response.tool_calls_made)} tool call(s)]")


if __name__ == "__main__":
    asyncio.run(main())
