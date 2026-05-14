"""Deterministic derived intelligence over stored snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_GENERIC_PROCESS_NAMES = {
    "helper",
    "renderer",
    "gpu",
    "plugin",
    "crashpad_handler",
    "python",
    "python3",
    "node",
    "bash",
    "zsh",
    "sh",
}

_HELPER_SUFFIXES = (
    " Helper",
    " Helper (Renderer)",
    " Helper (GPU)",
    " Helper (Plugin)",
)


def _extract_bundle_name(command: str) -> str | None:
    parts = Path(command).parts
    for index, part in enumerate(parts):
        if part.endswith(".app"):
            return part[:-4] or None
        if part == "Applications" and index + 1 < len(parts) and parts[index + 1].endswith(".app"):
            return parts[index + 1][:-4] or None
    return None


def _normalize_process_name(command: str) -> str:
    bundle_name = _extract_bundle_name(command)
    if bundle_name:
        return bundle_name

    base_name = Path(command).name or command
    for suffix in _HELPER_SUFFIXES:
        if base_name.endswith(suffix):
            return base_name[: -len(suffix)] or base_name
    return base_name


def _should_use_parent_fallback(name: str) -> bool:
    lowered = name.strip().lower()
    return lowered in _GENERIC_PROCESS_NAMES or lowered.endswith(" helper")


def _resolve_application_name(
    process: dict[str, Any],
    process_by_pid: dict[int, dict[str, Any]],
    cache: dict[int, str],
) -> str:
    pid = process.get("pid")
    if isinstance(pid, int) and pid in cache:
        return cache[pid]

    current_name = _normalize_process_name(process.get("command", ""))
    resolved_name = current_name or "Unknown"

    if _should_use_parent_fallback(current_name):
        seen: set[int] = set()
        parent_pid = process.get("ppid")
        while isinstance(parent_pid, int) and parent_pid not in seen:
            seen.add(parent_pid)
            parent = process_by_pid.get(parent_pid)
            if parent is None:
                break
            parent_name = _normalize_process_name(parent.get("command", ""))
            if parent_name and not _should_use_parent_fallback(parent_name):
                resolved_name = parent_name
                break
            parent_pid = parent.get("ppid")

    if isinstance(pid, int):
        cache[pid] = resolved_name
    return resolved_name


def group_processes_by_application(processes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    process_by_pid = {
        process["pid"]: process
        for process in processes
        if isinstance(process.get("pid"), int)
    }
    cache: dict[int, str] = {}
    grouped: dict[str, dict[str, Any]] = {}

    for process in processes:
        application_name = _resolve_application_name(process, process_by_pid, cache)
        bucket = grouped.setdefault(
            application_name,
            {
                "application": application_name,
                "totalMemoryBytes": 0,
                "processCount": 0,
                "processes": [],
            },
        )
        rss_bytes = int(process.get("rssBytes", 0) or 0)
        bucket["totalMemoryBytes"] += rss_bytes
        bucket["processCount"] += 1
        bucket["processes"].append(process)

    groups = list(grouped.values())
    for group in groups:
        group["processes"].sort(key=lambda item: (-int(item.get("rssBytes", 0) or 0), int(item.get("pid", 0) or 0)))

    groups.sort(key=lambda item: (-item["totalMemoryBytes"], item["application"]))
    return groups


def top_n_processes(snapshot: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    processes = list(snapshot.get("system", {}).get("processes", []))
    processes.sort(key=lambda item: (-int(item.get("rssBytes", 0) or 0), int(item.get("pid", 0) or 0)))
    return processes[:limit]


def max_memory_process(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    ranked = top_n_processes(snapshot, limit=1)
    return ranked[0] if ranked else None


def top_n_applications(snapshot: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    applications = list(snapshot.get("derived", {}).get("applications", []))
    applications.sort(key=lambda item: (-int(item.get("totalMemoryBytes", 0) or 0), item.get("application", "")))
    return applications[:limit]


def max_memory_application(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    ranked = top_n_applications(snapshot, limit=1)
    return ranked[0] if ranked else None


def free_space(snapshot: dict[str, Any]) -> int | None:
    disk = snapshot.get("system", {}).get("disk", {})
    free_bytes = disk.get("freeBytes")
    if free_bytes is not None:
        return int(free_bytes)

    total_bytes = disk.get("totalBytes")
    used_bytes = disk.get("usedBytes")
    if total_bytes is None or used_bytes is None:
        return None
    return max(0, int(total_bytes) - int(used_bytes))


def used_percentage(snapshot: dict[str, Any]) -> float | None:
    disk = snapshot.get("system", {}).get("disk", {})
    total_bytes = disk.get("totalBytes")
    used_bytes = disk.get("usedBytes")
    if total_bytes in {None, 0} or used_bytes is None:
        return None
    return round((float(used_bytes) / float(total_bytes)) * 100, 2)


def largest_directories(snapshot: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    directories: list[dict[str, Any]] = []
    for project in snapshot.get("projects", []):
        for item in project.get("largestItems", []):
            if item.get("type") != "directory":
                continue
            directories.append(
                {
                    "projectPath": project.get("path"),
                    "path": item.get("path"),
                    "name": item.get("name"),
                    "sizeBytes": item.get("sizeBytes", 0),
                }
            )

    directories.sort(key=lambda item: (-int(item.get("sizeBytes", 0) or 0), item.get("path", "")))
    return directories[:limit]


def used_memory(snapshot: dict[str, Any]) -> int | None:
    used_bytes = snapshot.get("system", {}).get("ram", {}).get("usedBytes")
    return None if used_bytes is None else int(used_bytes)


def available_memory(snapshot: dict[str, Any]) -> int | None:
    available_bytes = snapshot.get("system", {}).get("ram", {}).get("availableBytes")
    return None if available_bytes is None else int(available_bytes)


def memory_pressure_ratio(snapshot: dict[str, Any]) -> float | None:
    ram = snapshot.get("system", {}).get("ram", {})
    total_bytes = ram.get("totalBytes")
    used_bytes = ram.get("usedBytes")
    if total_bytes in {None, 0} or used_bytes is None:
        return None
    return round(float(used_bytes) / float(total_bytes), 4)


def disk_pressure_score(snapshot: dict[str, Any]) -> float | None:
    disk = snapshot.get("system", {}).get("disk", {})
    total_bytes = disk.get("totalBytes")
    used_bytes = disk.get("usedBytes")
    if total_bytes in {None, 0} or used_bytes is None:
        return None
    return round(float(used_bytes) / float(total_bytes), 4)


def memory_pressure_score(snapshot: dict[str, Any]) -> float | None:
    return memory_pressure_ratio(snapshot)


def system_load_score(snapshot: dict[str, Any]) -> float | None:
    disk_pressure = disk_pressure_score(snapshot)
    memory_pressure = memory_pressure_score(snapshot)
    scores = [score for score in (disk_pressure, memory_pressure) if score is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def build_derived_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    applications = group_processes_by_application(snapshot.get("system", {}).get("processes", []))
    return {
        "applications": applications,
        "metrics": {
            "diskPressureScore": disk_pressure_score(snapshot),
            "memoryPressureScore": memory_pressure_score(snapshot),
            "systemLoadScore": system_load_score(snapshot),
            "diskUsedPercentage": used_percentage(snapshot),
            "availableMemoryBytes": available_memory(snapshot),
            "usedMemoryBytes": used_memory(snapshot),
            "freeDiskBytes": free_space(snapshot),
        },
    }
