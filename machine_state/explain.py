"""Deterministic explanation rendering from structured analysis."""

from __future__ import annotations

from typing import Any


def render_because(prefix: str, causes: list[dict[str, Any]]) -> dict[str, Any]:
    if not causes:
        return {
            "summary": prefix + " no strong deterministic causes were found.",
            "reasons": [],
        }

    reasons = [str(cause.get("summary", "")).strip() for cause in causes if cause.get("summary")]
    return {
        "summary": prefix + " " + "; ".join(reasons),
        "reasons": reasons,
    }
