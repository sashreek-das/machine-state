"""Deterministic snapshot-to-snapshot comparison utilities."""

from __future__ import annotations

from typing import Any


def _index_by_path(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        item["path"]: item
        for item in items
        if isinstance(item.get("path"), str)
    }


def _index_by_application(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        item["application"]: item
        for item in items
        if isinstance(item.get("application"), str)
    }


def _project_directory_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
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
                    "sizeBytes": int(item.get("sizeBytes", 0) or 0),
                }
            )
    return directories


def compare_snapshots(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if previous is None:
        return {
            "available": False,
            "reason": "A previous snapshot is not available for comparison.",
            "currentTimestamp": current.get("timestamp"),
            "previousTimestamp": None,
        }

    current_disk = current.get("system", {}).get("disk", {})
    previous_disk = previous.get("system", {}).get("disk", {})
    disk_change = {
        "freeBytesDelta": int(current_disk.get("freeBytes", 0) or 0) - int(previous_disk.get("freeBytes", 0) or 0),
        "usedBytesDelta": int(current_disk.get("usedBytes", 0) or 0) - int(previous_disk.get("usedBytes", 0) or 0),
    }

    current_ram = current.get("system", {}).get("ram", {})
    previous_ram = previous.get("system", {}).get("ram", {})
    ram_change = {
        "usedBytesDelta": int(current_ram.get("usedBytes", 0) or 0) - int(previous_ram.get("usedBytes", 0) or 0),
        "availableBytesDelta": int(current_ram.get("availableBytes", 0) or 0) - int(previous_ram.get("availableBytes", 0) or 0),
    }

    current_apps = _index_by_application(current.get("derived", {}).get("applications", []))
    previous_apps = _index_by_application(previous.get("derived", {}).get("applications", []))

    app_changes: list[dict[str, Any]] = []
    for application_name in sorted(set(current_apps) | set(previous_apps)):
        current_app = current_apps.get(application_name)
        previous_app = previous_apps.get(application_name)
        current_memory = int((current_app or {}).get("totalMemoryBytes", 0) or 0)
        previous_memory = int((previous_app or {}).get("totalMemoryBytes", 0) or 0)
        delta = current_memory - previous_memory
        status = "unchanged"
        if current_app is None:
            status = "terminated"
        elif previous_app is None:
            status = "new"
        elif delta > 0:
            status = "increased"
        elif delta < 0:
            status = "decreased"

        app_changes.append(
            {
                "application": application_name,
                "status": status,
                "memoryBytesDelta": delta,
                "currentMemoryBytes": current_memory,
                "previousMemoryBytes": previous_memory,
            }
        )

    app_changes.sort(key=lambda item: (-abs(item["memoryBytesDelta"]), item["application"]))

    current_directories = _index_by_path(_project_directory_records(current))
    previous_directories = _index_by_path(_project_directory_records(previous))
    folder_changes: list[dict[str, Any]] = []
    for path in sorted(set(current_directories) | set(previous_directories)):
        current_item = current_directories.get(path)
        previous_item = previous_directories.get(path)
        current_size = int((current_item or {}).get("sizeBytes", 0) or 0)
        previous_size = int((previous_item or {}).get("sizeBytes", 0) or 0)
        delta = current_size - previous_size
        if delta == 0:
            continue
        reference = current_item or previous_item or {}
        folder_changes.append(
            {
                "projectPath": reference.get("projectPath"),
                "path": path,
                "name": reference.get("name"),
                "sizeBytesDelta": delta,
                "currentSizeBytes": current_size,
                "previousSizeBytes": previous_size,
            }
        )

    folder_changes.sort(key=lambda item: (-abs(item["sizeBytesDelta"]), item["path"]))

    return {
        "available": True,
        "reason": None,
        "currentTimestamp": current.get("timestamp"),
        "previousTimestamp": previous.get("timestamp"),
        "disk": disk_change,
        "ram": ram_change,
        "applications": app_changes,
        "folders": folder_changes,
    }
