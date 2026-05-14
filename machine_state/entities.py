"""Stable entity builders for deterministic machine understanding."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _application_id(name: str) -> str:
    return f"application:{name.strip().lower()}"


def _project_id(path: str) -> str:
    return f"project:{path}"


def _folder_id(path: str) -> str:
    return f"folder:{path}"


def _process_id(process: dict[str, Any]) -> str:
    pid = process.get("pid")
    command = process.get("command", "")
    return f"process:{pid}:{command}"


def build_entities(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    process_entities: list[dict[str, Any]] = []
    for process in snapshot.get("system", {}).get("processes", []):
        process_entities.append(
            {
                "entityId": _process_id(process),
                "entityType": "ProcessEntity",
                "pid": process.get("pid"),
                "ppid": process.get("ppid"),
                "command": process.get("command"),
                "rssBytes": int(process.get("rssBytes", 0) or 0),
                "memoryPercent": process.get("memoryPercent"),
            }
        )

    application_entities: list[dict[str, Any]] = []
    for application in snapshot.get("derived", {}).get("applications", []):
        application_entities.append(
            {
                "entityId": _application_id(application.get("application", "unknown")),
                "entityType": "ApplicationEntity",
                "name": application.get("application"),
                "totalMemoryBytes": int(application.get("totalMemoryBytes", 0) or 0),
                "processCount": int(application.get("processCount", 0) or 0),
                "processEntityIds": [_process_id(process) for process in application.get("processes", [])],
            }
        )

    project_entities: list[dict[str, Any]] = []
    folder_entities: list[dict[str, Any]] = []

    for project in snapshot.get("projects", []):
        project_path = str(project.get("path", ""))
        project_entity_id = _project_id(project_path)
        folder_ids: list[str] = []
        for item in project.get("largestItems", []):
            if item.get("type") != "directory":
                continue
            folder_path = str(item.get("path", ""))
            folder_entity_id = _folder_id(folder_path)
            folder_ids.append(folder_entity_id)
            folder_entities.append(
                {
                    "entityId": folder_entity_id,
                    "entityType": "FolderEntity",
                    "name": item.get("name"),
                    "path": folder_path,
                    "scope": "project-breakdown",
                    "sizeBytes": int(item.get("sizeBytes", 0) or 0),
                    "projectEntityId": project_entity_id,
                }
            )

        project_entities.append(
            {
                "entityId": project_entity_id,
                "entityType": "ProjectEntity",
                "name": Path(project_path).name or project_path,
                "path": project_path,
                "sizeBytes": int(project.get("sizeBytes", 0) or 0),
                "folderEntityIds": folder_ids,
            }
        )

    inventory = snapshot.get("system", {}).get("inventory", {})
    for item in inventory.get("indexedDirectories", []):
        folder_path = str(item.get("path", ""))
        folder_entities.append(
            {
                "entityId": _folder_id(folder_path),
                "entityType": "FolderEntity",
                "name": item.get("name"),
                "path": folder_path,
                "scope": "system-index",
                "sizeBytes": int(item.get("sizeBytes", 0) or 0),
                "depth": item.get("depth"),
                "incomplete": bool(item.get("incomplete", False)),
            }
        )

    unique_folders: dict[str, dict[str, Any]] = {}
    for folder in folder_entities:
        unique_folders.setdefault(folder["entityId"], folder)

    return {
        "applications": application_entities,
        "projects": project_entities,
        "folders": list(unique_folders.values()),
        "processes": process_entities,
    }
