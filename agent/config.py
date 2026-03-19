"""
Configuration management for GeosclawAI.
Supports loading from environment variables and .env files.
"""
from __future__ import annotations

from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

load_dotenv()


class Config(BaseSettings):
    """Central configuration for the GeosclawAI agent."""

    # ------------------------------------------------------------------ #
    # AI provider settings                                                 #
    # ------------------------------------------------------------------ #
    default_provider: Literal["openai", "anthropic", "gemini", "ollama", "azure_openai"] = Field(
        default="anthropic",
        description="Default AI provider to use",
    )

    # OpenAI
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="Default OpenAI model")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI API base URL (override for proxies)",
    )

    # Anthropic
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    anthropic_model: str = Field(
        default="claude-opus-4-5",
        description="Default Anthropic model",
    )

    # Google Gemini
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model: str = Field(
        default="gemini-2.0-flash",
        description="Default Gemini model",
    )

    # Ollama (local models)
    ollama_model: str = Field(
        default="llama3.2",
        description="Default Ollama model name",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1",
        description="Ollama API base URL",
    )

    # Azure OpenAI
    azure_openai_api_key: str = Field(default="", description="Azure OpenAI API key")
    azure_openai_endpoint: str = Field(
        default="",
        description="Azure OpenAI resource endpoint (e.g. https://<resource>.openai.azure.com/)",
    )
    azure_openai_deployment: str = Field(
        default="gpt-4o",
        description="Azure OpenAI deployment name",
    )
    azure_openai_api_version: str = Field(
        default="2024-08-01-preview",
        description="Azure OpenAI API version",
    )

    # ------------------------------------------------------------------ #
    # Agent behaviour                                                      #
    # ------------------------------------------------------------------ #
    max_iterations: int = Field(
        default=50,
        description="Maximum agentic loop iterations per task",
    )
    max_tokens: int = Field(
        default=8192,
        description="Maximum tokens per response",
    )
    temperature: float = Field(
        default=0.7,
        description="Sampling temperature (0.0-1.0)",
    )
    streaming: bool = Field(
        default=True,
        description="Enable streaming responses",
    )

    # ------------------------------------------------------------------ #
    # Token budget                                                         #
    # ------------------------------------------------------------------ #
    token_budget: int = Field(
        default=0,
        description=(
            "Maximum total tokens per agent.run() call (0 = unlimited). "
            "When the budget is approached the agent emits a warning."
        ),
    )
    token_budget_warning_threshold: float = Field(
        default=0.85,
        description="Fraction of token_budget at which a warning is emitted (0.0-1.0)",
    )

    # ------------------------------------------------------------------ #
    # Retry / reliability                                                  #
    # ------------------------------------------------------------------ #
    max_provider_retries: int = Field(
        default=3,
        description="Maximum retries on transient provider errors (0 = no retries)",
    )
    retry_base_delay: float = Field(
        default=1.0,
        description="Base delay in seconds for exponential backoff retries",
    )

    # ------------------------------------------------------------------ #
    # Parallel tool execution                                              #
    # ------------------------------------------------------------------ #
    parallel_tool_calls: bool = Field(
        default=True,
        description="Execute independent tool calls in parallel using asyncio.gather",
    )

    # ------------------------------------------------------------------ #
    # File / workspace                                                     #
    # ------------------------------------------------------------------ #
    workspace_dir: str = Field(
        default=".",
        description="Working directory for file operations",
    )
    max_file_size_kb: int = Field(
        default=512,
        description="Maximum file size (KB) the agent may read",
    )

    # ------------------------------------------------------------------ #
    # Shell execution                                                      #
    # ------------------------------------------------------------------ #
    shell_timeout: int = Field(
        default=30,
        description="Timeout in seconds for shell commands",
    )
    allow_shell: bool = Field(
        default=True,
        description="Enable the shell-execution tool",
    )

    # ------------------------------------------------------------------ #
    # Memory / history                                                     #
    # ------------------------------------------------------------------ #
    max_history_messages: int = Field(
        default=100,
        description="Maximum number of messages to keep in conversation history",
    )
    memory_file: str = Field(
        default=".geosclaw_memory.json",
        description="Path to persist conversation memory",
    )

    # ------------------------------------------------------------------ #
    # API server                                                           #
    # ------------------------------------------------------------------ #
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    api_key: str = Field(
        default="",
        description="Optional API key to protect the REST API",
    )

    # ------------------------------------------------------------------ #
    # Web search                                                           #
    # ------------------------------------------------------------------ #
    enable_web_search: bool = Field(
        default=True,
        description="Enable the web-search tool",
    )
    max_search_results: int = Field(
        default=5,
        description="Maximum search results returned per query",
    )

    model_config = {"env_prefix": "GEOSCLAW_", "case_sensitive": False}

    @field_validator("temperature")
    @classmethod
    def clamp_temperature(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    def is_provider_configured(self, provider: str) -> bool:
        """Return True if the provider has a non-empty API key."""
        if provider == "openai":
            return bool(self.openai_api_key)
        if provider == "anthropic":
            return bool(self.anthropic_api_key)
        if provider == "gemini":
            return bool(self.gemini_api_key)
        if provider == "ollama":
            return True  # local, no API key needed
        if provider == "azure_openai":
            return bool(self.azure_openai_api_key and self.azure_openai_endpoint)
        return False


# Singleton instance – import this wherever you need config
settings = Config()
