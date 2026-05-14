"""Persistent system memory.

Builds structured long-term behavioral memory from accumulated snapshots.
Memory is deterministic, queryable, inspectable, and explainable.

This is NOT vector memory. This is NOT semantic memory.
This is structured historical machine memory.

Examples of what is remembered:
- Recurring RAM spikes
- Historically heavy applications
- Folders that grow continuously
- Recurring cleanup candidates
- Common slowdown periods
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import store
from .constants import (
    RAM_PRESSURE_HIGH,
    HEAVY_APP_MIN_BYTES,
    GROWING_FOLDER_MIN_DELTA_BYTES,
    CLEANUP_CANDIDATE_MIN_BYTES,
    RAM_SPIKE_PATTERN_RATIO,
    RAM_SPIKE_RECENT_LIMIT,
    CLEANUP_CANDIDATES_MAX,
)


# ── Keys used in system_memory table ──────────────────────────────────────────
_KEY_HEAVY_APPLICATIONS = "heavy_applications"
_KEY_GROWING_FOLDERS = "growing_folders"
_KEY_RAM_SPIKE_PATTERN = "ram_spike_pattern"
_KEY_CLEANUP_CANDIDATES = "cleanup_candidates"
_KEY_SLOWDOWN_PERIODS = "slowdown_periods"
_KEY_SUMMARY = "memory_summary"


def _ordered(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(snapshots, key=lambda s: s.get("timestamp", ""))


def _parse_hour(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.hour
    except ValueError:
        return None


# ── Builders ──────────────────────────────────────────────────────────────────

def _build_heavy_applications(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identify applications that are historically heavy RAM consumers."""
    app_data: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        for app in snapshot.get("derived", {}).get("applications", []):
            name = str(app.get("application", ""))
            mem = int(app.get("totalMemoryBytes") or 0)
            record = app_data.setdefault(
                name,
                {
                    "application": name,
                    "totalObservations": 0,
                    "totalMemoryBytes": 0,
                    "peakMemoryBytes": 0,
                },
            )
            record["totalObservations"] += 1
            record["totalMemoryBytes"] += mem
            record["peakMemoryBytes"] = max(record["peakMemoryBytes"], mem)

    results: list[dict[str, Any]] = []
    for name, record in app_data.items():
        count = record["totalObservations"]
        avg = int(record["totalMemoryBytes"] / count) if count > 0 else 0
        if avg >= HEAVY_APP_MIN_BYTES:
            results.append(
                {
                    "application": name,
                    "averageMemoryBytes": avg,
                    "peakMemoryBytes": record["peakMemoryBytes"],
                    "observationCount": count,
                    "totalSnapshotsAnalyzed": len(snapshots),
                    "presenceRatio": round(count / len(snapshots), 4) if snapshots else 0.0,
                }
            )

    results.sort(key=lambda r: (-r["averageMemoryBytes"], r["application"]))
    return results


def _build_growing_folders(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identify folders with sustained growth across snapshots."""
    ordered = _ordered(snapshots)
    by_path: dict[str, list[dict[str, Any]]] = {}

    for snapshot in ordered:
        inventory = snapshot.get("system", {}).get("inventory", {})
        ts = snapshot.get("timestamp", "")
        for item in inventory.get("indexedDirectories", []):
            path = str(item.get("path", ""))
            if not path:
                continue
            by_path.setdefault(path, []).append(
                {
                    "timestamp": ts,
                    "sizeBytes": int(item.get("sizeBytes") or 0),
                    "name": item.get("name", ""),
                }
            )
        for project in snapshot.get("projects", []):
            path = str(project.get("path", ""))
            if not path:
                continue
            by_path.setdefault(path, []).append(
                {
                    "timestamp": ts,
                    "sizeBytes": int(project.get("sizeBytes") or 0),
                    "name": path.split("/")[-1],
                }
            )

    results: list[dict[str, Any]] = []
    for path, points in by_path.items():
        if len(points) < 2:
            continue
        first_size = points[0]["sizeBytes"]
        last_size = points[-1]["sizeBytes"]
        delta = last_size - first_size
        if delta < GROWING_FOLDER_MIN_DELTA_BYTES:
            continue
        results.append(
            {
                "path": path,
                "name": points[-1]["name"],
                "deltaBytes": delta,
                "firstSizeBytes": first_size,
                "latestSizeBytes": last_size,
                "firstSeenTimestamp": points[0]["timestamp"],
                "lastSeenTimestamp": points[-1]["timestamp"],
                "observationCount": len(points),
            }
        )

    results.sort(key=lambda r: (-r["deltaBytes"], r["path"]))
    return results


def _build_ram_spike_pattern(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Identify RAM spike patterns: frequency, typical hour, typical trigger."""
    ordered = _ordered(snapshots)
    spike_count = 0
    hour_buckets: dict[int, int] = {}
    spike_timestamps: list[str] = []

    for index in range(1, len(ordered)):
        prev = ordered[index - 1]
        curr = ordered[index]
        prev_used = int(prev.get("system", {}).get("ram", {}).get("usedBytes") or 0)
        curr_used = int(curr.get("system", {}).get("ram", {}).get("usedBytes") or 0)
        if prev_used <= 0 or curr_used <= prev_used:
            continue
        growth_ratio = (curr_used - prev_used) / prev_used
        if growth_ratio >= RAM_SPIKE_PATTERN_RATIO:
            spike_count += 1
            ts = curr.get("timestamp", "")
            spike_timestamps.append(ts)
            hour = _parse_hour(ts)
            if hour is not None:
                hour_buckets[hour] = hour_buckets.get(hour, 0) + 1

    most_common_hour: int | None = None
    if hour_buckets:
        most_common_hour = max(hour_buckets, key=lambda h: hour_buckets[h])

    return {
        "totalSpikeCount": spike_count,
        "spikeRate": round(spike_count / max(len(ordered) - 1, 1), 4),
        "mostCommonHour": most_common_hour,
        "hourDistribution": hour_buckets,
        "recentSpikes": spike_timestamps[-RAM_SPIKE_RECENT_LIMIT:],
        "snapshotsAnalyzed": len(ordered),
    }


def _build_cleanup_candidates(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identify large, stable or growing folders as cleanup candidates."""
    if not snapshots:
        return []
    latest = _ordered(snapshots)[-1]

    candidates: list[dict[str, Any]] = []

    # Large project folders
    for project in latest.get("projects", []):
        size = int(project.get("sizeBytes") or 0)
        if size >= CLEANUP_CANDIDATE_MIN_BYTES:
            candidates.append(
                {
                    "type": "project",
                    "path": project.get("path"),
                    "name": str(project.get("path", "")).split("/")[-1],
                    "sizeBytes": size,
                    "reason": "Large project folder.",
                }
            )
        # Large sub-directories within projects
        for item in project.get("largestItems", []):
            if item.get("type") != "directory":
                continue
            item_size = int(item.get("sizeBytes") or 0)
            if item_size >= CLEANUP_CANDIDATE_MIN_BYTES:
                candidates.append(
                    {
                        "type": "folder",
                        "path": item.get("path"),
                        "name": item.get("name"),
                        "sizeBytes": item_size,
                        "reason": "Large directory within project.",
                    }
                )

    # Large system directories
    for item in latest.get("system", {}).get("inventory", {}).get("indexedDirectories", []):
        size = int(item.get("sizeBytes") or 0)
        if size >= CLEANUP_CANDIDATE_MIN_BYTES:
            candidates.append(
                {
                    "type": "system_folder",
                    "path": item.get("path"),
                    "name": item.get("name"),
                    "sizeBytes": size,
                    "reason": "Large system-level directory.",
                }
            )

    candidates.sort(key=lambda c: (-c["sizeBytes"], c.get("path", "")))
    # Deduplicate by path
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in candidates:
        p = str(c.get("path", ""))
        if p not in seen:
            seen.add(p)
            unique.append(c)
    return unique[:CLEANUP_CANDIDATES_MAX]


def _build_slowdown_periods(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Identify hours of day where system pressure is consistently elevated."""
    hour_pressure: dict[int, list[float]] = {}
    for snapshot in snapshots:
        ts = snapshot.get("timestamp", "")
        hour = _parse_hour(ts)
        if hour is None:
            continue
        metrics = snapshot.get("derived", {}).get("metrics", {})
        pressure = metrics.get("systemLoadScore")
        if pressure is not None:
            hour_pressure.setdefault(hour, []).append(float(pressure))

    hourly_averages: list[dict[str, Any]] = []
    for hour, scores in sorted(hour_pressure.items()):
        avg = sum(scores) / len(scores)
        hourly_averages.append(
            {
                "hour": hour,
                "averageLoadScore": round(avg, 4),
                "sampleCount": len(scores),
            }
        )

    high_pressure_hours = [
        h for h in hourly_averages if h["averageLoadScore"] >= RAM_PRESSURE_HIGH
    ]
    high_pressure_hours.sort(key=lambda h: -h["averageLoadScore"])

    return {
        "hourlyAverages": hourly_averages,
        "highPressureHours": high_pressure_hours,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def rebuild_system_memory(
    snapshots: list[dict[str, Any]],
    db_path: str | None = None,
) -> dict[str, Any]:
    """Recompute all system memory records from the full snapshot history.

    This is an idempotent operation — calling it again with more snapshots
    will update the memory with newer data.

    Returns a summary of what was stored.
    """
    now = datetime.now(timezone.utc).isoformat()

    heavy_apps = _build_heavy_applications(snapshots)
    growing_folders = _build_growing_folders(snapshots)
    ram_spikes = _build_ram_spike_pattern(snapshots)
    cleanup = _build_cleanup_candidates(snapshots)
    slowdowns = _build_slowdown_periods(snapshots)

    store.save_system_memory(_KEY_HEAVY_APPLICATIONS, heavy_apps, now, db_path)
    store.save_system_memory(_KEY_GROWING_FOLDERS, growing_folders, now, db_path)
    store.save_system_memory(_KEY_RAM_SPIKE_PATTERN, ram_spikes, now, db_path)
    store.save_system_memory(_KEY_CLEANUP_CANDIDATES, cleanup, now, db_path)
    store.save_system_memory(_KEY_SLOWDOWN_PERIODS, slowdowns, now, db_path)

    summary = {
        "heavyApplicationsCount": len(heavy_apps),
        "growingFoldersCount": len(growing_folders),
        "totalRamSpikeCount": ram_spikes.get("totalSpikeCount", 0),
        "cleanupCandidatesCount": len(cleanup),
        "highPressureHoursCount": len(slowdowns.get("highPressureHours", [])),
        "snapshotsAnalyzed": len(snapshots),
        "updatedAt": now,
    }
    store.save_system_memory(_KEY_SUMMARY, summary, now, db_path)
    return summary


def get_system_memory(db_path: str | None = None) -> dict[str, Any]:
    """Retrieve all stored system memory."""
    return store.get_all_system_memory(db_path)


def get_heavy_applications(db_path: str | None = None) -> list[dict[str, Any]]:
    return store.get_system_memory(_KEY_HEAVY_APPLICATIONS, db_path) or []


def get_growing_folders(db_path: str | None = None) -> list[dict[str, Any]]:
    return store.get_system_memory(_KEY_GROWING_FOLDERS, db_path) or []


def get_ram_spike_pattern(db_path: str | None = None) -> dict[str, Any]:
    return store.get_system_memory(_KEY_RAM_SPIKE_PATTERN, db_path) or {}


def get_cleanup_candidates(db_path: str | None = None) -> list[dict[str, Any]]:
    return store.get_system_memory(_KEY_CLEANUP_CANDIDATES, db_path) or []


def get_slowdown_periods(db_path: str | None = None) -> dict[str, Any]:
    return store.get_system_memory(_KEY_SLOWDOWN_PERIODS, db_path) or {}
