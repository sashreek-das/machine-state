"""Low-level system inspection tools.

These functions only inspect system state and return JSON-serializable data.
They do not contain formatting or query logic.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_SYSTEM_SCAN_EXCLUDES = [
    "/dev",
    "/proc",
    "/sys",
    "/tmp",
    "/private/tmp",
    "/private/var/tmp",
    "/private/var/vm",
]

FORBIDDEN_COMMAND_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("rm", "-rf", "/"), "Refuses to delete the entire filesystem."),
    (("rm", "-rf", "*"), "Refuses to delete all files in the current directory."),
    (("rm", "-rf", "."), "Refuses to delete the current directory tree."),
    (("mv", "/folder", "/dev/null"), "Refuses to discard files by moving them into /dev/null."),
    (("dd", "if=/dev/zero", "of=/dev/sda"), "Refuses to overwrite a physical drive."),
    (("mkfs.ext4", "/dev/sda1"), "Refuses to format a drive partition."),
    (("kill", "-9", "-1"), "Refuses to kill all system processes."),
    (("chmod", "-R", "777", "/"), "Refuses to make the whole filesystem world-writable."),
    (("chown", "-R", "root:root", "/"), "Refuses to rewrite ownership for the whole filesystem."),
]

FORBIDDEN_TOKEN_SETS: list[tuple[set[str], str]] = [
    ({"wget", "-O-", "sh"}, "Refuses to download and execute untrusted remote shell code."),
    ({"curl", "bash"}, "Refuses to pipe remote content into bash."),
]

FORBIDDEN_EXACT_COMMANDS: list[tuple[str, str]] = [
    (":(){ :|:& };:", "Refuses to execute a fork bomb."),
]
FORBIDDEN_SUBSTRINGS: list[tuple[str, str]] = [
    ("> /etc/passwd", "Refuses to overwrite critical system account files."),
    ("> /dev/sda", "Refuses to write directly to a physical drive."),
]


def _ensure_command_is_safe(args: list[str]) -> None:
    normalized = tuple(str(arg).strip() for arg in args)
    joined = " ".join(normalized)

    for exact_command, reason in FORBIDDEN_EXACT_COMMANDS:
        if joined == exact_command:
            raise RuntimeError(f"Blocked unsafe command: {joined}. {reason}")

    for prefix, reason in FORBIDDEN_COMMAND_PATTERNS:
        if normalized[: len(prefix)] == prefix:
            raise RuntimeError(f"Blocked unsafe command: {joined}. {reason}")

    token_set = set(normalized)
    for required_tokens, reason in FORBIDDEN_TOKEN_SETS:
        if required_tokens.issubset(token_set):
            raise RuntimeError(f"Blocked unsafe command: {joined}. {reason}")

    for snippet, reason in FORBIDDEN_SUBSTRINGS:
        if snippet in joined:
            raise RuntimeError(f"Blocked unsafe command: {joined}. {reason}")


def _run_command(args: list[str]) -> str:
    _ensure_command_is_safe(args)
    result = subprocess.run(args, capture_output=True, text=True, check=True, shell=False)
    return result.stdout.strip()


def _safe_name(path: Path) -> str:
    return path.name or str(path)


def _directory_size_bytes(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path, onerror=lambda _: None, followlinks=False):
        for directory in dirs:
            dir_path = Path(root, directory)
            try:
                mode = dir_path.lstat().st_mode
            except OSError:
                continue
            if stat.S_ISLNK(mode):
                continue

        for filename in files:
            file_path = Path(root, filename)
            try:
                file_stat = file_path.lstat()
            except OSError:
                continue
            if stat.S_ISLNK(file_stat.st_mode):
                continue
            total += file_stat.st_size
    return total


def _normalize_exclude_paths(paths: list[str] | None) -> set[str]:
    normalized: set[str] = set()
    for raw_path in paths or []:
        try:
            normalized.add(str(Path(raw_path).expanduser().resolve()))
        except OSError:
            continue
    return normalized


def _is_excluded(path: Path, excluded_paths: set[str]) -> bool:
    try:
        resolved = str(path.resolve())
    except OSError:
        return True
    return resolved in excluded_paths


def _scan_directory_index(
    path: Path,
    excluded_paths: set[str],
    max_depth: int,
    current_depth: int = 0,
) -> tuple[int, list[dict[str, Any]], bool]:
    if _is_excluded(path, excluded_paths):
        return 0, [], False

    total_size = 0
    records: list[dict[str, Any]] = []
    had_errors = False

    try:
        entries = sorted(path.iterdir(), key=lambda item: item.name)
    except OSError:
        return 0, [], True

    for child in entries:
        try:
            if child.is_symlink():
                continue
            if child.is_file():
                total_size += child.stat().st_size
                continue
            if not child.is_dir():
                continue
        except OSError:
            had_errors = True
            continue

        if _is_excluded(child, excluded_paths):
            continue

        child_size, child_records, child_had_errors = _scan_directory_index(
            child,
            excluded_paths,
            max_depth=max_depth,
            current_depth=current_depth + 1,
        )
        total_size += child_size
        had_errors = had_errors or child_had_errors
        records.extend(child_records)

    if current_depth <= max_depth:
        records.append(
            {
                "path": str(path),
                "name": _safe_name(path),
                "type": "directory",
                "sizeBytes": total_size,
                "depth": current_depth,
                "incomplete": had_errors,
            }
        )

    return total_size, records, had_errors


def get_ram_usage() -> dict[str, Any]:
    system = platform.system()

    if system == "Darwin":
        total_bytes = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        vm_stat_output = _run_command(["vm_stat"])
        page_size = 4096
        pages: dict[str, int] = {}

        for line in vm_stat_output.splitlines():
            if "page size of" in line:
                match = re.search(r"page size of (\d+) bytes", line)
                if match:
                    page_size = int(match.group(1))
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            numeric_value = value.strip().replace(".", "")
            if not numeric_value.isdigit():
                continue
            pages[key.strip()] = int(numeric_value)

        free_pages = pages.get("Pages free", 0) + pages.get("Pages speculative", 0)
        active_pages = pages.get("Pages active", 0)
        inactive_pages = pages.get("Pages inactive", 0)
        wired_pages = pages.get("Pages wired down", 0) + pages.get("Pages occupied by compressor", 0)

        available_bytes = free_pages * page_size
        used_bytes = (active_pages + inactive_pages + wired_pages) * page_size

        return {
            "totalBytes": total_bytes,
            "usedBytes": min(used_bytes, total_bytes),
            "availableBytes": max(0, min(available_bytes, total_bytes)),
            "source": "sysconf+vm_stat",
        }

    if system == "Linux":
        meminfo: dict[str, int] = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, raw_value = line.split(":", 1)
                parts = raw_value.strip().split()
                if parts:
                    meminfo[key] = int(parts[0]) * 1024

        total_bytes = meminfo["MemTotal"]
        available_bytes = meminfo.get("MemAvailable", 0)
        used_bytes = total_bytes - available_bytes

        return {
            "totalBytes": total_bytes,
            "usedBytes": max(0, used_bytes),
            "availableBytes": max(0, available_bytes),
            "source": "/proc/meminfo",
        }

    raise RuntimeError(f"Unsupported operating system for RAM inspection: {system}")


def get_disk_usage(path: str = "/") -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {
        "path": str(Path(path).resolve()),
        "totalBytes": usage.total,
        "usedBytes": usage.used,
        "freeBytes": usage.free,
        "source": "shutil.disk_usage",
    }


def get_top_processes_by_memory(limit: int = 10) -> list[dict[str, Any]]:
    system = platform.system()

    if system in {"Darwin", "Linux"}:
        output = _run_command(["ps", "-axo", "pid=,ppid=,%mem=,rss=,comm="])
        processes: list[dict[str, Any]] = []

        for line in output.splitlines():
            parts = line.strip().split(None, 4)
            if len(parts) != 5:
                continue
            pid, ppid, percent_mem, rss_kb, command = parts
            processes.append(
                {
                    "pid": int(pid),
                    "ppid": int(ppid),
                    "memoryPercent": float(percent_mem),
                    "rssBytes": int(rss_kb) * 1024,
                    "command": command,
                }
            )

        processes.sort(key=lambda item: (-item["rssBytes"], item["pid"]))
        return processes[:limit]

    raise RuntimeError(f"Unsupported operating system for process inspection: {system}")


def get_largest_items(path: str, limit: int = 10) -> dict[str, Any]:
    directory = Path(path).expanduser().resolve()
    if not directory.exists():
        raise FileNotFoundError(f"Path does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")

    items: list[dict[str, Any]] = []
    for child in sorted(directory.iterdir(), key=lambda item: item.name):
        try:
            if child.is_symlink():
                continue
            if child.is_file():
                size_bytes = child.stat().st_size
                item_type = "file"
            elif child.is_dir():
                size_bytes = _directory_size_bytes(child)
                item_type = "directory"
            else:
                continue
        except OSError:
            continue

        items.append(
            {
                "path": str(child),
                "name": _safe_name(child),
                "type": item_type,
                "sizeBytes": size_bytes,
            }
        )

    items.sort(key=lambda item: (-item["sizeBytes"], item["path"]))
    return {
        "path": str(directory),
        "items": items[:limit],
    }


def analyze_project_folder(path: str, limit: int = 10) -> dict[str, Any]:
    directory = Path(path).expanduser().resolve()
    if not directory.exists():
        raise FileNotFoundError(f"Path does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")

    total_size_bytes = _directory_size_bytes(directory)
    largest = get_largest_items(str(directory), limit=limit)

    return {
        "path": str(directory),
        "sizeBytes": total_size_bytes,
        "breakdown": largest["items"],
    }


def get_system_inventory(
    root_path: str = "/",
    limit: int = 15,
    exclude_paths: list[str] | None = None,
    max_depth: int = 4,
) -> dict[str, Any]:
    root = Path(root_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")

    excluded = _normalize_exclude_paths(DEFAULT_SYSTEM_SCAN_EXCLUDES + (exclude_paths or []))
    indexed_directories: list[dict[str, Any]] = []
    top_level_items: list[dict[str, Any]] = []
    excluded_items: list[dict[str, Any]] = []

    for child in sorted(root.iterdir(), key=lambda item: item.name):
        try:
            if child.is_symlink():
                continue
        except OSError:
            continue

        if _is_excluded(child, excluded):
            excluded_items.append(
                {
                    "path": str(child),
                    "name": _safe_name(child),
                    "type": "excluded",
                    "sizeBytes": None,
                    "excluded": True,
                }
            )
            continue

        try:
            if child.is_file():
                top_level_items.append(
                    {
                        "path": str(child),
                        "name": _safe_name(child),
                        "type": "file",
                        "sizeBytes": child.stat().st_size,
                        "excluded": False,
                        "depth": 1,
                        "incomplete": False,
                    }
                )
                continue
            if not child.is_dir():
                continue
        except OSError:
            continue

        child_size, child_records, child_had_errors = _scan_directory_index(
            child,
            excluded,
            max_depth=max_depth,
            current_depth=1,
        )
        top_level_items.append(
            {
                "path": str(child),
                "name": _safe_name(child),
                "type": "directory",
                "sizeBytes": child_size,
                "excluded": False,
                "depth": 1,
                "incomplete": child_had_errors,
            }
        )
        indexed_directories.extend(child_records)

    top_level_items.sort(key=lambda item: (-int(item["sizeBytes"] or 0), item["path"]))
    indexed_directories.sort(key=lambda item: (-int(item["sizeBytes"] or 0), item["path"]))

    return {
        "path": str(root),
        "excludedPaths": sorted(excluded),
        "maxDepth": max_depth,
        "topLevelItems": top_level_items[:limit],
        "indexedDirectories": indexed_directories,
        "excludedTopLevelItems": excluded_items,
    }


def tool_output_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)
