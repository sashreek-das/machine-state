"""Execution planner.

Maps a detected intent to an ordered sequence of tool calls, validates
arguments, executes each tool against the runtime, and aggregates results.

The planner enforces the contract layer:
  - Only registered tools can be called
  - Arguments are validated before execution
  - No arbitrary code paths or system access is exposed
  - Unsafe tools (safe=False) are never executed
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any

from .contracts import TOOL_REGISTRY
from .intents import Intent, detect_intent
from .validators import validate_arguments
from ..constants import GB, DISK_PRESSURE_CRITICAL, DISK_PRESSURE_HIGH


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    status: str = "pending"  # pending | ok | error | blocked


@dataclass
class ExecutionPlan:
    intent: str
    intent_description: str
    query: str
    steps: list[ToolCall]


@dataclass
class PlanResult:
    intent: str
    query: str
    status: str              # ok | partial | error | unknown
    steps: list[dict[str, Any]]
    aggregated: dict[str, Any]
    safe: bool = True


# ── Execution context ──────────────────────────────────────────────────────────

@dataclass
class ExecutionContext:
    snapshot: dict[str, Any]
    recent_snapshots: list[dict[str, Any]]
    db_path: str


# ── Tool executors ─────────────────────────────────────────────────────────────

def _exec_get_machine_health(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..pressure.engine import compute_live_pressure
    from ..semantic.pressure import build_semantic_pressure_report
    from ..semantic.capabilities import system_capability_summary

    raw_pressure = compute_live_pressure(ctx.recent_snapshots)
    pressure = build_semantic_pressure_report(raw_pressure)
    capabilities = system_capability_summary(ctx.snapshot, raw_pressure)
    return {
        "pressure": pressure,
        "capabilities": capabilities,
        "overallHealthy": capabilities.get("overallHealthy", False),
        "recommendations": capabilities.get("recommendations", []),
    }


def _exec_get_pressure_summary(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..pressure.engine import compute_live_pressure
    from ..semantic.pressure import build_semantic_pressure_report

    window = int(args.get("window", 6))
    snapshots = ctx.recent_snapshots[-window:] if len(ctx.recent_snapshots) > window else ctx.recent_snapshots
    raw = compute_live_pressure(snapshots, window=window)
    return build_semantic_pressure_report(raw)


def _exec_get_system_storage(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..semantic.storage import build_storage_semantic_summary

    # Prefer a snapshot that has inventory data
    best = next(
        (s for s in ctx.recent_snapshots
         if s.get("availability", {}).get("system", {}).get("inventory", {}).get("available")),
        ctx.snapshot,
    )
    return build_storage_semantic_summary(best)


def _exec_get_application_usage(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..semantic.applications import build_all_application_profiles
    from ..relations import build_temporal_relationships

    top_n = int(args.get("top_n", 5))
    temporal = build_temporal_relationships(ctx.recent_snapshots)
    temporal_list = temporal.get("temporalRelationships", [])
    profiles = build_all_application_profiles(ctx.snapshot, temporal_relationships=temporal_list)
    return {"applications": profiles[:top_n]}


def _exec_get_app_profile(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..semantic.applications import build_application_semantic_profile
    from ..entity_history.builder import get_application_profile

    name = str(args.get("name", "")).strip()
    if not name:
        return {"available": False, "reason": "No application name provided."}

    entity_id = f"application:{name.lower()}"
    history = get_application_profile(entity_id, ctx.db_path)
    return build_application_semantic_profile(name, history, 0.0)


def _exec_check_install_compatibility(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..semantic.capabilities import can_install

    app_name = str(args.get("app_name", "")).strip()
    required_gb = float(args.get("required_gb", 0.0))
    required_bytes = int(required_gb * GB)
    return can_install(ctx.snapshot, required_bytes, app_name or None)


def _exec_get_activity_pattern(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..semantic.activity import build_activity_pattern
    return build_activity_pattern(ctx.recent_snapshots)


def _exec_get_ram_info(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..semantic.capabilities import ram_capability
    return ram_capability(ctx.snapshot)


def _exec_get_disk_info(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    disk = ctx.snapshot.get("system", {}).get("disk", {})
    total = int(disk.get("totalBytes") or 0)
    used = int(disk.get("usedBytes") or 0)
    free = int(disk.get("freeBytes") or 0)
    percent_used = round(used / total * 100, 1) if total > 0 else 0.0
    ratio = percent_used / 100.0
    status = "critical" if ratio >= DISK_PRESSURE_CRITICAL else ("low" if ratio >= DISK_PRESSURE_HIGH else "healthy")
    return {
        "totalGB": round(total / GB, 2),
        "usedGB": round(used / GB, 2),
        "freeGB": round(free / GB, 2),
        "percentUsed": percent_used,
        "status": status,
    }


def _exec_get_top_processes(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    limit = int(args.get("limit", 5))
    apps = ctx.snapshot.get("derived", {}).get("applications", [])
    sorted_apps = sorted(apps, key=lambda a: -(int(a.get("totalMemoryBytes") or 0)))
    total_ram = int(ctx.snapshot.get("system", {}).get("ram", {}).get("totalBytes") or 1)
    result = []
    for app in sorted_apps[:limit]:
        mem = int(app.get("totalMemoryBytes") or 0)
        result.append({
            "application": app.get("application"),
            "memoryGB": round(mem / GB, 2),
            "ramPercent": round(mem / total_ram * 100, 1),
            "processCount": app.get("processCount", 1),
        })
    return {"processes": result}


def _exec_get_events(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..store import get_events

    limit = int(args.get("limit", 10))
    event_type = str(args.get("event_type", "")).strip()
    events = get_events(db_path=ctx.db_path)
    if event_type:
        events = [e for e in events if e.get("eventType") == event_type]
    return {"events": events[:limit], "total": len(events)}


def _exec_get_entity_history(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..entity_history.builder import get_entity_profile

    entity_id = str(args.get("entity_id", "")).strip()
    if not entity_id:
        return {"available": False, "reason": "No entity_id provided."}
    return get_entity_profile(entity_id, ctx.db_path)


# ── Phase 8: Predictive executors ──────────────────────────────────────────────

def _exec_forecast_disk_growth(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..forecasting.disk_growth import (
        forecast_disk_exhaustion,
        get_folder_growth_hotspots,
        estimate_disk_growth_rate,
    )
    threshold = float(args.get("threshold_percent", 95.0))
    limit = int(args.get("limit", 5))
    return {
        "exhaustion": forecast_disk_exhaustion(ctx.recent_snapshots, threshold_percent=threshold),
        "growthHotspots": get_folder_growth_hotspots(ctx.recent_snapshots, limit=limit),
        "growthRate": estimate_disk_growth_rate(ctx.recent_snapshots),
    }


def _exec_predict_ram_pressure(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..forecasting.pressure_prediction import (
        predict_ram_trajectory,
        identify_recurring_pressure_windows,
    )
    return {
        "trajectory": predict_ram_trajectory(ctx.recent_snapshots),
        "recurringPressureWindows": identify_recurring_pressure_windows(ctx.recent_snapshots),
    }


def _exec_simulate_install(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..forecasting.install_impact import simulate_install_impact, check_long_term_safety

    required_gb = float(args.get("required_gb", 0.0))
    return {
        "impact": simulate_install_impact(ctx.snapshot, required_gb, ctx.recent_snapshots),
        "longTerm": check_long_term_safety(ctx.snapshot, required_gb, ctx.recent_snapshots),
    }


def _exec_analyze_workload(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..forecasting.workload_patterns import get_workload_risk_summary, identify_slowdown_windows

    return {
        "summary": get_workload_risk_summary(ctx.recent_snapshots),
        "slowdownWindows": identify_slowdown_windows(ctx.recent_snapshots),
    }


def _exec_get_system_trends(args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from ..forecasting.trend_analysis import (
        get_app_memory_trends,
        compute_overall_risk_score,
        get_proactive_insights,
    )
    top_n = int(args.get("top_n", 5))
    return {
        "riskScore": compute_overall_risk_score(ctx.snapshot, ctx.recent_snapshots),
        "appTrends": get_app_memory_trends(ctx.recent_snapshots, top_n=top_n),
        "insights": get_proactive_insights(ctx.snapshot, ctx.recent_snapshots),
    }


# ── Executor registry ──────────────────────────────────────────────────────────

_EXECUTORS: dict[str, Any] = {
    "get_machine_health": _exec_get_machine_health,
    "get_pressure_summary": _exec_get_pressure_summary,
    "get_system_storage": _exec_get_system_storage,
    "get_application_usage": _exec_get_application_usage,
    "get_app_profile": _exec_get_app_profile,
    "check_install_compatibility": _exec_check_install_compatibility,
    "get_activity_pattern": _exec_get_activity_pattern,
    "get_ram_info": _exec_get_ram_info,
    "get_disk_info": _exec_get_disk_info,
    "get_top_processes": _exec_get_top_processes,
    "get_events": _exec_get_events,
    "get_entity_history": _exec_get_entity_history,
    "forecast_disk_growth": _exec_forecast_disk_growth,
    "predict_ram_pressure": _exec_predict_ram_pressure,
    "simulate_install": _exec_simulate_install,
    "analyze_workload": _exec_analyze_workload,
    "get_system_trends": _exec_get_system_trends,
}


# ── Result aggregation ─────────────────────────────────────────────────────────

def _aggregate(intent: str, results: dict[str, Any], query: str) -> dict[str, Any]:
    """Combine tool results into an intent-specific aggregated response."""

    if intent == "install_feasibility":
        compat = results.get("check_install_compatibility", {})
        storage = results.get("get_system_storage", {})
        return {
            "feasible": compat.get("feasible"),
            "recommendation": compat.get("recommendation"),
            "requiredGB": compat.get("requiredGB"),
            "freeGB": compat.get("freeGB"),
            "remainingAfterInstallGB": compat.get("remainingAfterInstallGB"),
            "hasSafeBuffer": compat.get("hasSafeBuffer"),
            "storageStatus": storage.get("status"),
            "cleanupPotentialGB": storage.get("breakdown", {}).get("cleanupPotentialGB"),
        }

    if intent == "compatibility_check":
        health = results.get("get_machine_health", {})
        ram = results.get("get_ram_info", {})
        disk = results.get("get_disk_info", {})
        caps = health.get("capabilities", {})
        return {
            "canRunHeavyApp": caps.get("capabilities", {}).get("canRunHeavyApp"),
            "canRunModerateApp": caps.get("capabilities", {}).get("canRunModerateApp"),
            "canInstallLargeApp": caps.get("capabilities", {}).get("canInstallLargeApp"),
            "ramAvailableGB": ram.get("availableGB"),
            "diskFreeGB": disk.get("freeGB"),
            "overallHealthy": health.get("overallHealthy"),
            "recommendations": health.get("recommendations", []),
        }

    if intent == "slowdown_analysis":
        pressure = results.get("get_pressure_summary", {})
        processes = results.get("get_top_processes", {}).get("processes", [])
        events = results.get("get_events", {}).get("events", [])
        activity = results.get("get_activity_pattern", {})
        overall = pressure.get("overall", {})
        return {
            "primaryCause": overall.get("label", "Unknown"),
            "pressureState": overall.get("state"),
            "pressureMeaning": overall.get("meaning"),
            "topMemoryConsumers": processes[:3],
            "recentEvents": [
                {"type": e.get("event_type") or e.get("eventType"), "severity": e.get("severity")}
                for e in events[:5]
            ],
            "systemBehavior": activity.get("systemBehavior"),
            "pressurePattern": activity.get("pressurePattern"),
            "recommendations": [
                pressure.get("ram", {}).get("recommendation"),
                pressure.get("disk", {}).get("recommendation"),
            ],
        }

    if intent == "health_check":
        health = results.get("get_machine_health", {})
        pressure = health.get("pressure", {})
        caps = health.get("capabilities", {})
        return {
            "overallHealthy": health.get("overallHealthy"),
            "pressureState": pressure.get("overall", {}).get("state"),
            "pressureLabel": pressure.get("overall", {}).get("label"),
            "capabilities": caps.get("capabilities", {}),
            "recommendations": health.get("recommendations", []),
        }

    if intent == "pressure_analysis":
        pressure = results.get("get_pressure_summary", {})
        processes = results.get("get_top_processes", {}).get("processes", [])
        return {
            "overall": pressure.get("overall", {}),
            "ram": pressure.get("ram", {}),
            "disk": pressure.get("disk", {}),
            "topContributors": processes,
        }

    if intent == "storage_cleanup_advice":
        storage = results.get("get_system_storage", {})
        breakdown = storage.get("breakdown", {})
        return {
            "freeGB": storage.get("freeGB"),
            "status": storage.get("status"),
            "cleanupCandidates": breakdown.get("cleanupCandidates", []),
            "cleanupPotentialGB": breakdown.get("cleanupPotentialGB"),
            "topCategories": [
                {"label": c["label"], "sizeGB": c["sizeGB"], "cleanupSafe": c["cleanupSafe"]}
                for c in (breakdown.get("categories") or [])[:5]
            ],
        }

    if intent == "activity_analysis":
        activity = results.get("get_activity_pattern", {})
        usage = results.get("get_application_usage", {})
        return {
            "systemBehavior": activity.get("systemBehaviorLabel"),
            "pressurePattern": activity.get("pressurePatternLabel"),
            "peakHours": activity.get("topPeakHours", []),
            "dominantApplications": activity.get("dominantApplications", []),
            "applicationProfiles": usage.get("applications", []),
        }

    if intent == "app_profile_query":
        profile = results.get("get_app_profile", {})
        return profile

    if intent == "ram_query":
        return results.get("get_ram_info", {})

    if intent == "disk_query":
        disk = results.get("get_disk_info", {})
        storage = results.get("get_system_storage", {})
        return {
            "freeGB": disk.get("freeGB"),
            "usedGB": disk.get("usedGB"),
            "totalGB": disk.get("totalGB"),
            "percentUsed": disk.get("percentUsed"),
            "status": disk.get("status"),
            "cleanupPotentialGB": storage.get("breakdown", {}).get("cleanupPotentialGB"),
        }

    if intent == "restart_safety":
        health = results.get("get_machine_health", {})
        pressure = results.get("get_pressure_summary", {})
        processes = results.get("get_top_processes", {}).get("processes", [])
        overall = pressure.get("overall", {})
        ram = pressure.get("ram", {})
        disk = pressure.get("disk", {})
        pressure_state = overall.get("state", "unknown")
        safe_to_restart = pressure_state not in ("critical", "sustained_critical")
        return {
            "safeToRestart": safe_to_restart,
            "pressureState": pressure_state,
            "pressureLabel": overall.get("label", "unknown"),
            "pressureMeaning": overall.get("meaning"),
            "ramRecommendation": ram.get("recommendation"),
            "diskRecommendation": disk.get("recommendation"),
            "overallHealthy": health.get("overallHealthy"),
            "topProcesses": processes[:5],
        }

    if intent == "disk_forecast":
        disk_data = results.get("forecast_disk_growth", {})
        return {
            "exhaustion": disk_data.get("exhaustion", {}),
            "growthHotspots": disk_data.get("growthHotspots", []),
            "growthRate": disk_data.get("growthRate", {}),
        }

    if intent == "pressure_forecast":
        pressure_data = results.get("predict_ram_pressure", {})
        return {
            "trajectory": pressure_data.get("trajectory", {}),
            "recurringPressureWindows": pressure_data.get("recurringPressureWindows", {}),
        }

    if intent == "install_impact":
        sim_data = results.get("simulate_install", {})
        disk_data = results.get("forecast_disk_growth", {})
        return {
            "impact": sim_data.get("impact", {}),
            "longTerm": sim_data.get("longTerm", {}),
            "diskGrowthRate": disk_data.get("growthRate", {}),
        }

    if intent == "workload_analysis":
        workload = results.get("analyze_workload", {})
        return {
            "summary": workload.get("summary", {}),
            "slowdownWindows": workload.get("slowdownWindows", {}),
        }

    if intent == "trend_analysis":
        trends = results.get("get_system_trends", {})
        workload = results.get("analyze_workload", {})
        return {
            "riskScore": trends.get("riskScore", {}),
            "appTrends": trends.get("appTrends", []),
            "insights": trends.get("insights", []),
            "workloadSummary": workload.get("summary", {}),
        }

    # Default: return all results merged
    merged: dict[str, Any] = {}
    for v in results.values():
        if isinstance(v, dict):
            merged.update(v)
    return merged


# ── Plan builder ───────────────────────────────────────────────────────────────

def build_plan(query: str) -> ExecutionPlan:
    """Detect the intent and construct an execution plan."""
    intent = detect_intent(query)
    steps: list[ToolCall] = []

    for tool_name in intent.tools:
        tool_args = intent.parameters.get(tool_name, {})
        # Skip tools not in registry (safety check)
        if tool_name not in TOOL_REGISTRY:
            continue
        steps.append(ToolCall(tool_name=tool_name, arguments=tool_args))

    return ExecutionPlan(
        intent=intent.name,
        intent_description=intent.description,
        query=query,
        steps=steps,
    )


# ── Plan executor ──────────────────────────────────────────────────────────────

def execute_plan(
    plan: ExecutionPlan,
    snapshot: dict[str, Any],
    recent_snapshots: list[dict[str, Any]],
    db_path: str,
) -> PlanResult:
    """Execute an already-built plan against the runtime."""
    if plan.intent == "unknown":
        return PlanResult(
            intent="unknown",
            query=plan.query,
            status="unknown",
            steps=[],
            aggregated={},
            safe=True,
        )

    ctx = ExecutionContext(
        snapshot=snapshot,
        recent_snapshots=recent_snapshots,
        db_path=db_path,
    )

    step_results: list[dict[str, Any]] = []
    tool_outputs: dict[str, Any] = {}
    any_error = False

    for step in plan.steps:
        tool = TOOL_REGISTRY.get(step.tool_name)

        # Safety gate: block unsafe tools
        if tool and not tool.safe:
            step.status = "blocked"
            step.error = f"Tool '{step.tool_name}' is marked unsafe and cannot be executed."
            step_results.append({
                "tool": step.tool_name,
                "status": "blocked",
                "error": step.error,
            })
            any_error = True
            continue

        # Validate arguments
        validation = validate_arguments(step.tool_name, step.arguments)
        if not validation.valid:
            step.status = "error"
            step.error = f"Invalid arguments: {validation.first_error()}"
            step_results.append({
                "tool": step.tool_name,
                "status": "error",
                "error": step.error,
            })
            any_error = True
            continue

        # Execute
        executor = _EXECUTORS.get(step.tool_name)
        if executor is None:
            step.status = "error"
            step.error = f"No executor registered for tool '{step.tool_name}'"
            step_results.append({
                "tool": step.tool_name,
                "status": "error",
                "error": step.error,
            })
            any_error = True
            continue

        try:
            result = executor(validation.coerced_args, ctx)
            step.result = result
            step.status = "ok"
            tool_outputs[step.tool_name] = result
            step_results.append({
                "tool": step.tool_name,
                "status": "ok",
                "result": result,
            })
        except Exception as exc:
            step.status = "error"
            step.error = str(exc)
            step_results.append({
                "tool": step.tool_name,
                "status": "error",
                "error": step.error,
                "traceback": traceback.format_exc(),
            })
            any_error = True

    aggregated = _aggregate(plan.intent, tool_outputs, plan.query)
    status = "partial" if any_error else "ok"

    return PlanResult(
        intent=plan.intent,
        query=plan.query,
        status=status,
        steps=step_results,
        aggregated=aggregated,
        safe=True,
    )


# ── Primary entry point ────────────────────────────────────────────────────────

def run_query(
    query: str,
    snapshot: dict[str, Any],
    recent_snapshots: list[dict[str, Any]],
    db_path: str,
) -> PlanResult:
    """Detect intent, build plan, execute, and return aggregated results."""
    plan = build_plan(query)
    return execute_plan(plan, snapshot, recent_snapshots, db_path)
