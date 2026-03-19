# GeosclawAI – Project Roadmap

This document tracks what has been built, what is in progress, and what is planned. It also answers the common question: **"How long until GeosclawAI is fully complete?"**

---

## TL;DR – Completion Estimate

| Phase | Focus | Estimate |
|---|---|---|
| ✅ **Phase 1** | Core foundation | **Complete** |
| 🔄 **Phase 2** | Enhanced capabilities | **In Progress** (~1–2 weeks remaining) |
| 🔲 **Phase 3** | Production readiness | ~3–4 weeks |
| 🔲 **Phase 4** | Advanced & ecosystem features | ~4–6 weeks |

> **Total remaining:** roughly **8–12 weeks** of focused development (solo developer pace).  
> For a small team (2–3 contributors) this could be compressed to **4–5 weeks**.

A "fully featured" v1.0 release is targeted at the completion of Phase 3.  
Phase 4 represents the long-term roadmap beyond v1.0.

---

## ✅ Phase 1 – Core Foundation (Complete)

The working skeleton of GeosclawAI is in place.

### Providers
- [x] Abstracted `BaseProvider` interface — add any backend without changing agent logic
- [x] **Anthropic** (Claude models) — full tool-calling, streaming
- [x] **OpenAI** (GPT-4o and compatible models) — full tool-calling, streaming

### Tools (13 built-in)
- [x] `read_file` / `write_file` (append mode) / `delete_file`
- [x] `list_files` / `search_files` (regex, glob filter)
- [x] `create_directory`
- [x] `run_shell` — with configurable timeout and process cleanup
- [x] `web_search` — DuckDuckGo, no API key required
- [x] `web_fetch` — strip HTML, truncate, follow redirects
- [x] `analyze_code` — language detection, class/function extraction
- [x] `format_code` — Black integration
- [x] `save_memory` / `recall_memory` — JSON-backed key-value store

### Agent Core
- [x] Agentic loop — autonomous multi-step task execution
- [x] Configurable `max_iterations` guard
- [x] Tool-call parsing for both providers
- [x] `on_token` / `on_tool_call` callbacks
- [x] Simulated streaming (`Agent.stream()`)
- [x] Skill/plugin registration (`agent.register_skill(...)`)

### Interfaces
- [x] **Interactive CLI** (`geosclaw chat`) — Rich UI, spinners, slash commands
- [x] **Single-shot CLI** (`geosclaw ask "..."`)
- [x] **FastAPI REST API** — `POST /chat`, `POST /chat/stream` (SSE), session management, optional API-key auth
- [x] **Python SDK** — `create_agent()`, `agent.run()`, `agent.stream()`

### Memory
- [x] Sliding-window conversation history (configurable max messages)
- [x] File-backed persistence across sessions

### Infrastructure
- [x] Pydantic settings with `GEOSCLAW_*` env-var prefix
- [x] `.env.example` template
- [x] Path-traversal security guard on all file tools
- [x] `setup.py` + `pyproject.toml`
- [x] 42 unit and integration tests
- [x] `.gitignore`

---

## 🔄 Phase 2 – Enhanced Capabilities (In Progress)

These features bring GeosclawAI to parity with the most capable open-source agents.

### Additional Providers
- [x] **Google Gemini** provider (Gemini 2.0 Flash / any Gemini model) — `agent/providers/gemini_provider.py`
- [x] **Ollama** provider — run local models (Llama 3, Mistral, Qwen, etc.) — `agent/providers/ollama_provider.py`
- [x] **Azure OpenAI** provider — enterprise deployments — `agent/providers/azure_provider.py`

### Real Streaming
- [ ] Replace the simulated chunked streaming in `Agent.stream()` with native provider-side SSE token streaming for true latency reduction

### New Built-in Skills
- [x] **Git skill** — `git_status`, `git_diff`, `git_commit`, `git_push`, `git_log`, `git_create_branch` — `agent/skills/git_skill.py`
- [ ] **Browser skill** — headless browsing with Playwright: `open_url`, `click`, `fill_form`, `take_screenshot`, `extract_text`
- [ ] **Image/Vision skill** — pass screenshots or local images to vision-capable models

### Tool Improvements
- [x] `patch_file` — apply unified diffs rather than full rewrites — added to `agent/tools/file_tools.py`
- [x] `run_python` — execute Python code in a sandbox with output capture — added to `agent/tools/code_tools.py`
- [x] `run_tests` — run pytest / unittest and parse structured results — added to `agent/tools/code_tools.py`
- [ ] Parallel tool execution — run independent tool calls concurrently ✅ **done** (see Reliability below)

### Reliability
- [x] Automatic retry with exponential backoff on provider rate limits / transient errors — `agent/core.py`
- [x] Parallel tool execution — `asyncio.gather` for independent tool calls — `agent/core.py`
- [x] Token budget tracking and warnings before hitting limits — `agent/core.py`
- [ ] Structured error taxonomy (user errors vs. provider errors vs. tool errors)

---

## 🔲 Phase 3 – Production Readiness (~3–4 weeks)

These features are needed for a v1.0 release that teams can rely on.

### Web UI
- [ ] **Streamlit dashboard** — zero-install local UI for chatting with the agent, viewing tool calls and history
- [ ] (Stretch) React/Next.js frontend with real-time SSE streaming

### Long-Term Memory (RAG)
- [ ] **Vector store integration** — ChromaDB or SQLite-vec for embedding-based recall across long histories and document collections
- [ ] `index_directory` tool — chunk and embed all files in a directory
- [ ] `semantic_search` tool — retrieve relevant context before each LLM call

### Multi-Agent Orchestration
- [ ] `spawn_agent` tool — let the primary agent delegate sub-tasks to specialised sub-agents with their own tool sets
- [ ] Orchestrator / worker pattern for long-running parallel workflows

### Multi-User REST API
- [ ] JWT-based authentication
- [ ] Per-user session isolation and rate limiting
- [ ] Session persistence to SQLite (instead of in-memory dict)
- [ ] Admin endpoints: usage stats, session listing, session deletion

### Deployment
- [ ] `Dockerfile` and `docker-compose.yml`
- [ ] `docker compose up` single-command launch (agent + API + optional UI)
- [ ] Environment validation on startup with clear error messages

### Observability
- [ ] Structured JSON logging with configurable levels
- [ ] OpenTelemetry traces for provider calls and tool executions
- [ ] `/metrics` endpoint (Prometheus-compatible)
- [ ] Token and cost tracking per session

### Quality
- [ ] End-to-end integration tests against mock providers
- [ ] Coverage ≥ 85%
- [ ] CI pipeline (GitHub Actions) with lint, test, type-check, and security scan

---

## 🔲 Phase 4 – Advanced & Ecosystem Features (~4–6 weeks, post-v1.0)

Long-term features that make GeosclawAI a platform rather than just a library.

### Integrations
- [ ] **Slack** skill — read/send messages, react, create channels
- [ ] **Discord** skill — bot mode with per-channel agent sessions
- [ ] **Telegram** skill — webhook-based bot, group and private modes
- [ ] **Email** skill — IMAP read + SMTP send
- [ ] **Calendar** skill — Google Calendar / CalDAV read/write

### Desktop & GUI
- [ ] Desktop app (Electron or Tauri) wrapping the web UI for macOS / Windows / Linux
- [ ] System tray daemon for always-on background task execution

### Scheduling & Automation
- [ ] Cron-style task scheduler — "run this task every hour"
- [ ] Webhook trigger endpoint — run agent workflows from external events

### Skill Ecosystem
- [ ] Skill registry / plugin marketplace (`geosclaw install git-skill`)
- [ ] Skill packaging standard and contribution guide
- [ ] Community skill examples: Kubernetes, AWS, Terraform, databases

### Advanced AI
- [ ] Fine-tuning pipeline for domain-specific models
- [ ] Multi-modal input — audio transcription (Whisper), image capture
- [ ] Agent evaluation harness — benchmark quality of tool-use and task completion

---

## Contributing

If you'd like to help accelerate any phase, open an issue or PR!  
The [Contributing Guide](CONTRIBUTING.md) (coming in Phase 3) will have full details.

---

## Version History

| Version | Date | Notes |
|---|---|---|
| `0.2.0` | 2026-03-19 | Phase 2 started — Gemini/Ollama/Azure providers, Git skill, patch_file, run_python, run_tests, retry, parallel tool calls, token budget |
| `0.1.0` | 2026-03-15 | Initial release — Phase 1 complete |
