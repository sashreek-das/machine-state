"""CLI handler for Phase 5 semantic machine understanding."""

from __future__ import annotations

import argparse

from .. import store
from ..constants import GB
from ._utils import _print_json


def _semantic_command(args: argparse.Namespace) -> int:
    from ..semantic import applications as sem_apps
    from ..semantic import storage as sem_storage
    from ..semantic import capabilities as sem_cap
    from ..semantic import pressure as sem_pressure
    from ..semantic import activity as sem_activity
    from ..pressure import compute_live_pressure
    from ..relations import build_temporal_relationships
    from ..entity_history import get_application_profile

    db_path = args.db
    action = args.semantic_action

    if action == "pressure":
        snapshots = store.get_recent_snapshots(limit=8, db_path=db_path)
        if not snapshots:
            _print_json({"status": "no_data"})
            return 1
        live = compute_live_pressure(snapshots)
        report = sem_pressure.build_semantic_pressure_report(live)
        _print_json(report)
        return 0

    if action == "storage":
        snapshots = store.get_recent_snapshots(limit=8, db_path=db_path)
        best = next(
            (s for s in snapshots
             if s.get("availability", {}).get("system", {}).get("inventory", {}).get("available")),
            snapshots[0] if snapshots else None,
        )
        if not best:
            _print_json({"status": "no_data"})
            return 1
        _print_json(sem_storage.build_storage_semantic_summary(best))
        return 0

    if action == "app":
        app_name = args.app_name or ""
        if not app_name:
            _print_json({"status": "error", "reason": "Provide --name <application>."})
            return 1
        entity_id = f"application:{app_name.strip().lower()}"
        hist = get_application_profile(entity_id, db_path=db_path)

        all_snapshots = store.get_all_snapshots(db_path=db_path)
        temporal = build_temporal_relationships(all_snapshots)
        strength = next(
            (r["strength"] for r in temporal.get("temporalRelationships", [])
             if r["from"] == entity_id),
            None,
        )
        profile = sem_apps.build_application_semantic_profile(app_name, hist, strength)
        _print_json(profile)
        return 0

    if action == "capability":
        snapshot = store.get_latest_snapshot(db_path=db_path)
        if not snapshot:
            _print_json({"status": "no_data"})
            return 1
        snapshots = store.get_recent_snapshots(limit=8, db_path=db_path)
        live = compute_live_pressure(snapshots)
        summary = sem_cap.system_capability_summary(snapshot, live)

        if args.install_size_gb and args.install_size_gb > 0:
            install_bytes = int(args.install_size_gb * GB)
            feasibility = sem_cap.can_install(snapshot, install_bytes, args.install_app)
            summary["installFeasibility"] = feasibility

        _print_json(summary)
        return 0

    if action == "activity":
        snapshots = store.get_all_snapshots(db_path=db_path)
        if not snapshots:
            _print_json({"status": "no_data"})
            return 1
        _print_json(sem_activity.build_activity_pattern(snapshots))
        return 0

    if action == "summary":
        snapshot = store.get_latest_snapshot(db_path=db_path)
        all_snapshots = store.get_all_snapshots(db_path=db_path)
        recent_snapshots = store.get_recent_snapshots(limit=8, db_path=db_path)

        if not snapshot:
            _print_json({"status": "no_data"})
            return 1

        live = compute_live_pressure(recent_snapshots)
        pressure_report = sem_pressure.build_semantic_pressure_report(live)

        best_snap = next(
            (s for s in recent_snapshots
             if s.get("availability", {}).get("system", {}).get("inventory", {}).get("available")),
            snapshot,
        )
        storage_summary = sem_storage.build_storage_semantic_summary(best_snap)
        cap_summary = sem_cap.system_capability_summary(snapshot, live)

        temporal = build_temporal_relationships(all_snapshots)
        app_profiles = sem_apps.build_all_application_profiles(
            snapshot,
            temporal_relationships=temporal.get("temporalRelationships", []),
        )
        heavy = sem_apps.get_heavy_applications(app_profiles)
        activity = sem_activity.build_activity_pattern(all_snapshots)

        _print_json({
            "pressure": pressure_report,
            "storage": {
                "freeGB": storage_summary["freeGB"],
                "usedGB": storage_summary["usedGB"],
                "status": storage_summary["status"],
                "safeForLargeInstall": storage_summary["safeForLargeInstall"],
            },
            "capabilities": cap_summary["capabilities"],
            "recommendations": cap_summary["recommendations"],
            "heavyApplications": [
                {
                    "name": p["name"],
                    "category": p["category"],
                    "liveMemoryGB": p["liveMemoryGB"],
                    "pressureImpact": p["pressureImpact"],
                }
                for p in heavy
            ],
            "activity": {
                "systemBehavior": activity.get("systemBehaviorLabel"),
                "pressurePattern": activity.get("pressurePatternLabel"),
                "topPeakHours": activity.get("topPeakHours"),
            },
        })
        return 0

    _print_json({"status": "error", "reason": f"Unknown semantic action: {action}"})
    return 1
