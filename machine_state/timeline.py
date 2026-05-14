"""Deterministic time-series utilities over stored snapshots."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _ordered_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        snapshots,
        key=lambda item: _parse_timestamp(item.get("timestamp")) or datetime.min,
    )


def _application_record(snapshot: dict[str, Any], application_name: str) -> dict[str, Any] | None:
    target = application_name.strip().lower()
    for item in snapshot.get("derived", {}).get("applications", []):
        if str(item.get("application", "")).strip().lower() == target:
            return item
    return None


def _folder_record(snapshot: dict[str, Any], folder_name: str) -> dict[str, Any] | None:
    target = folder_name.strip().lower()

    for project in snapshot.get("projects", []):
        project_path = str(project.get("path", ""))
        if target == Path(project_path).name.lower():
            return {
                "path": project_path,
                "name": Path(project_path).name or project_path,
                "sizeBytes": int(project.get("sizeBytes", 0) or 0),
                "scope": "project",
            }
        for item in project.get("largestItems", []):
            if item.get("type") != "directory":
                continue
            if str(item.get("name", "")).lower() == target:
                return {
                    "path": item.get("path"),
                    "name": item.get("name"),
                    "sizeBytes": int(item.get("sizeBytes", 0) or 0),
                    "scope": "project-breakdown",
                }

    inventory = snapshot.get("system", {}).get("inventory", {})
    for item in inventory.get("indexedDirectories", []):
        if str(item.get("name", "")).lower() == target:
            return {
                "path": item.get("path"),
                "name": item.get("name"),
                "sizeBytes": int(item.get("sizeBytes", 0) or 0),
                "scope": "system-index",
            }
    return None


def _series_summary(points: list[dict[str, Any]], value_key: str) -> dict[str, Any]:
    if not points:
        return {
            "available": False,
            "reason": "No matching historical points are available.",
            "points": [],
        }

    first = points[0]
    last = points[-1]
    start_value = int(first.get(value_key, 0) or 0)
    end_value = int(last.get(value_key, 0) or 0)
    delta = end_value - start_value
    direction = "flat"
    if delta > 0:
        direction = "increasing"
    elif delta < 0:
        direction = "decreasing"

    peak = max(points, key=lambda item: int(item.get(value_key, 0) or 0))
    duration_seconds = None
    start_time = _parse_timestamp(first.get("timestamp"))
    end_time = _parse_timestamp(last.get("timestamp"))
    if start_time is not None and end_time is not None:
        duration_seconds = max(0.0, (end_time - start_time).total_seconds())

    rate_per_hour = None
    if duration_seconds and duration_seconds > 0:
        rate_per_hour = round(delta / (duration_seconds / 3600.0), 2)

    return {
        "available": True,
        "points": points,
        "startTimestamp": first.get("timestamp"),
        "endTimestamp": last.get("timestamp"),
        "deltaBytes": delta,
        "direction": direction,
        "peak": peak,
        "rateBytesPerHour": rate_per_hour,
        "durationSeconds": duration_seconds,
    }


def ram_usage_trend(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    points = []
    for snapshot in _ordered_snapshots(snapshots):
        ram = snapshot.get("system", {}).get("ram", {})
        if ram.get("usedBytes") is None:
            continue
        points.append(
            {
                "timestamp": snapshot.get("timestamp"),
                "usedBytes": int(ram.get("usedBytes", 0) or 0),
                "availableBytes": int(ram.get("availableBytes", 0) or 0),
            }
        )
    return _series_summary(points, "usedBytes")


def disk_usage_trend(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    points = []
    for snapshot in _ordered_snapshots(snapshots):
        disk = snapshot.get("system", {}).get("disk", {})
        if disk.get("usedBytes") is None:
            continue
        points.append(
            {
                "timestamp": snapshot.get("timestamp"),
                "usedBytes": int(disk.get("usedBytes", 0) or 0),
                "freeBytes": int(disk.get("freeBytes", 0) or 0),
                "totalBytes": int(disk.get("totalBytes", 0) or 0),
                "path": disk.get("path"),
            }
        )
    return _series_summary(points, "usedBytes")


def application_memory_trend(snapshots: list[dict[str, Any]], application_name: str) -> dict[str, Any]:
    points = []
    for snapshot in _ordered_snapshots(snapshots):
        record = _application_record(snapshot, application_name)
        if record is None:
            continue
        points.append(
            {
                "timestamp": snapshot.get("timestamp"),
                "application": record.get("application"),
                "totalMemoryBytes": int(record.get("totalMemoryBytes", 0) or 0),
                "processCount": int(record.get("processCount", 0) or 0),
            }
        )
    summary = _series_summary(points, "totalMemoryBytes")
    summary["application"] = application_name
    return summary


def folder_size_trend(snapshots: list[dict[str, Any]], folder_name: str) -> dict[str, Any]:
    points = []
    for snapshot in _ordered_snapshots(snapshots):
        record = _folder_record(snapshot, folder_name)
        if record is None:
            continue
        points.append(
            {
                "timestamp": snapshot.get("timestamp"),
                "path": record.get("path"),
                "name": record.get("name"),
                "scope": record.get("scope"),
                "sizeBytes": int(record.get("sizeBytes", 0) or 0),
            }
        )
    summary = _series_summary(points, "sizeBytes")
    summary["folder"] = folder_name
    return summary


def growing_folders(snapshots: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    by_path: dict[str, list[dict[str, Any]]] = {}
    for snapshot in _ordered_snapshots(snapshots):
        inventory = snapshot.get("system", {}).get("inventory", {})
        seen_paths: set[str] = set()
        for item in inventory.get("indexedDirectories", []):
            path = str(item.get("path", ""))
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            by_path.setdefault(path, []).append(
                {
                    "timestamp": snapshot.get("timestamp"),
                    "name": item.get("name"),
                    "path": path,
                    "sizeBytes": int(item.get("sizeBytes", 0) or 0),
                }
            )

    growth_records: list[dict[str, Any]] = []
    for path, points in by_path.items():
        if len(points) < 2:
            continue
        summary = _series_summary(points, "sizeBytes")
        delta = int(summary.get("deltaBytes", 0) or 0)
        if delta <= 0:
            continue
        growth_records.append(
            {
                "path": path,
                "name": points[-1].get("name"),
                "deltaBytes": delta,
                "rateBytesPerHour": summary.get("rateBytesPerHour"),
                "startTimestamp": summary.get("startTimestamp"),
                "endTimestamp": summary.get("endTimestamp"),
            }
        )

    growth_records.sort(key=lambda item: (-int(item.get("deltaBytes", 0) or 0), item.get("path", "")))
    return growth_records[:limit]


def correlate_applications_with_memory_spikes(snapshots: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    ordered = _ordered_snapshots(snapshots)
    if len(ordered) < 2:
        return []

    scores: dict[str, dict[str, Any]] = {}
    for index in range(1, len(ordered)):
        previous = ordered[index - 1]
        current = ordered[index]
        previous_apps = {
            item.get("application"): int(item.get("totalMemoryBytes", 0) or 0)
            for item in previous.get("derived", {}).get("applications", [])
        }
        current_apps = {
            item.get("application"): int(item.get("totalMemoryBytes", 0) or 0)
            for item in current.get("derived", {}).get("applications", [])
        }
        current_ram = int(current.get("system", {}).get("ram", {}).get("usedBytes", 0) or 0)
        previous_ram = int(previous.get("system", {}).get("ram", {}).get("usedBytes", 0) or 0)
        ram_delta = current_ram - previous_ram
        if ram_delta <= 0:
            continue

        for name in sorted(set(previous_apps) | set(current_apps)):
            current_memory = current_apps.get(name, 0)
            previous_memory = previous_apps.get(name, 0)
            delta = current_memory - previous_memory
            if delta <= 0:
                continue
            record = scores.setdefault(
                name,
                {
                    "application": name,
                    "totalApplicationMemoryGrowthBytes": 0,
                    "observedRamGrowthBytes": 0,
                    "spikeCount": 0,
                },
            )
            record["totalApplicationMemoryGrowthBytes"] += delta
            record["observedRamGrowthBytes"] += ram_delta
            record["spikeCount"] += 1

    ranked = list(scores.values())
    for record in ranked:
        observed = int(record.get("observedRamGrowthBytes", 0) or 0)
        growth = int(record.get("totalApplicationMemoryGrowthBytes", 0) or 0)
        record["contributionRatio"] = round(growth / observed, 4) if observed > 0 else 0.0

    ranked.sort(
        key=lambda item: (
            -float(item.get("contributionRatio", 0.0) or 0.0),
            -int(item.get("totalApplicationMemoryGrowthBytes", 0) or 0),
            item.get("application", ""),
        )
    )
    return ranked[:limit]
