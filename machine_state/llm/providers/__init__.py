"""LLM provider abstraction layer."""

from .base import LLMProvider, LLMResponse, ProviderError


def get_provider(name: str, **kwargs) -> "LLMProvider":
    """Instantiate a provider by name.

    Supported names: anthropic, openai, gemini, ollama
    kwargs are forwarded to the provider constructor (api_key, model, base_url, etc.)
    """
    name = name.lower().strip()
    if name == "anthropic":
        from .anthropic import AnthropicProvider
        return AnthropicProvider(**kwargs)
    if name == "openai":
        from .openai import OpenAIProvider
        return OpenAIProvider(**kwargs)
    if name == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(**kwargs)
    if name == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider(**kwargs)
    raise ValueError(f"Unknown LLM provider: '{name}'. Choose from: anthropic, openai, gemini, ollama")


__all__ = ["LLMProvider", "LLMResponse", "ProviderError", "get_provider"]
