"""CLI handler for `machine-state dash` (Phase 9)."""

from __future__ import annotations

import argparse


def _dash_command(args: argparse.Namespace) -> int:
    from ..tui import run_dashboard
    run_dashboard(db_path=args.db, interval=args.interval)
    return 0
