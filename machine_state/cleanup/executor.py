"""Cleanup executor — deletes safe candidates after pre-flight checks (Phase 9).

Contract:
  - Only items with risk == "safe" are ever touched by execute_cleanup.
  - "review" items are listed but never auto-deleted.
  - Every deletion is logged to SQLite before the rmtree call.
  - If a path no longer exists at execution time, it is skipped silently.
  - dry_run=True prints what would be done but changes nothing.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import CleanupCandidate


@dataclass
class ExecutionResult:
    deleted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str]  = field(default_factory=list)
    bytes_freed: int   = 0


def execute_cleanup(
    candidates: list[CleanupCandidate],
    dry_run: bool = True,
    db_path: str | Path | None = None,
) -> ExecutionResult:
    """Delete all safe candidates (unless dry_run).

    Logs each deletion to SQLite before removing.
    """
    from .. import store

    result = ExecutionResult()
    safe = [c for c in candidates if c.risk == "safe"]

    for c in safe:
        if not c.path.exists():
            result.skipped.append(str(c.path))
            continue
        if dry_run:
            result.deleted.append(f"[dry-run] would remove {c.path}  ({c.size_bytes:,} bytes)")
            result.bytes_freed += c.size_bytes
            continue
        try:
            store.log_cleanup_deletion(
                str(c.path), c.category, c.size_bytes, db_path
            )
            if c.action == "empty trash":
                for item in c.path.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
            else:
                shutil.rmtree(c.path, ignore_errors=True)
            result.deleted.append(str(c.path))
            result.bytes_freed += c.size_bytes
        except OSError as exc:
            result.errors.append(f"{c.path}: {exc}")

    return result
