"""machine_state CLI subpackage.

Entry point: main()
Invoked as: python3 -m machine_state.cli <command> [args]
"""

from __future__ import annotations

import sys

from .parser import build_parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
