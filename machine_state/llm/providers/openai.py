"""OpenAI provider.

Uses the OpenAI SDK if available, falls back to direct HTTP via urllib.
API key sourced from OPENAI_API_KEY environment variable or constructor.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import LLMProvider, LLMResponse, ProviderError

_API_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(LLMProvider):

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 1024,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model
        self._max_tokens = max_tokens
        if not self._api_key:
            raise ProviderError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or pass api_key= to OpenAIProvider()."
            )

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, system_prompt: str, user_message: str) -> LLMResponse:
        try:
            return self._complete_sdk(system_prompt, user_message)
        except ImportError:
            pass
        return self._complete_http(system_prompt, user_message)

    def _complete_sdk(self, system_prompt: str, user_message: str) -> LLMResponse:
        import openai  # type: ignore
        client = openai.OpenAI(api_key=self._api_key)
        resp = client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=self._model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )

    def _complete_http(self, system_prompt: str, user_message: str) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _API_URL,
            data=data,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8")
            raise ProviderError(f"OpenAI API error {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"OpenAI connection error: {exc.reason}") from exc

        text = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = body.get("usage", {})
        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=self._model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )
