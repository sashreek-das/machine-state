"""CLI handler for `machine-state health` (Phase 9)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .. import store
from ..health import compute_health_score
from ._utils import _print_json

_B  = "\033[1m"
_R  = "\033[0m"
_D  = "\033[2m"
_GR = "\033[1;32m"
_YL = "\033[1;33m"
_RD = "\033[1;31m"


def _score_colour(score: int) -> str:
    if score >= 85:
        return _GR
    if score >= 65:
        return _YL
    return _RD


def _bar(ratio: float, width: int = 20) -> str:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(ratio * width)
    empty = width - filled
    col = _GR if ratio >= 0.65 else (_YL if ratio >= 0.45 else _RD)
    return f"{col}{'█' * filled}{_D}{'░' * empty}{_R}"


def _health_command(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        snapshots = store.get_recent_snapshots(limit=12, db_path=args.db)
        events    = store.get_events(limit=50, db_path=args.db)
        result    = compute_health_score(snapshots, events)
        scores    = store.get_health_scores(limit=10, db_path=args.db)
        result["history"] = scores
        _print_json(result)
        return 0

    snapshots = store.get_recent_snapshots(limit=12, db_path=args.db)
    events    = store.get_events(limit=50, db_path=args.db)
    h         = compute_health_score(snapshots, events)
    scores    = store.get_health_scores(limit=5, db_path=args.db)

    score = h["score"]
    label = h["label"]
    col   = _score_colour(score)
    comp  = h["components"]

    print()
    print(f"  {_bar(score / 100)}  {col}{_B}{score}{_R} / 100  {col}{label}{_R}")

    if len(scores) >= 2:
        prev = scores[1]["score"]
        delta = score - prev
        sign = "+" if delta >= 0 else ""
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        c = _GR if delta > 0 else (_RD if delta < 0 else _D)
        print(f"\n  Trend  {c}{arrow} {sign}{delta}{_R} vs previous snapshot")

    print(f"\n  {_D}Components{_R}")
    for key, val in comp.items():
        c = _score_colour(val)
        print(f"    {key:<12} {c}{val:>3}{_R}")

    print()
    return 0
