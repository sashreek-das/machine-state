"""Shared utilities for CLI command handlers."""

from __future__ import annotations

import json
from typing import Any


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))
