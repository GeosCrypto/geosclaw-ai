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
    default_provider: Literal["openai", "anthropic"] = Field(
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
        return False


# Singleton instance – import this wherever you need config
settings = Config()
