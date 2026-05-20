"""Cleanup engine — scan, estimate, and execute disk space recovery (Phase 9)."""

from .scanner import CleanupCandidate, scan_cleanup_candidates
from .estimator import estimate_recovery
from .executor import execute_cleanup

__all__ = [
    "CleanupCandidate",
    "scan_cleanup_candidates",
    "estimate_recovery",
    "execute_cleanup",
]
