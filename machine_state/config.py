"""User configuration: LLM provider, model, and API key.

Stored at ~/.machine-state/config.json (configuration, not runtime state).
Written by `machine-state setup`; read by the chat command.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .store import DATA_DIR

_CONFIG_PATH = DATA_DIR / "config.json"


def load() -> dict[str, Any]:
    """Load config. Returns {} if not present or unreadable."""
    if not _CONFIG_PATH.exists():
        return {}
    try:
        with _CONFIG_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(data: dict[str, Any]) -> None:
    """Write config atomically, restricting file permissions to owner-only."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _CONFIG_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.chmod(0o600)
    tmp.replace(_CONFIG_PATH)


def provider_kwargs() -> tuple[str, dict[str, Any]]:
    """Return (provider_name, kwargs) from saved config.

    Falls back to ('ollama', {}) when no config is present.
    """
    cfg = load()
    name = cfg.get("provider", "ollama")
    kwargs: dict[str, Any] = {}
    if cfg.get("model"):
        kwargs["model"] = cfg["model"]
    if cfg.get("api_key"):
        kwargs["api_key"] = cfg["api_key"]
    if cfg.get("ollama_base_url"):
        kwargs["base_url"] = cfg["ollama_base_url"]
    return name, kwargs
