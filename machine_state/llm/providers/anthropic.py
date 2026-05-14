"""Anthropic Claude provider.

Uses the Anthropic SDK if available, falls back to direct HTTP via urllib.
API key sourced from ANTHROPIC_API_KEY environment variable or constructor.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import LLMProvider, LLMResponse, ProviderError

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicProvider(LLMProvider):

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 1024,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._max_tokens = max_tokens
        if not self._api_key:
            raise ProviderError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key= to AnthropicProvider()."
            )

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, system_prompt: str, user_message: str) -> LLMResponse:
        # Try SDK first
        try:
            return self._complete_sdk(system_prompt, user_message)
        except ImportError:
            pass
        # Fall back to raw HTTP
        return self._complete_http(system_prompt, user_message)

    def _complete_sdk(self, system_prompt: str, user_message: str) -> LLMResponse:
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=self._api_key)
        msg = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = msg.content[0].text if msg.content else ""
        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=self._model,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
        )

    def _complete_http(self, system_prompt: str, user_message: str) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _API_URL,
            data=data,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": _API_VERSION,
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8")
            raise ProviderError(f"Anthropic API error {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Anthropic connection error: {exc.reason}") from exc

        text = body.get("content", [{}])[0].get("text", "")
        usage = body.get("usage", {})
        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=self._model,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )
