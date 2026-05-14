"""Ollama local provider.

Connects to a locally running Ollama instance via HTTP.
No API key required. Default base URL: http://localhost:11434.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import LLMProvider, LLMResponse, ProviderError

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "qwen3:8b"


class OllamaProvider(LLMProvider):

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self._model = model or os.environ.get("OLLAMA_MODEL", _DEFAULT_MODEL)
        self._base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        self._max_tokens = max_tokens

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, system_prompt: str, user_message: str) -> LLMResponse:
        url = f"{self._base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "options": {"num_predict": self._max_tokens},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8")
            raise ProviderError(f"Ollama API error {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(
                f"Cannot reach Ollama at {self._base_url}. "
                "Is Ollama running? Start it with: ollama serve"
            ) from exc

        text = body.get("message", {}).get("content", "")
        usage = body.get("prompt_eval_count"), body.get("eval_count")
        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=self._model,
            input_tokens=usage[0],
            output_tokens=usage[1],
        )

    def list_models(self) -> list[str]:
        """Return a list of models available in this Ollama instance."""
        url = f"{self._base_url}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in body.get("models", [])]
        except Exception:
            return []
