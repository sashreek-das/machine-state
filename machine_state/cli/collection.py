"""CLI handlers for raw data collection: tool and collect commands."""

from __future__ import annotations

import argparse
from typing import Any

from .. import snapshot, store, tools
from ._utils import _print_json


def _tool_command(args: argparse.Namespace) -> int:
    try:
        if args.tool_name == "ram":
            _print_json(tools.get_ram_usage())
            return 0

        if args.tool_name == "disk":
            _print_json(tools.get_disk_usage(args.path or "/"))
            return 0

        if args.tool_name == "processes":
            _print_json(tools.get_top_processes_by_memory(limit=args.limit))
            return 0

        if args.tool_name == "project":
            if not args.path:
                raise SystemExit("--path is required for the project tool")
            _print_json(tools.analyze_project_folder(args.path, limit=args.limit))
            return 0

        if args.tool_name == "largest-items":
            if not args.path:
                raise SystemExit("--path is required for the largest-items tool")
            _print_json(tools.get_largest_items(args.path, limit=args.limit))
            return 0

        if args.tool_name == "system-inventory":
            _print_json(tools.get_system_inventory(args.path or "/", limit=args.limit, max_depth=args.max_depth))
            return 0
    except Exception as exc:
        _print_json(
            {
                "status": "unavailable",
                "tool": args.tool_name,
                "reason": str(exc),
            }
        )
        return 1

    raise SystemExit(f"Unsupported tool: {args.tool_name}")


def _collect_command(args: argparse.Namespace) -> int:
    from ..entity_history import record_snapshot_entities
    from ..events import detect_and_store_events

    built_snapshot = snapshot.build_snapshot(
        project_paths=args.project,
        process_limit=args.process_limit,
        item_limit=args.item_limit,
        full_system=args.full_system,
        system_item_limit=args.system_item_limit,
        system_max_depth=args.system_max_depth,
    )
    store_result = store.save_snapshot(built_snapshot, db_path=args.db)

    entity_counts = record_snapshot_entities(built_snapshot, db_path=args.db)
    recent = store.get_recent_snapshots(limit=2, db_path=args.db)
    detected_events: list[Any] = []
    if len(recent) >= 2:
        detected_events = detect_and_store_events(recent[1], recent[0], db_path=args.db)

    _print_json(
        {
            "status": "ok",
            "storedSnapshot": store_result,
            "entityCounts": entity_counts,
            "eventsDetected": len(detected_events),
            "snapshot": built_snapshot,
        }
    )
    return 0
