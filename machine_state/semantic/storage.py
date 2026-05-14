"""Semantic storage classification.

Classifies raw directory data from snapshots into meaningful storage categories:
Downloads, Caches, Trash, Backups, Media, Application Data, Developer, System.

Provides:
- per-category size breakdown
- cleanup potential (which categories are safe to clear)
- human-readable storage status
"""

from __future__ import annotations

from typing import Any

from ..constants import GB, LARGE_INSTALL_THRESHOLD_BYTES

# ── Category definitions ──────────────────────────────────────────────────────

# Each category maps to a list of path fragment patterns (case-insensitive substring match)
STORAGE_CATEGORIES: dict[str, dict[str, Any]] = {
    "downloads": {
        "patterns": ["/downloads"],
        "label": "Downloads",
        "cleanupSafe": True,
        "description": "Files downloaded from the internet.",
    },
    "caches": {
        "patterns": ["/library/caches", "/caches", "/.cache", "/cache"],
        "label": "Caches",
        "cleanupSafe": True,
        "description": "Temporary application cache files.",
    },
    "trash": {
        "patterns": ["/.trash", "/.trashes"],
        "label": "Trash",
        "cleanupSafe": True,
        "description": "Files pending deletion.",
    },
    "backups": {
        "patterns": ["/backups", "/backup", "/time machine", "mobilebackups", "/icloud drive"],
        "label": "Backups",
        "cleanupSafe": False,
        "description": "System and application backups.",
    },
    "media": {
        "patterns": ["/movies", "/music", "/pictures", "/photos", "/videos", "/media"],
        "label": "Media",
        "cleanupSafe": False,
        "description": "Photos, videos, and music files.",
    },
    "app_data": {
        "patterns": ["/library/application support", "/library/containers", "/library/group containers"],
        "label": "Application Data",
        "cleanupSafe": False,
        "description": "Application settings and data.",
    },
    "developer": {
        "patterns": [
            "/developer", "/xcode", "/.gradle", "/.m2", "/node_modules",
            "/.npm", "/.yarn", "/.cargo", "/.rustup", "/.pyenv",
            "/.nvm", "/.rbenv", "/derived data", "/deriveddata",
            "/.android", "/android", "/.gradle",
            "/library/developer",
        ],
        "label": "Developer Tools & Build Artifacts",
        "cleanupSafe": True,
        "description": "Developer tools, build caches, and project artifacts.",
    },
    "docker": {
        "patterns": ["/docker", "com.docker", "/.docker"],
        "label": "Docker",
        "cleanupSafe": True,
        "description": "Docker images, containers, and volumes.",
    },
    "system": {
        "patterns": ["/system", "/usr", "/private", "/opt", "/bin", "/sbin", "/library/apple"],
        "label": "System",
        "cleanupSafe": False,
        "description": "macOS system files.",
    },
    "user_library": {
        "patterns": ["/library/logs", "/library/preferences", "/library/saved application state"],
        "label": "User Library",
        "cleanupSafe": True,
        "description": "User library files (logs, preferences).",
    },
    "desktop": {
        "patterns": ["/desktop"],
        "label": "Desktop",
        "cleanupSafe": False,
        "description": "Files on the Desktop.",
    },
    "documents": {
        "patterns": ["/documents"],
        "label": "Documents",
        "cleanupSafe": False,
        "description": "User documents.",
    },
}

_DEFAULT_CATEGORY = "other"


def classify_path(path: str) -> str:
    """Return the semantic storage category for a given path."""
    lowered = path.lower()
    for category, meta in STORAGE_CATEGORIES.items():
        for pattern in meta["patterns"]:
            if pattern in lowered:
                return category
    return _DEFAULT_CATEGORY


def _fmt_gb(b: int) -> float:
    return round(b / GB, 2)


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n = int(n / 1024)
    return f"{n:.1f} PB"


def _collect_directories(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Gather all directory records from inventory + projects."""
    dirs: list[dict[str, Any]] = []
    inventory = snapshot.get("system", {}).get("inventory", {})
    for item in inventory.get("indexedDirectories", []):
        dirs.append(
            {
                "path": str(item.get("path", "")),
                "name": str(item.get("name", "")),
                "sizeBytes": int(item.get("sizeBytes") or 0),
                "depth": item.get("depth", 0),
                "source": "inventory",
            }
        )
    for project in snapshot.get("projects", []):
        dirs.append(
            {
                "path": str(project.get("path", "")),
                "name": str(project.get("path", "")).split("/")[-1],
                "sizeBytes": int(project.get("sizeBytes") or 0),
                "depth": 1,
                "source": "project",
            }
        )
        for item in project.get("largestItems", []):
            if item.get("type") == "directory":
                dirs.append(
                    {
                        "path": str(item.get("path", "")),
                        "name": str(item.get("name", "")),
                        "sizeBytes": int(item.get("sizeBytes") or 0),
                        "depth": 2,
                        "source": "project-breakdown",
                    }
                )
    return dirs


def build_storage_breakdown(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Classify all known directories into semantic storage categories.

    Returns per-category size totals, cleanup potential, and a ranked breakdown.
    """
    dirs = _collect_directories(snapshot)
    if not dirs:
        return {
            "available": False,
            "reason": "No directory data in snapshot. Run with --full-system for storage breakdown.",
        }

    # Deduplicate: keep only the shallowest (most representative) path per category
    # to avoid double-counting nested directories
    by_category: dict[str, list[dict[str, Any]]] = {}
    seen_paths: set[str] = set()
    for d in sorted(dirs, key=lambda x: (classify_path(x["path"]), x["depth"], x["path"])):
        path = d["path"]
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        cat = classify_path(path)
        by_category.setdefault(cat, []).append(d)

    # Build per-category summary — use the largest single entry per category
    # to give a meaningful top-level estimate
    categories: list[dict[str, Any]] = []
    total_classified = 0

    all_known = list(STORAGE_CATEGORIES.keys()) + [_DEFAULT_CATEGORY]
    for cat in all_known:
        items = by_category.get(cat, [])
        if not items:
            continue
        # Use the largest item as the representative size for this category
        # (avoids double-counting parent+child dirs)
        largest = max(items, key=lambda x: x["sizeBytes"])
        size = largest["sizeBytes"]
        total_classified += size

        meta = STORAGE_CATEGORIES.get(cat, {})
        categories.append(
            {
                "category": cat,
                "label": meta.get("label", cat.replace("_", " ").title()),
                "sizeBytes": size,
                "sizeGB": _fmt_gb(size),
                "sizeHuman": _fmt_bytes(size),
                "cleanupSafe": meta.get("cleanupSafe", False),
                "description": meta.get("description", ""),
                "topDirectory": largest["path"],
                "directoryCount": len(items),
            }
        )

    categories.sort(key=lambda c: -c["sizeBytes"])

    cleanup_candidates = [c for c in categories if c["cleanupSafe"] and c["sizeBytes"] > 0]
    cleanup_potential = sum(c["sizeBytes"] for c in cleanup_candidates)

    return {
        "available": True,
        "categories": categories,
        "totalClassifiedGB": _fmt_gb(total_classified),
        "cleanupPotentialGB": _fmt_gb(cleanup_potential),
        "cleanupCandidates": [c["label"] for c in cleanup_candidates],
        "directoriesAnalyzed": len(seen_paths),
    }


def get_storage_status(free_bytes: int, total_bytes: int) -> str:
    """Return a semantic label for storage status."""
    if total_bytes <= 0:
        return "unknown"
    ratio = free_bytes / total_bytes
    if ratio >= 0.30:
        return "healthy"
    if ratio >= 0.15:
        return "low"
    if ratio >= 0.05:
        return "critical"
    return "full"


def build_storage_semantic_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a complete semantic storage summary from a snapshot."""
    disk = snapshot.get("system", {}).get("disk", {})
    free_bytes = int(disk.get("freeBytes") or 0)
    total_bytes = int(disk.get("totalBytes") or 0)
    used_bytes = int(disk.get("usedBytes") or 0)

    status = get_storage_status(free_bytes, total_bytes)
    safe_for_large_install = free_bytes >= (LARGE_INSTALL_THRESHOLD_BYTES)  # 10 GB free

    breakdown = build_storage_breakdown(snapshot)

    return {
        "freeGB": _fmt_gb(free_bytes),
        "usedGB": _fmt_gb(used_bytes),
        "totalGB": _fmt_gb(total_bytes),
        "status": status,
        "safeForLargeInstall": safe_for_large_install,
        "percentUsed": round(used_bytes / total_bytes * 100, 1) if total_bytes > 0 else None,
        "breakdown": breakdown,
    }
