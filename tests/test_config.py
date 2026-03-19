"""Tests for configuration management."""
from __future__ import annotations

import os

import pytest

from agent.config import Config


def test_default_values():
    """Config should have sensible defaults."""
    cfg = Config()
    assert cfg.default_provider in ("anthropic", "openai")
    assert cfg.max_iterations > 0
    assert cfg.max_tokens > 0
    assert 0.0 <= cfg.temperature <= 1.0


def test_temperature_clamping():
    """Temperatures outside [0, 1] should be clamped."""
    cfg = Config(temperature=5.0)
    assert cfg.temperature == 1.0

    cfg2 = Config(temperature=-0.5)
    assert cfg2.temperature == 0.0


def test_is_provider_configured_empty_key():
    """is_provider_configured should return False when no key is set."""
    cfg = Config(anthropic_api_key="", openai_api_key="")
    assert not cfg.is_provider_configured("anthropic")
    assert not cfg.is_provider_configured("openai")
    assert not cfg.is_provider_configured("unknown")


def test_is_provider_configured_with_key():
    """is_provider_configured should return True when a key is present."""
    cfg = Config(anthropic_api_key="sk-ant-test", openai_api_key="sk-openai-test")
    assert cfg.is_provider_configured("anthropic")
    assert cfg.is_provider_configured("openai")


def test_env_prefix(monkeypatch):
    """Config should read env vars with GEOSCLAW_ prefix."""
    monkeypatch.setenv("GEOSCLAW_MAX_ITERATIONS", "99")
    cfg = Config()
    assert cfg.max_iterations == 99
