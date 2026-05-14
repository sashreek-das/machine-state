"""Deterministic rule-based event detection from snapshot transitions.

Compares consecutive snapshots and emits structured events when meaningful
system changes are detected. All rules are threshold-based and reproducible.
"""

from __future__ import annotations

from typing import Any

from .. import store
from ..constants import (
    RAM_SPIKE_RATIO,
    RAM_PRESSURE_CRITICAL,
    DISK_PRESSURE_CRITICAL,
    FOLDER_GROWTH_EVENT_BYTES,
    CACHE_EXPLOSION_EVENT_BYTES,
    PROCESS_RUNAWAY_RATIO,
    APP_MEMORY_SPIKE_BYTES,
)

# Event type constants
EVENT_TYPES = {
    # RAM events
    "ram_spike": "ram_spike",
    "ram_pressure_critical": "ram_pressure_critical",
    "ram_pressure_sustained": "ram_pressure_sustained",
    # Disk events
    "disk_pressure_critical": "disk_pressure_critical",
    "disk_folder_growth": "disk_folder_growth",
    "disk_cache_explosion": "disk_cache_explosion",
    # Process events
    "process_runaway": "process_runaway",
    "process_memory_growth": "process_memory_growth",
    # Application events
    "application_memory_spike": "application_memory_spike",
}



def _get_ram(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("system", {}).get("ram", {})


def _get_disk(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("system", {}).get("disk", {})


def _get_processes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return snapshot.get("system", {}).get("processes", [])


def _get_applications(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return snapshot.get("derived", {}).get("applications", [])


def _get_inventory_dirs(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return snapshot.get("system", {}).get("inventory", {}).get("indexedDirectories", [])


def _detect_ram_events(
    previous: dict[str, Any],
    current: dict[str, Any],
    timestamp: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    prev_ram = _get_ram(previous)
    curr_ram = _get_ram(current)

    prev_used = int(prev_ram.get("usedBytes") or 0)
    curr_used = int(curr_ram.get("usedBytes") or 0)
    curr_total = int(curr_ram.get("totalBytes") or 0)

    # RAM spike: significant growth between snapshots
    if prev_used > 0 and curr_used > prev_used:
        growth_ratio = (curr_used - prev_used) / prev_used
        if growth_ratio >= RAM_SPIKE_RATIO:
            events.append(
                {
                    "timestamp": timestamp,
                    "event_type": EVENT_TYPES["ram_spike"],
                    "severity": "warning" if growth_ratio < 0.25 else "critical",
                    "domain": "ram",
                    "summary": f"RAM usage spiked by {round(growth_ratio * 100, 1)}% "
                               f"({_fmt_bytes(curr_used - prev_used)} increase).",
                    "evidence": {
                        "previousUsedBytes": prev_used,
                        "currentUsedBytes": curr_used,
                        "growthBytes": curr_used - prev_used,
                        "growthRatio": round(growth_ratio, 4),
                    },
                }
            )

    # Critical RAM pressure threshold crossed
    if curr_total > 0 and curr_used > 0:
        pressure = curr_used / curr_total
        prev_total = int(prev_ram.get("totalBytes") or 0)
        prev_pressure = (prev_used / prev_total) if prev_total > 0 else 0.0
        if pressure >= RAM_PRESSURE_CRITICAL and prev_pressure < RAM_PRESSURE_CRITICAL:
            events.append(
                {
                    "timestamp": timestamp,
                    "event_type": EVENT_TYPES["ram_pressure_critical"],
                    "severity": "critical",
                    "domain": "ram",
                    "summary": f"RAM pressure crossed critical threshold at "
                               f"{round(pressure * 100, 1)}% used.",
                    "evidence": {
                        "pressureScore": round(pressure, 4),
                        "usedBytes": curr_used,
                        "totalBytes": curr_total,
                        "availableBytes": int(curr_ram.get("availableBytes") or 0),
                    },
                }
            )

    return events


def _detect_disk_events(
    previous: dict[str, Any],
    current: dict[str, Any],
    timestamp: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    prev_disk = _get_disk(previous)
    curr_disk = _get_disk(current)

    curr_used = int(curr_disk.get("usedBytes") or 0)
    curr_total = int(curr_disk.get("totalBytes") or 0)
    prev_used = int(prev_disk.get("usedBytes") or 0)
    prev_total = int(prev_disk.get("totalBytes") or 0)

    # Disk pressure threshold crossed
    if curr_total > 0 and curr_used > 0:
        pressure = curr_used / curr_total
        prev_pressure = (prev_used / prev_total) if prev_total > 0 else 0.0
        if pressure >= DISK_PRESSURE_CRITICAL and prev_pressure < DISK_PRESSURE_CRITICAL:
            events.append(
                {
                    "timestamp": timestamp,
                    "event_type": EVENT_TYPES["disk_pressure_critical"],
                    "severity": "critical",
                    "domain": "disk",
                    "summary": f"Disk pressure crossed critical threshold at "
                               f"{round(pressure * 100, 1)}% used.",
                    "evidence": {
                        "pressureScore": round(pressure, 4),
                        "usedBytes": curr_used,
                        "totalBytes": curr_total,
                        "freeBytes": int(curr_disk.get("freeBytes") or 0),
                    },
                }
            )

    # Folder growth events from inventory
    # Only compare when the previous snapshot also had inventory data —
    # otherwise every directory would appear to grow from 0 (first-scan false positive).
    prev_inventory_dirs = _get_inventory_dirs(previous)
    if not prev_inventory_dirs:
        return events

    prev_dirs = {
        str(d.get("path", "")): int(d.get("sizeBytes") or 0)
        for d in prev_inventory_dirs
    }
    for directory in _get_inventory_dirs(current):
        path = str(directory.get("path", ""))
        curr_size = int(directory.get("sizeBytes") or 0)
        prev_size = prev_dirs.get(path, 0)
        growth = curr_size - prev_size
        if growth >= CACHE_EXPLOSION_EVENT_BYTES:
            events.append(
                {
                    "timestamp": timestamp,
                    "event_type": EVENT_TYPES["disk_cache_explosion"],
                    "severity": "critical",
                    "domain": "disk",
                    "summary": f"Cache explosion detected in {directory.get('name', path)}: "
                               f"+{_fmt_bytes(growth)}.",
                    "evidence": {
                        "path": path,
                        "name": directory.get("name"),
                        "previousSizeBytes": prev_size,
                        "currentSizeBytes": curr_size,
                        "growthBytes": growth,
                    },
                }
            )
        elif growth >= FOLDER_GROWTH_EVENT_BYTES:
            events.append(
                {
                    "timestamp": timestamp,
                    "event_type": EVENT_TYPES["disk_folder_growth"],
                    "severity": "warning",
                    "domain": "disk",
                    "summary": f"Significant folder growth in {directory.get('name', path)}: "
                               f"+{_fmt_bytes(growth)}.",
                    "evidence": {
                        "path": path,
                        "name": directory.get("name"),
                        "previousSizeBytes": prev_size,
                        "currentSizeBytes": curr_size,
                        "growthBytes": growth,
                    },
                }
            )

    return events


def _detect_process_events(
    previous: dict[str, Any],
    current: dict[str, Any],
    timestamp: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    curr_ram = _get_ram(current)
    curr_total = int(curr_ram.get("totalBytes") or 0)

    # Runaway process: single process consuming >40% of total RAM
    if curr_total > 0:
        for process in _get_processes(current):
            rss = int(process.get("rssBytes") or 0)
            if rss / curr_total >= PROCESS_RUNAWAY_RATIO:
                events.append(
                    {
                        "timestamp": timestamp,
                        "event_type": EVENT_TYPES["process_runaway"],
                        "severity": "critical",
                        "domain": "processes",
                        "summary": f"Runaway process detected: {process.get('command', 'unknown')} "
                                   f"consuming {_fmt_bytes(rss)} "
                                   f"({round(rss / curr_total * 100, 1)}% of RAM).",
                        "evidence": {
                            "pid": process.get("pid"),
                            "command": process.get("command"),
                            "rssBytes": rss,
                            "ramRatio": round(rss / curr_total, 4),
                            "totalRamBytes": curr_total,
                        },
                    }
                )

    # Application memory spike: app grew significantly between snapshots
    prev_apps = {
        str(a.get("application", "")): int(a.get("totalMemoryBytes") or 0)
        for a in _get_applications(previous)
    }
    for app in _get_applications(current):
        name = str(app.get("application", ""))
        curr_mem = int(app.get("totalMemoryBytes") or 0)
        prev_mem = prev_apps.get(name, 0)
        growth = curr_mem - prev_mem
        if growth >= APP_MEMORY_SPIKE_BYTES:
            events.append(
                {
                    "timestamp": timestamp,
                    "event_type": EVENT_TYPES["application_memory_spike"],
                    "severity": "warning",
                    "domain": "processes",
                    "summary": f"{name} memory grew by {_fmt_bytes(growth)} "
                               f"(now using {_fmt_bytes(curr_mem)}).",
                    "evidence": {
                        "application": name,
                        "previousMemoryBytes": prev_mem,
                        "currentMemoryBytes": curr_mem,
                        "growthBytes": growth,
                        "processCount": app.get("processCount"),
                    },
                }
            )

    return events


def detect_events(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    """Detect meaningful events by comparing two consecutive snapshots.

    Returns a list of event dicts. Each event has:
      timestamp, event_type, severity, domain, summary, evidence.
    """
    timestamp = current.get("timestamp", "")
    events: list[dict[str, Any]] = []
    events.extend(_detect_ram_events(previous, current, timestamp))
    events.extend(_detect_disk_events(previous, current, timestamp))
    events.extend(_detect_process_events(previous, current, timestamp))
    return events


def detect_and_store_events(
    previous: dict[str, Any],
    current: dict[str, Any],
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Detect events and persist them to the database.

    Returns the list of newly detected events.
    """
    events = detect_events(previous, current)
    for event in events:
        store.save_event(event, db_path)
    return events


def _fmt_bytes(n: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n = int(n / 1024)
    return f"{n:.1f} PB"
