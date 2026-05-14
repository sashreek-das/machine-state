"""CLI handlers for the background scheduler daemon and notification engine."""

from __future__ import annotations

import argparse

from .. import store
from ._utils import _print_json


def _scheduler_command(args: argparse.Namespace) -> int:
    from ..scheduler import start_daemon, stop_daemon, get_status, SchedulerConfig

    config = SchedulerConfig(
        project_paths=args.project,
        process_limit=args.process_limit,
        item_limit=args.item_limit,
        system_item_limit=args.system_item_limit,
        system_max_depth=args.system_max_depth,
        db_path=args.db,
    )
    if args.scheduler_action == "start":
        _print_json(start_daemon(config))
    elif args.scheduler_action == "stop":
        _print_json(stop_daemon(config))
    elif args.scheduler_action == "status":
        _print_json(get_status(config))
    elif args.scheduler_action == "schedule":
        from ..incremental import get_schedule_status
        _print_json(get_schedule_status(args.db))
    elif args.scheduler_action == "run-once":
        from ..scheduler.runner import run_once
        result = run_once(config)
        _print_json(result)
    return 0


def _scheduler_daemon_command(args: argparse.Namespace) -> int:
    """Hidden command invoked by the scheduler daemon in PyInstaller mode.

    Called as: machine-state _scheduler-daemon '<config_json>'
    This is not intended for direct user invocation.
    """
    import json
    from pathlib import Path
    from ..scheduler.config import SchedulerConfig
    from ..scheduler.runner import run_scheduler_loop

    cfg_dict = json.loads(args.config_json)
    cfg = SchedulerConfig(
        domain_intervals=cfg_dict.get("domain_intervals", {}),
        project_paths=cfg_dict.get("project_paths", []),
        process_limit=cfg_dict.get("process_limit", 10),
        item_limit=cfg_dict.get("item_limit", 10),
        system_item_limit=cfg_dict.get("system_item_limit", 15),
        system_max_depth=cfg_dict.get("system_max_depth", 4),
        poll_interval_seconds=cfg_dict.get("poll_interval_seconds", 60),
        db_path=cfg_dict.get("db_path"),
        rebuild_memory_every_n_collections=cfg_dict.get("rebuild_memory_every_n_collections", 5),
    )
    cfg.pid_file = Path(cfg_dict["pid_file"])
    cfg.log_file = Path(cfg_dict["log_file"])
    run_scheduler_loop(cfg)
    return 0


def _notify_command(args: argparse.Namespace) -> int:
    from ..notifications import evaluate_and_notify, get_pending_notifications
    snapshots = store.get_recent_snapshots(limit=12, db_path=args.db)
    if not snapshots:
        _print_json({"status": "no_data", "reason": "No snapshots available."})
        return 1
    if args.dry_run:
        pending = get_pending_notifications(snapshots, db_path=args.db)
        _print_json({"pending": pending, "count": len(pending)})
    else:
        results = evaluate_and_notify(snapshots, db_path=args.db)
        _print_json({"results": results, "count": len(results)})
    return 0
