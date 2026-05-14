"""CLI handlers for Phase 4 runtime analysis: events, pressure, history, memory, relations."""

from __future__ import annotations

import argparse

from .. import store
from ._utils import _print_json


def _events_command(args: argparse.Namespace) -> int:
    events = store.get_events(
        limit=args.limit,
        domain=args.domain or None,
        event_type=args.type or None,
        db_path=args.db,
    )
    _print_json({"events": events, "count": len(events)})
    return 0


def _pressure_command(args: argparse.Namespace) -> int:
    from ..pressure import compute_live_pressure
    snapshots = store.get_recent_snapshots(limit=args.window, db_path=args.db)
    if not snapshots:
        _print_json({"status": "no_data", "reason": "No snapshots available."})
        return 1
    result = compute_live_pressure(snapshots, window=args.window)
    _print_json(result)
    return 0


def _history_command(args: argparse.Namespace) -> int:
    from ..entity_history import get_entity_profile, list_tracked_entities
    if args.entity_id:
        _print_json(get_entity_profile(args.entity_id, db_path=args.db))
    else:
        entities = list_tracked_entities(db_path=args.db)
        _print_json({"entities": entities, "count": len(entities)})
    return 0


def _memory_command(args: argparse.Namespace) -> int:
    from .. import memory as mem_module
    if args.rebuild:
        snapshots = store.get_all_snapshots(db_path=args.db)
        summary = mem_module.rebuild_system_memory(snapshots, db_path=args.db)
        _print_json({"status": "rebuilt", "summary": summary})
    elif args.key == "heavy-apps":
        _print_json({"heavyApplications": mem_module.get_heavy_applications(db_path=args.db)})
    elif args.key == "growing-folders":
        _print_json({"growingFolders": mem_module.get_growing_folders(db_path=args.db)})
    elif args.key == "ram-spikes":
        _print_json(mem_module.get_ram_spike_pattern(db_path=args.db))
    elif args.key == "cleanup":
        _print_json({"cleanupCandidates": mem_module.get_cleanup_candidates(db_path=args.db)})
    elif args.key == "slowdowns":
        _print_json(mem_module.get_slowdown_periods(db_path=args.db))
    else:
        _print_json(mem_module.get_system_memory(db_path=args.db))
    return 0


def _temporal_relations_command(args: argparse.Namespace) -> int:
    from ..relations import build_temporal_relationships
    snapshots = store.get_all_snapshots(db_path=args.db)
    if not snapshots:
        _print_json({"status": "no_data", "reason": "No snapshots available."})
        return 1
    result = build_temporal_relationships(snapshots)
    _print_json(result)
    return 0
