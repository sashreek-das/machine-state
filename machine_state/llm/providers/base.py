"""Abstract base class for all LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(Exception):
    """Raised when an LLM provider call fails."""


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is not None and self.output_tokens is not None:
            return self.input_tokens + self.output_tokens
        return None


class LLMProvider(ABC):
    """Abstract base for all LLM providers.

    Each provider implements complete() which takes a system prompt and a
    user message and returns a structured LLMResponse.

    The system prompt enforces runtime authority and anti-hallucination rules.
    The user message contains the query + structured context from the runtime.
    """

    @abstractmethod
    def complete(self, system_prompt: str, user_message: str) -> LLMResponse:
        """Call the LLM and return a response."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short name of this provider (e.g. 'anthropic')."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier being used."""
        ...
