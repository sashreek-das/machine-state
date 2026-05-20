"""CLI handler for `machine-state cleanup` (Phase 9)."""

from __future__ import annotations

import argparse

from ..constants import GB, MB
from ._utils import _print_json

_B  = "\033[1m"
_R  = "\033[0m"
_D  = "\033[2m"
_GR = "\033[1;32m"
_YL = "\033[1;33m"
_RD = "\033[1;31m"


def _fmt(n: int) -> str:
    if n >= GB:
        return f"{n / GB:.1f} GB"
    if n >= MB:
        return f"{n / MB:.0f} MB"
    return f"{n / 1024:.0f} KB"


def _cleanup_command(args: argparse.Namespace) -> int:
    from ..cleanup import scan_cleanup_candidates, estimate_recovery, execute_cleanup

    if not getattr(args, "json", False):
        print("\n  Scanning for reclaimable space...", end="", flush=True)
    candidates = scan_cleanup_candidates()
    if not getattr(args, "json", False):
        print(f"\r\033[K", end="")

    if not candidates:
        print("  Nothing significant found to clean up.")
        return 0

    summary = estimate_recovery(candidates)

    if getattr(args, "json", False):
        _print_json({
            "candidates": [
                {"category": c.category, "path": str(c.path),
                 "size_bytes": c.size_bytes, "risk": c.risk, "action": c.action}
                for c in candidates
            ],
            "total_bytes": summary.total_bytes,
            "safe_bytes": summary.safe_bytes,
            "review_bytes": summary.review_bytes,
        })
        return 0

    print(f"\n  Found {_fmt(summary.total_bytes)} of reclaimable space:\n")
    header = f"  {'Category':<30} {'Size':<10} {'Risk':<8} Action"
    print(f"  {_D}{'-' * 60}{_R}")
    print(f"  {_D}{header.strip()}{_R}")
    print(f"  {_D}{'-' * 60}{_R}")
    for c in candidates:
        col = _GR if c.risk == "safe" else _YL
        print(f"  {c.category:<30} {_fmt(c.size_bytes):<10} "
              f"{col}{c.risk:<8}{_R} {_D}{c.action}{_R}")
    print(f"  {_D}{'-' * 60}{_R}")

    if getattr(args, "apply", False):
        print(f"\n  Applying safe deletions ({_fmt(summary.safe_bytes)})...")
        result = execute_cleanup(
            candidates, dry_run=False, db_path=getattr(args, "db", None)
        )
        for path in result.deleted:
            print(f"  {_GR}✓{_R}  {path}")
        for err in result.errors:
            print(f"  {_RD}✗{_R}  {err}")
        print(f"\n  Freed {_fmt(result.bytes_freed)}.")
    elif getattr(args, "dry_run", False):
        result = execute_cleanup(candidates, dry_run=True)
        print(f"\n  {_D}Dry run — nothing deleted:{_R}")
        for line in result.deleted:
            print(f"  {_D}{line}{_R}")
    else:
        print(f"\n  {_D}Run with --apply to remove safe items "
              f"({_fmt(summary.safe_bytes)}).{_R}")
        print(f"  {_D}Run with --dry-run to preview exact paths.{_R}")

    print()
    return 0
