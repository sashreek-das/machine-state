"""CLI handler for `machine-state digest` (Phase 9)."""

from __future__ import annotations

import argparse

from ..digest import digest_path, week_key
from ._utils import _print_json


def _digest_command(args: argparse.Namespace) -> int:
    wk = getattr(args, "week", None) or week_key()

    if getattr(args, "list", False):
        from pathlib import Path
        reports_dir = Path.home() / ".machine-state" / "reports"
        if not reports_dir.exists():
            print("  No digests generated yet.")
            return 0
        files = sorted(reports_dir.glob("*.md"), reverse=True)
        for f in files:
            print(f"  {f.stem}  →  {f}")
        return 0

    if getattr(args, "generate", False):
        from ..digest import generate_digest
        out = generate_digest(wk=wk, db_path=args.db)
        print(f"  Written: {out}")
        return 0

    path = digest_path(wk)
    if not path.exists():
        print(f"  No digest for {wk}. Run with --generate to create it.")
        return 1

    print(path.read_text(encoding="utf-8"))
    return 0
