"""CLI handler for the `setup` command."""

from __future__ import annotations

import argparse


def _setup_command(args: argparse.Namespace) -> int:
    from ..setup import run_setup
    return run_setup()
