"""Recovery size estimation for cleanup candidates (Phase 9)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import CleanupCandidate


@dataclass
class RecoverySummary:
    total_bytes: int
    safe_bytes: int
    review_bytes: int
    safe_count: int
    review_count: int


def estimate_recovery(candidates: list[CleanupCandidate]) -> RecoverySummary:
    """Sum up recoverable bytes by risk category."""
    safe_bytes = sum(c.size_bytes for c in candidates if c.risk == "safe")
    review_bytes = sum(c.size_bytes for c in candidates if c.risk == "review")
    return RecoverySummary(
        total_bytes=safe_bytes + review_bytes,
        safe_bytes=safe_bytes,
        review_bytes=review_bytes,
        safe_count=sum(1 for c in candidates if c.risk == "safe"),
        review_count=sum(1 for c in candidates if c.risk == "review"),
    )
