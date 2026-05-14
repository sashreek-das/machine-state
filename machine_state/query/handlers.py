"""Domain answer builders for the query layer.

Each _answer_* function takes a query string, a timestamp, and domain-specific
data, and returns a structured result dict.  All heavy lifting (intent detection,
parameter extraction) is delegated to intents.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import causal, derived, diff, explain, forecast, timeline
from ..constants import GB, RAM_PRESSURE_HIGH, DISK_PRESSURE_CRITICAL
from .intents import (
    extract_top_n,
    extract_named_folder,
    extract_named_application,
)


# ── Result constructors ───────────────────────────────────────────────────────

def unavailable(
    query: str,
    snapshot_timestamp: str | None,
    reason: str,
    domain: str | None = None,
    operation: str | None = None,
) -> dict[str, Any]:
    return {
        "query": query,
        "snapshotTimestamp": snapshot_timestamp,
        "status": "unavailable",
        "domain": domain,
        "operation": operation,
        "reason": reason,
    }


def ok(
    query: str,
    snapshot_timestamp: str,
    domain: str,
    operation: str,
    single_answer: Any,
    supporting_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "query": query,
        "snapshotTimestamp": snapshot_timestamp,
        "status": "ok",
        "domain": domain,
        "operation": operation,
        "singleAnswer": single_answer,
        "supportingEvidence": supporting_evidence,
    }


# ── Availability guard ────────────────────────────────────────────────────────

def check_domain_availability(
    availability: dict[str, Any],
    domain: str,
    payload: Any,
    query: str,
    timestamp: str,
    operation: str,
) -> dict[str, Any] | None:
    if domain not in {"applications", "processes", "disk", "ram"}:
        return None
    meta_key = "processes" if domain == "applications" else domain
    meta = availability.get(meta_key, {})
    if not meta.get("available", bool(payload)):
        return unavailable(
            query,
            timestamp,
            meta.get("reason") or f"{domain} data is not available in the latest snapshot.",
            domain=domain,
            operation=operation,
        )
    return None


# ── Project / folder helpers ──────────────────────────────────────────────────

def _largest_project_folder(projects: list[dict[str, Any]]) -> dict[str, Any] | None:
    folders: list[dict[str, Any]] = []
    for project in projects:
        for item in project.get("largestItems", []):
            if item.get("type") != "directory":
                continue
            folders.append({
                "projectPath": project["path"],
                "path": item["path"],
                "name": item["name"],
                "sizeBytes": item["sizeBytes"],
            })
    if not folders:
        return None
    folders.sort(key=lambda item: (-item["sizeBytes"], item["path"]))
    return folders[0]


def _project_contributors(projects: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    contributors: list[dict[str, Any]] = []
    for project in projects:
        for item in project.get("largestItems", []):
            contributors.append({
                "projectPath": project["path"],
                "path": item["path"],
                "name": item["name"],
                "type": item["type"],
                "sizeBytes": item["sizeBytes"],
            })
    contributors.sort(key=lambda item: (-item["sizeBytes"], item["path"]))
    return contributors[:limit]


def _find_folder_record(snapshot: dict[str, Any], folder_name: str) -> dict[str, Any] | None:
    target = folder_name.strip().lower()

    for project in snapshot.get("projects", []):
        project_path = project.get("path", "")
        if target == project_path.lower().rstrip("/").split("/")[-1]:
            return {
                "scope": "project",
                "projectPath": project_path,
                "path": project_path,
                "name": Path(project_path).name or project_path,
                "sizeBytes": project.get("sizeBytes"),
            }
        for item in project.get("largestItems", []):
            if item.get("type") != "directory":
                continue
            if str(item.get("name", "")).lower() == target:
                return {
                    "scope": "project-breakdown",
                    "projectPath": project_path,
                    "path": item.get("path"),
                    "name": item.get("name"),
                    "sizeBytes": item.get("sizeBytes"),
                }

    inventory = snapshot.get("system", {}).get("inventory", {})
    for item in inventory.get("indexedDirectories", []):
        if str(item.get("name", "")).lower() == target:
            return {
                "scope": "system-index",
                "projectPath": None,
                "path": item.get("path"),
                "name": item.get("name"),
                "sizeBytes": item.get("sizeBytes"),
                "depth": item.get("depth"),
                "incomplete": item.get("incomplete"),
            }

    for item in inventory.get("topLevelItems", []):
        if item.get("type") != "directory":
            continue
        if str(item.get("name", "")).lower() == target:
            return {
                "scope": "system-inventory",
                "projectPath": None,
                "path": item.get("path"),
                "name": item.get("name"),
                "sizeBytes": item.get("sizeBytes"),
            }

    return None


# ── Semantic handlers ─────────────────────────────────────────────────────────

def answer_semantic_capability(
    query: str,
    snapshot: dict[str, Any],
    timestamp: str,
) -> dict[str, Any]:
    import re
    from ..semantic.capabilities import can_install, system_capability_summary

    size_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:gb|gigabyte)", query.lower())
    required_bytes = int(float(size_match.group(1)) * GB) if size_match else 0

    app_match = re.search(r"\binstall\s+([a-z0-9 ]+?)(?:\s*\?|$)", query.lower())
    app_name = app_match.group(1).strip() if app_match else None

    if required_bytes > 0 or app_name:
        result = can_install(snapshot, required_bytes, app_name)
        return ok(query, timestamp, "semantic", "capability", result, {"snapshot": "latest"})

    result = system_capability_summary(snapshot)
    return ok(query, timestamp, "semantic", "capability_summary", result, {"snapshot": "latest"})


def answer_semantic_health(
    query: str,
    snapshot: dict[str, Any],
    timestamp: str,
    recent_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    from ..semantic.pressure import build_semantic_pressure_report
    from ..semantic.capabilities import system_capability_summary
    from ..pressure import compute_live_pressure

    live = compute_live_pressure(recent_snapshots)
    pressure = build_semantic_pressure_report(live)
    caps = system_capability_summary(snapshot, live)

    return ok(
        query, timestamp, "semantic", "health",
        {
            "overallPressure": pressure["overall"],
            "capabilities": caps["capabilities"],
            "recommendations": caps["recommendations"],
        },
        {"pressure": pressure, "capabilities": caps},
    )


def answer_semantic_storage(
    query: str,
    snapshot: dict[str, Any],
    timestamp: str,
) -> dict[str, Any]:
    from ..semantic.storage import build_storage_semantic_summary
    result = build_storage_semantic_summary(snapshot)
    return ok(query, timestamp, "semantic", "storage_breakdown", result, {"snapshot": "latest"})


# ── Domain handlers ───────────────────────────────────────────────────────────

def answer_applications(
    query: str,
    timestamp: str,
    snapshot: dict[str, Any],
    availability: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    applications = derived.top_n_applications(snapshot, limit=max(1, extract_top_n(query, default=10)))
    guard = check_domain_availability(availability, "applications", applications, query, timestamp, operation)
    if guard is not None:
        return guard

    if operation == "top_n":
        top_n = extract_top_n(query, default=10)
        result = applications[:top_n]
        return ok(query, timestamp, "applications", "top_n", result, {
            "count": top_n,
            "sortBy": "totalMemoryBytes_desc",
            "records": result,
        })

    top_application = derived.max_memory_application(snapshot)
    if top_application is None:
        return unavailable(query, timestamp, "No application records are available in the latest snapshot.", "applications", operation)

    return ok(query, timestamp, "applications", "max", top_application, {
        "sortBy": "totalMemoryBytes_desc",
        "recordsConsidered": len(snapshot.get("derived", {}).get("applications", [])),
        "topRecord": top_application,
    })


def answer_processes(
    query: str,
    timestamp: str,
    processes: list[dict[str, Any]],
    availability: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    guard = check_domain_availability(availability, "processes", processes, query, timestamp, operation)
    if guard is not None:
        return guard

    ranked = sorted(processes, key=lambda item: (-item["rssBytes"], item["pid"]))

    if operation == "top_n":
        top_n = extract_top_n(query, default=10)
        result = ranked[:top_n]
        return ok(query, timestamp, "processes", "top_n", result, {
            "count": top_n,
            "sortBy": "rssBytes_desc",
            "records": result,
        })

    top_process = ranked[0] if ranked else None
    if top_process is None:
        return unavailable(query, timestamp, "No process records are available in the latest snapshot.", "processes", operation)

    return ok(query, timestamp, "processes", "max", top_process, {
        "sortBy": "rssBytes_desc",
        "recordsConsidered": len(ranked),
        "topRecord": top_process,
    })


def answer_disk(
    query: str,
    timestamp: str,
    disk: dict[str, Any],
    availability: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    guard = check_domain_availability(availability, "disk", disk, query, timestamp, operation)
    if guard is not None:
        return guard

    total_bytes = disk.get("totalBytes")
    used_bytes = disk.get("usedBytes")
    free_bytes = disk.get("freeBytes")

    if operation in {"remaining", "free_space"}:
        computed_free = free_bytes
        if computed_free is None and total_bytes is not None and used_bytes is not None:
            computed_free = total_bytes - used_bytes
        if computed_free is None:
            return unavailable(query, timestamp, "Disk free space cannot be computed from the latest snapshot.", "disk", operation)
        return ok(query, timestamp, "disk", operation,
            {"freeBytes": computed_free, "path": disk.get("path")},
            {"formula": "freeBytes or totalBytes - usedBytes", "disk": disk})

    if operation == "percent_used":
        if total_bytes in {None, 0} or used_bytes is None:
            return unavailable(query, timestamp, "Disk percent used cannot be computed from the latest snapshot.", "disk", operation)
        percent_used = round((used_bytes / total_bytes) * 100, 2)
        return ok(query, timestamp, "disk", "percent_used",
            {"percentUsed": percent_used, "path": disk.get("path")},
            {"formula": "usedBytes / totalBytes * 100", "disk": disk})

    return unavailable(query, timestamp, "Disk operation is not supported.", "disk", operation)


def answer_projects(
    query: str,
    timestamp: str,
    snapshot: dict[str, Any],
    projects: list[dict[str, Any]],
    operation: str,
) -> dict[str, Any]:
    if not projects:
        inventory = snapshot.get("system", {}).get("inventory", {})
        has_inventory = bool(inventory.get("topLevelItems") or inventory.get("indexedDirectories"))
        if not has_inventory or operation != "folder_size":
            return unavailable(query, timestamp, "Project data is not available in the latest snapshot.", "projects", operation)

    if operation == "folder_size":
        folder_name = extract_named_folder(query)
        if not folder_name:
            return unavailable(query, timestamp, "Could not determine which folder you are asking about.", "projects", operation)
        folder_record = _find_folder_record(snapshot, folder_name)
        if folder_record is None:
            return unavailable(
                query, timestamp,
                f"Folder '{folder_name}' is not present in the stored project breakdown or system inventory for the latest snapshot.",
                "projects", operation,
            )
        return ok(query, timestamp, "projects", "folder_size", folder_record, {
            "matchedFolder": folder_name,
            "record": folder_record,
        })

    if operation == "largest_folder":
        largest_folder = _largest_project_folder(projects)
        if largest_folder is None:
            return unavailable(query, timestamp, "No folder records are available in project breakdown data.", "projects", operation)
        return ok(query, timestamp, "projects", "largest_folder", largest_folder, {
            "sortBy": "sizeBytes_desc",
            "records": _project_contributors(projects, limit=10),
        })

    if operation == "top_n":
        top_n = extract_top_n(query, default=10)
        contributors = _project_contributors(projects, limit=top_n)
        return ok(query, timestamp, "projects", "top_n", contributors, {
            "count": top_n,
            "sortBy": "sizeBytes_desc",
            "records": contributors,
        })

    return unavailable(query, timestamp, "Project operation is not supported.", "projects", operation)


def answer_ram(
    query: str,
    timestamp: str,
    snapshot: dict[str, Any],
    ram: dict[str, Any],
    availability: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    guard = check_domain_availability(availability, "ram", ram, query, timestamp, operation)
    if guard is not None:
        return guard

    if operation == "available":
        available_bytes = ram.get("availableBytes")
        if available_bytes is None:
            return unavailable(query, timestamp, "RAM available bytes are missing from the latest snapshot.", "ram", operation)
        return ok(query, timestamp, "ram", "available", {"availableBytes": available_bytes}, {"ram": ram})

    if operation == "used":
        used_bytes = ram.get("usedBytes")
        if used_bytes is None:
            return unavailable(query, timestamp, "RAM used bytes are missing from the latest snapshot.", "ram", operation)
        return ok(query, timestamp, "ram", "used", {"usedBytes": used_bytes}, {"ram": ram})

    if operation == "pressure":
        pressure_score = snapshot.get("derived", {}).get("metrics", {}).get("memoryPressureScore")
        if pressure_score is None:
            return unavailable(query, timestamp, "Memory pressure cannot be computed from the latest snapshot.", "ram", operation)
        return ok(query, timestamp, "ram", "pressure",
            {"memoryPressureScore": pressure_score, "underPressure": pressure_score >= RAM_PRESSURE_HIGH},
            {"formula": "usedBytes / totalBytes", "ram": ram})

    return unavailable(query, timestamp, "RAM operation is not supported.", "ram", operation)


def answer_system(
    query: str,
    timestamp: str,
    snapshot: dict[str, Any],
    recent_snapshots: list[dict[str, Any]],
    operation: str,
) -> dict[str, Any]:
    metrics = snapshot.get("derived", {}).get("metrics", {})
    memory_pressure = metrics.get("memoryPressureScore")
    disk_pressure = metrics.get("diskPressureScore")

    if operation == "memory_pressure":
        if memory_pressure is None:
            return unavailable(query, timestamp, "Memory pressure cannot be computed from the latest snapshot.", "system", operation)
        return ok(query, timestamp, "system", "memory_pressure",
            {"memoryPressureScore": memory_pressure, "underPressure": memory_pressure >= RAM_PRESSURE_HIGH},
            {"metrics": metrics})

    if operation == "disk_pressure":
        if disk_pressure is None:
            return unavailable(query, timestamp, "Disk pressure cannot be computed from the latest snapshot.", "system", operation)
        return ok(query, timestamp, "system", "disk_pressure",
            {"diskPressureScore": disk_pressure, "underPressure": disk_pressure >= DISK_PRESSURE_CRITICAL},
            {"metrics": metrics})

    if operation == "system_pressure":
        return ok(query, timestamp, "system", "system_pressure",
            {
                "memoryPressureScore": memory_pressure,
                "diskPressureScore": disk_pressure,
                "systemLoadScore": metrics.get("systemLoadScore"),
            },
            {"metrics": metrics})

    if operation == "slowdown_summary":
        explanation = causal.explain_system_slowdown(snapshot, recent_snapshots)
        rendered = explain.render_because("System slowdown likely caused by:", explanation.get("causes", []))
        return ok(query, timestamp, "system", "slowdown_summary",
            {"summary": rendered["summary"], "reasons": rendered["reasons"]},
            {"metrics": metrics, "causes": explanation.get("causes", [])})

    if operation == "ram_cause":
        explanation = causal.explain_high_ram(snapshot, recent_snapshots)
        rendered = explain.render_because("High RAM usage is likely caused by:", explanation.get("causes", []))
        return ok(query, timestamp, "system", "ram_cause", rendered,
            {"metrics": metrics, "causes": explanation.get("causes", [])})

    if operation == "disk_cause":
        explanation = causal.explain_disk_growth(snapshot, recent_snapshots)
        rendered = explain.render_because("Disk pressure is likely caused by:", explanation.get("causes", []))
        return ok(query, timestamp, "system", "disk_cause", rendered,
            {"metrics": metrics, "causes": explanation.get("causes", [])})

    return unavailable(query, timestamp, "System operation is not supported.", "system", operation)


def answer_history(
    query: str,
    timestamp: str,
    snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
    recent_snapshots: list[dict[str, Any]],
    operation: str,
) -> dict[str, Any]:
    if operation == "ram_trend":
        trend = timeline.ram_usage_trend(recent_snapshots)
        if not trend.get("available"):
            return unavailable(query, timestamp, trend.get("reason", "RAM trend is not available."), "history", operation)
        return ok(query, timestamp, "history", "ram_trend", trend, {"points": trend.get("points", [])})

    if operation == "disk_trend":
        trend = timeline.disk_usage_trend(recent_snapshots)
        if not trend.get("available"):
            return unavailable(query, timestamp, trend.get("reason", "Disk trend is not available."), "history", operation)
        return ok(query, timestamp, "history", "disk_trend", trend, {"points": trend.get("points", [])})

    if operation == "application_trend":
        application_name = extract_named_application(query)
        if not application_name:
            return unavailable(query, timestamp, "Could not determine which application you are asking about.", "history", operation)
        trend = timeline.application_memory_trend(recent_snapshots, application_name)
        if not trend.get("available"):
            return unavailable(query, timestamp, trend.get("reason", "Application trend is not available."), "history", operation)
        return ok(query, timestamp, "history", "application_trend", trend, {
            "application": application_name,
            "points": trend.get("points", []),
        })

    if operation == "folder_trend":
        folder_name = extract_named_folder(query)
        if not folder_name:
            return unavailable(query, timestamp, "Could not determine which folder you are asking about.", "history", operation)
        trend = timeline.folder_size_trend(recent_snapshots, folder_name)
        if not trend.get("available"):
            return unavailable(query, timestamp, trend.get("reason", "Folder trend is not available."), "history", operation)
        return ok(query, timestamp, "history", "folder_trend", trend, {
            "folder": folder_name,
            "points": trend.get("points", []),
        })

    snapshot_diff = diff.compare_snapshots(snapshot, previous_snapshot)
    if not snapshot_diff.get("available"):
        return unavailable(query, timestamp, snapshot_diff.get("reason", "Snapshot diff is not available."), "history", operation)

    if operation == "growing_folders":
        growing_folders = timeline.growing_folders(recent_snapshots, limit=max(1, extract_top_n(query, default=10)))
        return ok(query, timestamp, "history", "growing_folders", growing_folders, {
            "currentTimestamp": snapshot_diff.get("currentTimestamp"),
            "previousTimestamp": snapshot_diff.get("previousTimestamp"),
            "records": growing_folders,
        })

    if operation == "snapshot_diff":
        app_changes = snapshot_diff.get("applications", [])
        folder_changes = snapshot_diff.get("folders", [])
        top_app_change = app_changes[0] if app_changes else None
        top_folder_change = folder_changes[0] if folder_changes else None

        summary_parts: list[str] = []
        disk_used_delta = int(snapshot_diff.get("disk", {}).get("usedBytesDelta", 0) or 0)
        if disk_used_delta != 0:
            summary_parts.append(f"Disk used bytes changed by {disk_used_delta}")
        ram_used_delta = int(snapshot_diff.get("ram", {}).get("usedBytesDelta", 0) or 0)
        if ram_used_delta != 0:
            summary_parts.append(f"RAM used bytes changed by {ram_used_delta}")
        if top_app_change is not None and int(top_app_change.get("memoryBytesDelta", 0) or 0) != 0:
            summary_parts.append(
                f"{top_app_change['application']} memory changed by {top_app_change['memoryBytesDelta']} bytes"
            )
        if top_folder_change is not None:
            summary_parts.append(
                f"{top_folder_change['name']} changed by {top_folder_change['sizeBytesDelta']} bytes"
            )

        return ok(query, timestamp, "history", "snapshot_diff",
            {"summary": summary_parts, "diff": snapshot_diff},
            {
                "currentTimestamp": snapshot_diff.get("currentTimestamp"),
                "previousTimestamp": snapshot_diff.get("previousTimestamp"),
                "diff": snapshot_diff,
            })

    return unavailable(query, timestamp, "History operation is not supported.", "history", operation)


def answer_forecast(
    query: str,
    timestamp: str,
    recent_snapshots: list[dict[str, Any]],
    operation: str,
) -> dict[str, Any]:
    if operation == "disk_pressure":
        prediction = forecast.forecast_disk_pressure(recent_snapshots)
        if not prediction.get("available"):
            return unavailable(query, timestamp, prediction.get("reason", "Disk forecast is not available."), "forecast", operation)
        return ok(query, timestamp, "forecast", "disk_pressure", prediction, {"summary": prediction.get("summary")})

    if operation == "folder_growth":
        folder_name = extract_named_folder(query)
        if not folder_name:
            return unavailable(query, timestamp, "Could not determine which folder you are asking about.", "forecast", operation)
        prediction = forecast.forecast_folder_growth(recent_snapshots, folder_name)
        if not prediction.get("available"):
            return unavailable(query, timestamp, prediction.get("reason", "Folder forecast is not available."), "forecast", operation)
        return ok(query, timestamp, "forecast", "folder_growth", prediction, {
            "folder": folder_name,
            "summary": prediction.get("summary"),
        })

    return unavailable(query, timestamp, "Forecast operation is not supported.", "forecast", operation)


def answer_relations(
    query: str,
    timestamp: str,
    snapshot: dict[str, Any],
    recent_snapshots: list[dict[str, Any]],
    operation: str,
) -> dict[str, Any]:
    if operation == "apps_vs_ram_spikes":
        correlations = timeline.correlate_applications_with_memory_spikes(
            recent_snapshots, limit=max(1, extract_top_n(query, default=5))
        )
        return ok(query, timestamp, "relations", "apps_vs_ram_spikes", correlations, {
            "records": correlations,
            "relationshipCounts": snapshot.get("relations", {}).get("counts", {}),
        })

    if operation == "folders_growth":
        growing = timeline.growing_folders(recent_snapshots, limit=max(1, extract_top_n(query, default=10)))
        return ok(query, timestamp, "relations", "folders_growth", growing, {
            "records": growing,
            "relationshipCounts": snapshot.get("relations", {}).get("counts", {}),
        })

    return unavailable(query, timestamp, "Relations operation is not supported.", "relations", operation)
