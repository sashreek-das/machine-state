"""Scheduler runner loop.

Implements the core scheduling loop that:
1. Polls for due domains every `poll_interval_seconds`
2. Builds incremental snapshots for only the due domains
3. Persists snapshots and detects events
4. Records entity history
5. Periodically rebuilds system memory
6. Is failure-safe: collection errors do not crash the loop
"""

from __future__ import annotations

import time
import traceback
from datetime import datetime, timezone
from typing import Any

from .config import SchedulerConfig
from .. import store
from ..entity_history import record_snapshot_entities
from ..events import detect_and_store_events
from ..incremental import get_due_domains, record_domain_collection, build_incremental_snapshot
from .. import memory as mem_module
from ..health import compute_health_score
from ..digest.generator import week_key, digest_path, generate_digest


def _log(log_file: Any, message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    try:
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def run_once(config: SchedulerConfig) -> dict[str, Any]:
    """Execute one collection cycle: check due domains, collect, persist.

    Returns a summary dict describing what was collected and any errors.
    """
    db_path = config.db_path
    due_domains = get_due_domains(db_path)

    if not due_domains:
        return {"collected": False, "reason": "No domains due for collection."}

    try:
        snapshot = build_incremental_snapshot(
            due_domains=due_domains,
            project_paths=config.project_paths,
            process_limit=config.process_limit,
            item_limit=config.item_limit,
            system_item_limit=config.system_item_limit,
            system_max_depth=config.system_max_depth,
        )
    except Exception as exc:
        return {
            "collected": False,
            "reason": f"Snapshot collection failed: {exc}",
            "traceback": traceback.format_exc(),
        }

    # Persist snapshot
    try:
        store.save_snapshot(snapshot, db_path)
    except Exception as exc:
        return {
            "collected": False,
            "reason": f"Snapshot persistence failed: {exc}",
        }

    # Record entity history
    try:
        record_snapshot_entities(snapshot, db_path)
    except Exception as exc:
        pass  # non-fatal; no log_file in scope here

    # Detect and store events (compare with previous snapshot)
    try:
        recent = store.get_recent_snapshots(limit=2, db_path=db_path)
        if len(recent) >= 2:
            detect_and_store_events(recent[1], recent[0], db_path)
    except Exception:
        pass  # non-fatal

    # Compute and persist composite health score
    try:
        recent12 = store.get_recent_snapshots(limit=12, db_path=db_path)
        events   = store.get_events(limit=50, db_path=db_path)
        health   = compute_health_score(recent12, events)
        store.save_health_score(
            ts=health["ts"],
            score=health["score"],
            label=health["label"],
            components=health["components"],
            db_path=db_path,
        )
    except Exception:
        pass  # non-fatal

    # Evaluate user-defined alert rules
    try:
        from ..alerts.loader import load_alert_rules
        from ..alerts.evaluator import evaluate_rules
        from ..alerts.dispatcher import dispatch_fires
        rules = load_alert_rules()
        if rules and recent12:
            fires = evaluate_rules(rules, recent12[0], health["score"])
            dispatch_fires(fires, db_path=db_path)
    except Exception:
        pass  # non-fatal

    # Record collection times for all due domains
    collected_at = snapshot.get("timestamp", datetime.now(timezone.utc).isoformat())
    for domain in due_domains:
        try:
            record_domain_collection(domain, collected_at, db_path)
        except Exception:
            pass  # non-fatal

    return {
        "collected": True,
        "timestamp": collected_at,
        "domainsCollected": due_domains,
    }


def run_scheduler_loop(config: SchedulerConfig, stop_flag: Any = None) -> None:
    """Run the scheduler loop until stop_flag is set (or forever).

    Args:
        config: Scheduler configuration.
        stop_flag: A threading.Event or similar object with an `is_set()` method.
                   If None, runs forever.
    """
    log_file = config.log_file
    poll_interval = config.poll_interval_seconds
    collection_count = 0

    _log(log_file, "Scheduler started.")
    _log(log_file, f"Config: {config.to_dict()}")

    while True:
        if stop_flag is not None and stop_flag.is_set():
            _log(log_file, "Stop flag set. Scheduler exiting.")
            break

        try:
            result = run_once(config)
            if result.get("collected"):
                collection_count += 1
                domains = result.get("domainsCollected", [])
                _log(log_file, f"Collected domains: {domains} (collection #{collection_count})")

                # Periodically rebuild system memory
                if (
                    config.rebuild_memory_every_n_collections > 0
                    and collection_count % config.rebuild_memory_every_n_collections == 0
                ):
                    try:
                        all_snapshots = store.get_all_snapshots(config.db_path, limit=200)
                        summary = mem_module.rebuild_system_memory(all_snapshots, config.db_path)
                        _log(log_file, f"System memory rebuilt: {summary}")
                    except Exception as exc:
                        _log(log_file, f"System memory rebuild failed: {exc}")

                # Generate weekly digest on the first cycle after a week boundary
                current_wk = week_key()
                if not hasattr(run_scheduler_loop, "_last_digest_wk"):
                    run_scheduler_loop._last_digest_wk = current_wk  # type: ignore[attr-defined]
                if current_wk != run_scheduler_loop._last_digest_wk:  # type: ignore[attr-defined]
                    run_scheduler_loop._last_digest_wk = current_wk  # type: ignore[attr-defined]
                    if not digest_path(current_wk).exists():
                        try:
                            out = generate_digest(db_path=config.db_path)
                            _log(log_file, f"Weekly digest written: {out}")
                        except Exception as exc:
                            _log(log_file, f"Digest generation failed: {exc}")
            else:
                reason = result.get("reason", "")
                if "No domains due" not in reason:
                    _log(log_file, f"Collection skipped: {reason}")
        except Exception as exc:
            _log(log_file, f"Scheduler loop error: {exc}\n{traceback.format_exc()}")

        # Sleep in small increments so stop_flag is checked promptly
        elapsed = 0
        while elapsed < poll_interval:
            if stop_flag is not None and stop_flag.is_set():
                break
            time.sleep(min(5, poll_interval - elapsed))
            elapsed += 5

    _log(log_file, "Scheduler stopped.")
