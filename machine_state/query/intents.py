"""Intent detection and parameter extraction for the query layer.

All functions here are pure: given a query string, return a classification
or extracted value. No snapshot access, no side effects.
"""

from __future__ import annotations

import re


def extract_top_n(query: str, default: int = 10) -> int:
    match = re.search(r"\btop\s+(\d+)\b", query.lower())
    if match:
        return max(1, int(match.group(1)))
    return default


def extract_named_folder(query: str) -> str | None:
    match = re.search(
        r"\b(?:taken|used|using|occupied)\s+by\s+['\"]?([^'\"?]+?)['\"]?(?:\?|$)",
        query,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().rstrip(".")

    match = re.search(
        r"\bdoes\s+['\"]?([^'\"]+?)['\"]?\s+(?:use|take|occupy|consume)",
        query,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().rstrip(".")

    match = re.search(r"\b(['\"]?[^'\"]+?['\"]?)\s+(?:is\s+)?taking\s+up", query, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip(".")

    match = re.search(
        r"\bfolder\s+['\"]?([^'\"]+?)['\"]?(?:\s+(?:growth|size|trend|over|forecast)|\?|$)",
        query,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().rstrip(".")

    match = re.search(
        r"\bdirectory\s+['\"]?([^'\"]+?)['\"]?(?:\s+(?:growth|size|trend|over|forecast)|\?|$)",
        query,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().rstrip(".")

    return None


def extract_named_application(query: str) -> str | None:
    match = re.search(r"\b(?:app|application)\s+['\"]?([^'\"]+?)['\"]?(?:\?|$)", query, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip(".")

    match = re.search(r"\bfor\s+['\"]?([^'\"]+?)['\"]?(?:\?|$)", query, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip(".")

    return None


def detect_semantic_query(lowered: str) -> str | None:
    """Return a semantic query type if the query matches a Phase 5 semantic pattern."""
    if re.search(r"\bcan\s+i\s+install\b", lowered):
        return "semantic_capability"
    if re.search(r"\bwill\s+this\s+fit\b", lowered):
        return "semantic_capability"
    if re.search(r"\bhow\s+much\s+(?:space\s+)?(?:will\s+)?remain\b", lowered):
        return "semantic_capability"
    if re.search(r"\b(?:is\s+my\s+)?system\s+healthy\b", lowered):
        return "semantic_health"
    if re.search(r"\bhow\s+is\s+my\s+(?:machine|system|mac)\b", lowered):
        return "semantic_health"
    if re.search(r"\bwhat\s+(?:category|categories|type)\s+(?:of\s+)?storage\b", lowered):
        return "semantic_storage"
    if re.search(r"\bstorage\s+breakdown\b", lowered):
        return "semantic_storage"
    if re.search(r"\bclean\s?(?:up)?\b.*\b(?:storage|disk|space|cache|downloads)\b", lowered):
        return "semantic_storage"
    if re.search(r"\b(?:storage|disk|space|cache)\b.*\bclean\s?(?:up)?\b", lowered):
        return "semantic_storage"
    if re.search(r"\bfree\s+(?:up\s+)?(?:storage|disk|space)\b", lowered):
        return "semantic_storage"
    if re.search(r"\bsystem\s+(?:state|status|summary)\b", lowered):
        return "semantic_health"
    return None


def detect_domain(lowered: str) -> str | None:
    if "forecast" in lowered or "projected" in lowered or "when will" in lowered:
        return "forecast"
    if "correlate" in lowered or "correlation" in lowered or "grow together" in lowered:
        return "relations"
    if "changed" in lowered or "since my last snapshot" in lowered or "growing over time" in lowered:
        return "history"
    if "trend" in lowered or "over time" in lowered:
        return "history"
    if "why" in lowered and (
        "ram" in lowered or "memory" in lowered or "disk" in lowered
        or "storage" in lowered or "slow" in lowered
    ):
        return "system"
    if "slow" in lowered or "pressure" in lowered:
        return "system"
    if "app" in lowered or "application" in lowered:
        return "applications"
    if "process" in lowered:
        return "processes"
    if re.search(r"\b(?:taken|used|using|occupied)\s+by\b", lowered) or re.search(
        r"\bdoes\s+\S+.*\s+(?:use|take|occupy|consume)", lowered
    ):
        return "projects"
    if (
        "project" in lowered or "folder" in lowered
        or "directory" in lowered or "file" in lowered or "contributor" in lowered
    ):
        return "projects"
    if "disk" in lowered or "space" in lowered or "storage" in lowered:
        return "disk"
    if "ram" in lowered or "memory" in lowered:
        return "ram"
    return None


def detect_operation(lowered: str, domain: str | None) -> str | None:
    if domain == "forecast":
        if "disk" in lowered or "storage" in lowered or "full" in lowered:
            return "disk_pressure"
        if "folder" in lowered or "directory" in lowered or "project" in lowered:
            return "folder_growth"

    if domain == "relations":
        if "application" in lowered and "ram" in lowered:
            return "apps_vs_ram_spikes"
        if "grow together" in lowered or ("folder" in lowered and "correlate" in lowered):
            return "folders_growth"

    if domain == "history":
        if ("folders" in lowered or "directories" in lowered) and ("grow" in lowered or "growing" in lowered):
            return "growing_folders"
        if ("ram" in lowered or "memory" in lowered) and ("trend" in lowered or "over time" in lowered):
            return "ram_trend"
        if ("disk" in lowered or "storage" in lowered) and ("trend" in lowered or "over time" in lowered):
            return "disk_trend"
        if ("app" in lowered or "application" in lowered) and ("trend" in lowered or "over time" in lowered):
            return "application_trend"
        if ("folder" in lowered or "directory" in lowered or "project" in lowered) and (
            "trend" in lowered or "over time" in lowered
        ):
            return "folder_trend"
        if "folder" in lowered and ("grow" in lowered or "growing" in lowered):
            return "growing_folders"
        if "changed" in lowered or "since my last snapshot" in lowered:
            return "snapshot_diff"

    if domain == "system":
        if "why" in lowered and "ram" in lowered:
            return "ram_cause"
        if "why" in lowered and ("disk" in lowered or "storage" in lowered):
            return "disk_cause"
        if "why" in lowered and "slow" in lowered:
            return "slowdown_summary"
        if "memory pressure" in lowered:
            return "memory_pressure"
        if "disk pressure" in lowered or "storage pressure" in lowered:
            return "disk_pressure"
        if "pressure" in lowered:
            return "system_pressure"

    if domain == "applications":
        if "top " in lowered:
            return "top_n"
        if "most" in lowered or "highest" in lowered or "max" in lowered:
            return "max"
        if "memory" in lowered:
            return "max"

    if domain == "processes":
        if "top " in lowered:
            return "top_n"
        if "most" in lowered or "highest" in lowered or "max" in lowered:
            return "max"
        if "memory" in lowered:
            return "max"

    if domain == "disk":
        if "full" in lowered or "pressure" in lowered:
            return "percent_used"
        if "percent" in lowered or "%" in lowered:
            return "percent_used"
        if "remaining" in lowered or "left" in lowered:
            return "remaining"
        if "free" in lowered:
            return "free_space"
        if "how much" in lowered or "used" in lowered or "space" in lowered:
            return "free_space"

    if domain == "projects":
        if (
            "how much" in lowered or "space" in lowered or "size" in lowered
            or "taken" in lowered or "used" in lowered or "using" in lowered
        ):
            return "folder_size"
        if "top " in lowered and (
            "contributor" in lowered or "largest" in lowered
            or "file" in lowered or "folder" in lowered
        ):
            return "top_n"
        if "largest" in lowered or "biggest" in lowered or "most" in lowered:
            return "largest_folder"
        if "contributor" in lowered:
            return "top_n"

    if domain == "ram":
        if "pressure" in lowered:
            return "pressure"
        if "remaining" in lowered or "available" in lowered or "free" in lowered:
            return "available"
        if "how much" in lowered or "used" in lowered or "memory" in lowered:
            return "used"

    return None
