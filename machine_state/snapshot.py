"""Snapshot builder."""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import derived, entities, relations, tools

logger = logging.getLogger(__name__)


def _collect_section(name: str, collector: Any, fallback: Any) -> dict[str, Any]:
    """Run a collection function and return a tagged result.

    On success: {"available": True, "reason": None, "data": <result>}
    On failure: {"available": False, "reason": <message>, "data": fallback}

    All exceptions are logged at ERROR level with full traceback so failures
    are never invisible. The snapshot is still built with fallback data so
    the scheduler loop continues, but the availability block records the failure.
    """
    try:
        return {
            "available": True,
            "reason": None,
            "data": collector(),
        }
    except Exception as exc:
        logger.error(
            "Collection failed for domain '%s': %s\n%s",
            name,
            exc,
            traceback.format_exc(),
        )
        return {
            "available": False,
            "reason": str(exc),
            "data": fallback,
        }


def build_snapshot(
    project_paths: list[str] | None = None,
    process_limit: int = 10,
    item_limit: int = 10,
    full_system: bool = False,
    system_item_limit: int = 15,
    system_max_depth: int = 4,
) -> dict[str, Any]:
    normalized_projects: list[dict[str, Any]] = []
    for raw_path in project_paths or []:
        project = tools.analyze_project_folder(raw_path, limit=item_limit)
        normalized_projects.append(
            {
                "path": project["path"],
                "sizeBytes": project["sizeBytes"],
                "largestItems": project["breakdown"],
            }
        )

    root_disk_path = str(Path("/").resolve())
    ram_section = _collect_section("ram", tools.get_ram_usage, {})
    disk_section = _collect_section("disk", lambda: tools.get_disk_usage(root_disk_path), {})
    process_section = _collect_section(
        "processes",
        lambda: tools.get_top_processes_by_memory(limit=process_limit),
        [],
    )
    inventory_section = _collect_section(
        "inventory",
        lambda: tools.get_system_inventory(
            root_disk_path,
            limit=system_item_limit,
            max_depth=system_max_depth,
        ),
        {},
    ) if full_system else {
        "available": False,
        "reason": "System inventory collection was not requested.",
        "data": {},
    }

    collection_errors = [
        f"{domain}: {section['reason']}"
        for domain, section in [
            ("ram", ram_section),
            ("disk", disk_section),
            ("processes", process_section),
            ("inventory", inventory_section),
        ]
        if not section["available"] and section["reason"] != "System inventory collection was not requested."
    ]

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {
            "ram": ram_section["data"],
            "disk": disk_section["data"],
            "processes": process_section["data"],
            "inventory": inventory_section["data"],
        },
        "availability": {
            "collectionErrors": collection_errors,
            "isComplete": len(collection_errors) == 0,
            "system": {
                "ram": {
                    "available": ram_section["available"],
                    "reason": ram_section["reason"],
                },
                "disk": {
                    "available": disk_section["available"],
                    "reason": disk_section["reason"],
                },
                "processes": {
                    "available": process_section["available"],
                    "reason": process_section["reason"],
                },
                "inventory": {
                    "available": inventory_section["available"],
                    "reason": inventory_section["reason"],
                },
            },
        },
        "projects": normalized_projects,
    }

    if collection_errors:
        logger.warning(
            "Snapshot at %s is incomplete. Failed domains: %s",
            snapshot["timestamp"],
            ", ".join(collection_errors),
        )

    snapshot["derived"] = derived.build_derived_state(snapshot)
    snapshot["entities"] = entities.build_entities(snapshot)
    snapshot["relations"] = relations.build_relationships(snapshot, snapshot["entities"])
    return snapshot
