"""
Example: Simple chat with GeosclawAI agent.

Set the GEOSCLAW_ANTHROPIC_API_KEY (or GEOSCLAW_OPENAI_API_KEY) environment
variable before running this example.
"""
import asyncio
import os

from agent.core import create_agent


async def main():
    agent = create_agent()

    # Simple single-turn query
    response = await agent.run("What is the capital of France?")
    print("Agent:", response.content)

    # Multi-turn conversation
    response = await agent.run("What about Germany?")
    print("Agent:", response.content)

    print(f"\n[Used {response.total_tokens} tokens, {response.iterations} iteration(s)]")


if __name__ == "__main__":
    asyncio.run(main())
