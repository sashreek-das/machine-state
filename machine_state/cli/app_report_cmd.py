"""CLI handler for `machine-state app-report <name>` (Phase 9)."""

from __future__ import annotations

import argparse

from ..constants import GB, MB
from ._utils import _print_json

_B  = "\033[1m"
_R  = "\033[0m"
_D  = "\033[2m"
_GR = "\033[1;32m"
_YL = "\033[1;33m"


def _fmt(n: int) -> str:
    if n >= GB:
        return f"{n / GB:.1f} GB"
    if n >= MB:
        return f"{n / MB:.0f} MB"
    return f"{n / 1024:.0f} KB"


def _app_report_command(args: argparse.Namespace) -> int:
    from ..app_report import get_app_report

    try:
        report = get_app_report(args.app_name, db_path=args.db)
    except ValueError as exc:
        print(f"  {exc}")
        return 1

    if getattr(args, "json", False):
        _print_json(report)
        return 0

    ram  = report.get("ram", {})
    sess = report.get("sessions", {})
    evts = report.get("events", {})

    print(f"\n  {_B}{report['application']}{_R}  —  behavioural profile\n")
    print(f"  {_D}{'─' * 50}{_R}\n")

    print(f"  {_B}Memory{_R}")
    if ram:
        print(f"    Average          {_fmt(ram.get('avgBytes', 0))}")
        print(f"    Peak             {_fmt(ram.get('peakBytes', 0))}")
        print(f"    Observations     {ram.get('observations', 0)}")

    print(f"\n  {_B}Sessions{_R}")
    print(f"    Observed         {sess.get('count', 0)}")
    if sess.get("avgDurationLabel"):
        print(f"    Avg length       {sess['avgDurationLabel']}")
    if sess.get("longestLabel"):
        print(f"    Longest          {sess['longestLabel']}")

    print(f"\n  {_B}Events{_R}")
    print(f"    Related events   {evts.get('relatedEvents', 0)}")
    print(f"    Critical events  {evts.get('criticalEvents', 0)}")

    print(f"\n  {_D}First seen  {report.get('firstSeen', '?')}{_R}")
    print(f"  {_D}Last seen   {report.get('lastSeen', '?')}{_R}\n")
    return 0
