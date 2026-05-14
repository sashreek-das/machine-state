"""Google Gemini provider.

Uses the google-generativeai SDK if available, falls back to direct HTTP via urllib.
API key sourced from GOOGLE_API_KEY environment variable or constructor.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import LLMProvider, LLMResponse, ProviderError

_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider(LLMProvider):

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 1024,
    ) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self._model = model
        self._max_tokens = max_tokens
        if not self._api_key:
            raise ProviderError(
                "Google API key not found. Set GOOGLE_API_KEY environment variable "
                "or pass api_key= to GeminiProvider()."
            )

    @property
    def provider_name(self) -> str:
        return "gemini"

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
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=self._api_key)
        model = genai.GenerativeModel(
            model_name=self._model,
            system_instruction=system_prompt,
        )
        resp = model.generate_content(
            user_message,
            generation_config=genai.GenerationConfig(max_output_tokens=self._max_tokens),
        )
        text = resp.text or ""
        usage = resp.usage_metadata
        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=self._model,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )

    def _complete_http(self, system_prompt: str, user_message: str) -> LLMResponse:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent?key={self._api_key}"
        )
        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_message}]}],
            "generationConfig": {"maxOutputTokens": self._max_tokens},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8")
            raise ProviderError(f"Gemini API error {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Gemini connection error: {exc.reason}") from exc

        candidates = body.get("candidates", [{}])
        parts = candidates[0].get("content", {}).get("parts", [{}])
        text = parts[0].get("text", "")
        usage = body.get("usageMetadata", {})
        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=self._model,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
        )
