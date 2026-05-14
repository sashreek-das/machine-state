"""Shared return types for the machine_state runtime.

Every public function in the deterministic runtime that can fail or produce
partial results MUST return RuntimeResult. This contract exists so that:

  - The LLM context builder (llm/context_builder.py) has a stable, typed
    surface to consume — it never needs to guess at dict shapes.
  - Error conditions are explicit and surfaced, never silently swallowed.
  - The presence of errors does not prevent partial data from being returned.

Usage:

    from machine_state.types import RuntimeResult

    def get_pressure(snapshots: list[dict]) -> RuntimeResult:
        if not snapshots:
            return RuntimeResult.unavailable("No snapshots available.")
        ...
        return RuntimeResult(available=True, data={"level": "high"})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeResult:
    """Standard return type for all deterministic runtime functions.

    Attributes:
        available: True if data was produced; False if the operation could not
                   complete (missing data, insufficient history, etc.).
        data:      The result payload. Non-empty only when available=True.
        errors:    Non-fatal issues encountered during computation. May be
                   non-empty even when available=True (partial results).
        reason:    Human-readable explanation when available=False.
    """

    available: bool
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    reason: str = ""

    @classmethod
    def unavailable(cls, reason: str, errors: list[str] | None = None) -> RuntimeResult:
        """Construct a result that signals unavailability with a reason."""
        return cls(available=False, reason=reason, errors=errors or [])

    @classmethod
    def ok(cls, data: dict[str, Any], errors: list[str] | None = None) -> RuntimeResult:
        """Construct a successful result with optional non-fatal error notes."""
        return cls(available=True, data=data, errors=errors or [])

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON output and legacy dict consumers."""
        result: dict[str, Any] = {
            "available": self.available,
        }
        if self.available:
            result.update(self.data)
        else:
            result["reason"] = self.reason
        if self.errors:
            result["errors"] = self.errors
        return result
