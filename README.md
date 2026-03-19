# GeosclawAI 🤖

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Phase 2 In Progress](https://img.shields.io/badge/status-Phase%202%20In%20Progress-blue.svg)](ROADMAP.md)

**GeosclawAI** is a powerful, autonomous AI agent combining the best features of top AI coding and workflow agents – Claude Code, OpenClaw, and more – into a single open-source framework.

> **⏱ Completion estimate:** Phase 2 is now actively running.  
> Full v1.0 production readiness is ~**4–6 weeks** away.  
> See the [**📍 Roadmap**](ROADMAP.md) for a detailed breakdown of what's done and what's planned.

---

## 📍 Current Status

| Phase | Description | Status |
|---|---|---|
| **Phase 1** | Core foundation (providers, tools, CLI, API, memory) | ✅ **Complete** |
| **Phase 2** | Enhanced capabilities (Gemini/Ollama/Azure, Git skill, patch_file, run_python, run_tests, retry, parallel tools, token budget) | 🔄 **In Progress** |
| **Phase 3** | Production readiness (Web UI, vector memory, Docker, CI, multi-user API) | 🔲 ~3–4 weeks |
| **Phase 4** | Advanced features (messaging integrations, scheduler, skill marketplace) | 🔲 post-v1.0 |

Full details and per-feature checklists are in [**ROADMAP.md**](ROADMAP.md).

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔌 **Multi-provider** | Anthropic (Claude), OpenAI (GPT-4o), Google Gemini, Ollama (local), Azure OpenAI |
| 🛠️ **Rich tool system** | File I/O, patch_file, shell execution, run_python, run_tests, web search, code analysis, persistent memory |
| 🔄 **Agentic loop** | Autonomous multi-step task execution with tool calling |
| ⚡ **Parallel tools** | Independent tool calls executed concurrently with `asyncio.gather` |
| 🔁 **Retry / backoff** | Automatic exponential-backoff retry on provider rate limits and transient errors |
| 💰 **Token budget** | Configurable per-run token budget with usage warnings |
| 📡 **Streaming** | Real-time token streaming via CLI and REST API (Server-Sent Events) |
| 🌐 **REST API** | FastAPI-based API server with session management |
| 💬 **Interactive CLI** | Rich terminal interface with slash commands |
| 🧠 **Memory** | Sliding-window conversation history + file-backed persistent memory |
| 🧩 **Skills / Plugins** | Git skill built-in; extend with your own pluggable tool bundles |
| 🔒 **Security** | Path-traversal protection, configurable shell execution, optional API key |
| 🧪 **Tested** | 80+ unit and integration tests |

---

## 🚀 Quick Start

### 1. Install

```bash
git clone https://github.com/GeosCrypto/geosclaw-ai.git
cd geosclaw-ai
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and add your API key(s)
```

```ini
# .env
GEOSCLAW_ANTHROPIC_API_KEY=sk-ant-...   # or GEOSCLAW_OPENAI_API_KEY
GEOSCLAW_DEFAULT_PROVIDER=anthropic
```

### 3. Start chatting

```bash
geosclaw chat
```

Or send a single message:

```bash
geosclaw ask "Write a Python script that sorts a list of numbers"
```

Or start the API server:

```bash
geosclaw serve
```

---

## 📖 Usage

### CLI

```
Usage: geosclaw [OPTIONS] COMMAND [ARGS]...

  GeosclawAI – A powerful autonomous AI agent.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  ask    Send a single message to the agent and print the response.
  chat   Start an interactive chat session with the agent.
  serve  Start the GeosclawAI REST API server.
```

#### Interactive chat options

```bash
geosclaw chat \
  --provider anthropic \           # or openai
  --model claude-opus-4-5 \        # model override
  --workspace /path/to/project \   # working directory
  --system "You are a DevOps expert" \  # custom system prompt
  --no-shell \                     # disable shell execution
  --save-history                   # persist conversation to disk
```

#### In-session slash commands

| Command | Description |
|---|---|
| `/help` | Show available commands |
| `/clear` | Clear conversation history |
| `/history` | Show conversation history |
| `/tools` | List available tools |
| `/system <prompt>` | Update the system prompt |
| `/exit` | Exit the agent |

---

### REST API

Start the server:

```bash
geosclaw serve --host 0.0.0.0 --port 8000
```

#### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/tools` | List available tools |
| `GET` | `/sessions` | List active sessions |
| `DELETE` | `/sessions/{id}` | Delete a session |
| `POST` | `/chat` | Send a message |
| `POST` | `/chat/stream` | Stream a response (SSE) |

#### Example: Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Write a Python hello world script",
    "session_id": "my-session",
    "enable_tools": true
  }'
```

Response:

```json
{
  "session_id": "my-session",
  "content": "Here is a Python hello world script:\n\n```python\nprint('Hello, world!')\n```",
  "tool_calls_made": [{"tool": "write_file", "arguments": {"path": "hello.py", "content": "..."}}],
  "iterations": 2,
  "total_tokens": 312
}
```

#### Example: Streaming

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me about Python"}'
```

---

### Python SDK

```python
import asyncio
from agent.core import create_agent

async def main():
    agent = create_agent()  # uses settings from .env

    # Single-turn
    response = await agent.run("What is 2 + 2?")
    print(response.content)

    # Multi-turn (history is preserved)
    response = await agent.run("Multiply that by 10")
    print(response.content)

    # With callbacks
    def on_tool_call(name, args):
        print(f"Calling tool: {name}")

    response = await agent.run(
        "Read the file README.md and summarise it",
        on_tool_call=on_tool_call,
    )

    # Streaming
    async for token in agent.stream("Write a haiku"):
        print(token, end="", flush=True)

asyncio.run(main())
```

#### Choosing a provider explicitly

```python
from agent.providers.anthropic_provider import AnthropicProvider
from agent.providers.openai_provider import OpenAIProvider
from agent.core import Agent, build_default_tools

# Anthropic
provider = AnthropicProvider(api_key="sk-ant-...", model="claude-opus-4-5")

# OpenAI
provider = OpenAIProvider(api_key="sk-...", model="gpt-4o")

agent = Agent(provider=provider, tools=build_default_tools())
```

---

## 🛠️ Available Tools

| Tool | Description |
|---|---|
| `read_file` | Read the contents of a file |
| `write_file` | Write (or append) to a file |
| `list_files` | List files in a directory |
| `search_files` | Regex search across files |
| `delete_file` | Delete a file |
| `create_directory` | Create a directory |
| `patch_file` | Apply a unified diff (patch) to a file *(Phase 2)* |
| `run_shell` | Execute a shell command |
| `run_python` | Execute a Python code snippet in a subprocess *(Phase 2)* |
| `run_tests` | Run pytest and return structured results *(Phase 2)* |
| `web_search` | Search the web with DuckDuckGo |
| `web_fetch` | Fetch a web page |
| `analyze_code` | Analyse a source code file |
| `format_code` | Format Python code with Black |
| `save_memory` | Persist a note to disk |
| `recall_memory` | Retrieve a persisted note |

---

## 🧩 Skills (Plugin System)

Create domain-specific tool bundles:

```python
from agent.skills.base_skill import BaseSkill
from agent.tools.base import BaseTool

class GitSkill(BaseSkill):
    name = "git"
    description = "Git operations"

    def get_tools(self) -> list[BaseTool]:
        return [GitStatusTool(), GitCommitTool(), GitPushTool()]

# Register with the agent
agent.register_skill(GitSkill())
```

---

Also update the Skills section to reference the built-in Git skill:

```python
from agent.skills.git_skill import GitSkill

# Use the built-in Git skill
agent.register_skill(GitSkill())
```

Or create your own:

```python
from agent.skills.base_skill import BaseSkill
from agent.tools.base import BaseTool

class MySkill(BaseSkill):
    name = "my_skill"
    description = "Custom operations"

    def get_tools(self) -> list[BaseTool]:
        return [MyTool1(), MyTool2()]

agent.register_skill(MySkill())
```

---

## ⚙️ Configuration

All settings can be configured via environment variables (prefixed with `GEOSCLAW_`) or a `.env` file.

| Variable | Default | Description |
|---|---|---|
| `GEOSCLAW_DEFAULT_PROVIDER` | `anthropic` | AI provider: `anthropic`, `openai`, `gemini`, `ollama`, `azure_openai` |
| `GEOSCLAW_ANTHROPIC_API_KEY` | _(empty)_ | Anthropic API key |
| `GEOSCLAW_ANTHROPIC_MODEL` | `claude-opus-4-5` | Anthropic model name |
| `GEOSCLAW_OPENAI_API_KEY` | _(empty)_ | OpenAI API key |
| `GEOSCLAW_OPENAI_MODEL` | `gpt-4o` | OpenAI model name |
| `GEOSCLAW_GEMINI_API_KEY` | _(empty)_ | Google Gemini API key *(Phase 2)* |
| `GEOSCLAW_GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model name *(Phase 2)* |
| `GEOSCLAW_OLLAMA_MODEL` | `llama3.2` | Ollama local model *(Phase 2)* |
| `GEOSCLAW_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama API URL *(Phase 2)* |
| `GEOSCLAW_AZURE_OPENAI_API_KEY` | _(empty)_ | Azure OpenAI API key *(Phase 2)* |
| `GEOSCLAW_AZURE_OPENAI_ENDPOINT` | _(empty)_ | Azure OpenAI resource endpoint *(Phase 2)* |
| `GEOSCLAW_AZURE_OPENAI_DEPLOYMENT` | `gpt-4o` | Azure deployment name *(Phase 2)* |
| `GEOSCLAW_MAX_ITERATIONS` | `50` | Max agentic loop iterations |
| `GEOSCLAW_MAX_TOKENS` | `8192` | Max tokens per response |
| `GEOSCLAW_TEMPERATURE` | `0.7` | Sampling temperature |
| `GEOSCLAW_TOKEN_BUDGET` | `0` | Per-run token budget (0 = unlimited) *(Phase 2)* |
| `GEOSCLAW_MAX_PROVIDER_RETRIES` | `3` | Max retries on transient errors *(Phase 2)* |
| `GEOSCLAW_PARALLEL_TOOL_CALLS` | `true` | Execute independent tools in parallel *(Phase 2)* |
| `GEOSCLAW_WORKSPACE_DIR` | `.` | Working directory for file ops |
| `GEOSCLAW_MAX_FILE_SIZE_KB` | `512` | Max file size the agent may read |
| `GEOSCLAW_ALLOW_SHELL` | `true` | Enable shell execution |
| `GEOSCLAW_SHELL_TIMEOUT` | `30` | Shell command timeout (seconds) |
| `GEOSCLAW_ENABLE_WEB_SEARCH` | `true` | Enable web search |
| `GEOSCLAW_MAX_SEARCH_RESULTS` | `5` | Max search results |
| `GEOSCLAW_MAX_HISTORY_MESSAGES` | `100` | Max conversation history |
| `GEOSCLAW_API_HOST` | `0.0.0.0` | API server host |
| `GEOSCLAW_API_PORT` | `8000` | API server port |
| `GEOSCLAW_API_KEY` | _(empty)_ | Optional API auth key |

---

## 🧪 Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## 🗂️ Project Structure

```
geosclaw-ai/
├── agent/
│   ├── __init__.py          # Package metadata
│   ├── config.py            # Configuration management
│   ├── core.py              # Main Agent class + factory (retry, parallel tools, token budget)
│   ├── memory.py            # Conversation history
│   ├── cli.py               # CLI (geosclaw command)
│   ├── api.py               # FastAPI REST server
│   ├── providers/
│   │   ├── base.py          # Provider interface
│   │   ├── anthropic_provider.py
│   │   ├── openai_provider.py
│   │   ├── gemini_provider.py   # Phase 2 – Google Gemini
│   │   ├── ollama_provider.py   # Phase 2 – Ollama (local models)
│   │   └── azure_provider.py    # Phase 2 – Azure OpenAI
│   ├── tools/
│   │   ├── base.py          # Tool interface
│   │   ├── file_tools.py    # File operations + patch_file (Phase 2)
│   │   ├── shell_tools.py   # Shell execution
│   │   ├── web_tools.py     # Web search & fetch
│   │   ├── code_tools.py    # Code analysis, format, run_python, run_tests (Phase 2)
│   │   └── memory_tools.py  # Persistent memory
│   └── skills/
│       ├── base_skill.py    # Skill plugin interface
│       ├── git_skill.py     # Phase 2 – Git operations
│       └── ...              # Add your own skills here
├── tests/                   # Test suite (80+ tests)
├── examples/                # Usage examples
├── .env.example             # Environment template
├── ROADMAP.md               # Project roadmap & completion estimates
├── requirements.txt
├── setup.py
└── pyproject.toml
```

---

## 📍 Roadmap

See [**ROADMAP.md**](ROADMAP.md) for the full plan, phase-by-phase feature checklists, and time estimates.

---

## 📄 License

MIT License.
