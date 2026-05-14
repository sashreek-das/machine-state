"""CLI handler for the ask command — deterministic query routing."""

from __future__ import annotations

import argparse

from .. import query, store
from ._utils import _print_json


def _ask_command(args: argparse.Namespace) -> int:
    from ..planner.planner import run_query, build_plan
    from ..planner.intents import detect_intent

    recent_snapshots = store.get_recent_snapshots(limit=args.history_limit, db_path=args.db)
    latest_snapshot = recent_snapshots[0] if recent_snapshots else None
    previous_snapshot = recent_snapshots[1] if len(recent_snapshots) > 1 else None

    # Phase 6: try the planner first
    intent = detect_intent(args.query)
    if intent.name != "unknown" and latest_snapshot is not None:
        db_path = args.db or str(store.DEFAULT_DB_PATH)
        result = run_query(args.query, latest_snapshot, recent_snapshots, db_path)
        _print_json({
            "status": result.status,
            "domain": "planner",
            "intent": result.intent,
            "query": result.query,
            "singleAnswer": result.aggregated,
            "steps": result.steps,
            "snapshotTimestamp": latest_snapshot.get("timestamp"),
        })
        return 0

    # Fallback to Phase 1–5 query routing
    response = query.answer_query(
        latest_snapshot,
        args.query,
        previous_snapshot=previous_snapshot,
        recent_snapshots=recent_snapshots,
    )
    _print_json(response)
    return 0
