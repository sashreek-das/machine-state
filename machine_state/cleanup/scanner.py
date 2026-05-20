"""Filesystem scanner for cleanable disk space (Phase 9).

All discovery is read-only (os.stat / os.walk).
No subprocess calls, no writes.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

_HOME = Path.home()
_30_DAYS = 30 * 86400
_7_DAYS  = 7  * 86400

# (category, path_fn, risk, action, stale_seconds)
_CATALOGUE: list[tuple[str, Path, str, str, int | None]] = [
    ("Xcode Derived Data",     _HOME / "Library/Developer/Xcode/DerivedData",  "safe",   "rm -rf",    None),
    ("Xcode Device Support",   _HOME / "Library/Developer/Xcode/iOS DeviceSupport", "safe", "rm -rf", None),
    ("npm cache",              _HOME / ".npm/_cacache",                         "safe",   "rm -rf",    None),
    ("pip cache",              _HOME / ".cache/pip",                            "safe",   "rm -rf",    None),
    ("Homebrew cache",         _HOME / "Library/Caches/Homebrew",               "safe",   "rm -rf",    None),
    ("CocoaPods cache",        _HOME / ".cocoapods/repos",                      "safe",   "rm -rf",    None),
    ("Gradle cache",           _HOME / ".gradle/caches",                        "safe",   "rm -rf",    None),
    ("App caches (stale)",     _HOME / "Library/Caches",                        "safe",   "rm -rf",    _30_DAYS),
    ("App logs (old)",         _HOME / "Library/Logs",                          "review", "show files", _7_DAYS),
    ("Downloads (old files)",  _HOME / "Downloads",                             "review", "show files", _30_DAYS),
    ("Trash",                  _HOME / ".Trash",                                "safe",   "empty trash", None),
    ("Simulator runtimes",     _HOME / "Library/Developer/CoreSimulator/Caches", "safe",  "rm -rf",    None),
]


@dataclass
class CleanupCandidate:
    category: str
    path: Path
    size_bytes: int
    risk: str    # "safe" | "review"
    action: str


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    total += _dir_size(Path(entry.path))
                else:
                    total += entry.stat(follow_symlinks=False).st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def _stale_size(path: Path, max_age_secs: int) -> int:
    """Size of files/subdirs in path whose mtime is older than max_age_secs."""
    cutoff = time.time() - max_age_secs
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                st = entry.stat(follow_symlinks=False)
                if st.st_mtime < cutoff:
                    if entry.is_dir(follow_symlinks=False):
                        total += _dir_size(Path(entry.path))
                    else:
                        total += st.st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def scan_cleanup_candidates(
    min_size_bytes: int = 50 * 1024 * 1024,
) -> list[CleanupCandidate]:
    """Scan well-known locations for reclaimable disk space.

    Returns candidates sorted by size descending.
    Only paths that actually exist and exceed min_size_bytes are included.
    """
    candidates: list[CleanupCandidate] = []
    for category, path, risk, action, stale_secs in _CATALOGUE:
        if not path.exists():
            continue
        if stale_secs is not None:
            size = _stale_size(path, stale_secs)
        else:
            size = _dir_size(path)
        if size >= min_size_bytes:
            candidates.append(
                CleanupCandidate(
                    category=category,
                    path=path,
                    size_bytes=size,
                    risk=risk,
                    action=action,
                )
            )
    candidates.sort(key=lambda c: c.size_bytes, reverse=True)
    return candidates
