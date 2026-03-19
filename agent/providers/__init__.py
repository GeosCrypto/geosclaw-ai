"""AI provider sub-package."""
from agent.providers.base import BaseProvider, Message, Role
from agent.providers.anthropic_provider import AnthropicProvider
from agent.providers.openai_provider import OpenAIProvider
from agent.providers.ollama_provider import OllamaProvider
from agent.providers.azure_provider import AzureOpenAIProvider

__all__ = [
    "BaseProvider",
    "Message",
    "Role",
    "AnthropicProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "AzureOpenAIProvider",
    # GeminiProvider is optional (requires google-genai); import directly when needed
]
