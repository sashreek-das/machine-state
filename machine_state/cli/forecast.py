"""CLI handler for Phase 8 predictive forecasting commands."""

from __future__ import annotations

import argparse

from .. import store
from ._utils import _print_json


def _forecast_command(args: argparse.Namespace) -> int:
    recent_snapshots = store.get_recent_snapshots(limit=24, db_path=args.db)
    latest_snapshot = recent_snapshots[0] if recent_snapshots else None
    if not latest_snapshot:
        _print_json({"status": "no_data", "reason": "No snapshots available. Run: collect"})
        return 1

    action = args.forecast_action

    if action == "disk":
        from ..forecasting.disk_growth import (
            forecast_disk_exhaustion, get_folder_growth_hotspots, estimate_disk_growth_rate,
        )
        _print_json({
            "exhaustion": forecast_disk_exhaustion(recent_snapshots),
            "growthRate": estimate_disk_growth_rate(recent_snapshots),
            "hotspots": get_folder_growth_hotspots(recent_snapshots, limit=args.limit),
        })
        return 0

    if action == "ram":
        from ..forecasting.pressure_prediction import (
            predict_ram_trajectory, identify_recurring_pressure_windows,
        )
        _print_json({
            "trajectory": predict_ram_trajectory(recent_snapshots),
            "recurringPressureWindows": identify_recurring_pressure_windows(recent_snapshots),
        })
        return 0

    if action == "workload":
        from ..forecasting.workload_patterns import get_workload_risk_summary, identify_slowdown_windows
        _print_json({
            "summary": get_workload_risk_summary(recent_snapshots),
            "slowdownWindows": identify_slowdown_windows(recent_snapshots),
        })
        return 0

    if action == "trends":
        from ..forecasting.trend_analysis import (
            get_app_memory_trends, compute_overall_risk_score, get_proactive_insights,
        )
        _print_json({
            "riskScore": compute_overall_risk_score(latest_snapshot, recent_snapshots),
            "appTrends": get_app_memory_trends(recent_snapshots, top_n=args.limit),
            "insights": get_proactive_insights(latest_snapshot, recent_snapshots),
        })
        return 0

    if action == "install":
        from ..forecasting.install_impact import simulate_install_impact, check_long_term_safety
        gb = args.size_gb or 0.0
        _print_json({
            "impact": simulate_install_impact(latest_snapshot, gb, recent_snapshots),
            "longTerm": check_long_term_safety(latest_snapshot, gb, recent_snapshots),
        })
        return 0

    _print_json({"status": "error", "reason": f"Unknown forecast action: {action}"})
    return 1
