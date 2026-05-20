"""CLI handler for `machine-state diff --from X --to Y` (Phase 9)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .. import store
from ..diff import compare_snapshots, resolve_time_ref, find_snapshot_near
from ..constants import GB, MB
from ._utils import _print_json

_B  = "\033[1m"
_R  = "\033[0m"
_D  = "\033[2m"
_GR = "\033[1;32m"
_RD = "\033[1;31m"


def _fmt(n: int) -> str:
    if abs(n) >= GB:
        return f"{n / GB:+.1f} GB"
    if abs(n) >= MB:
        return f"{n / MB:+.0f} MB"
    return f"{n:+,} B"


def _fmt_abs(n: int) -> str:
    if n >= GB:
        return f"{n / GB:.1f} GB"
    if n >= MB:
        return f"{n / MB:.0f} MB"
    return f"{n / 1024:.0f} KB"


def _diff_command(args: argparse.Namespace) -> int:
    all_snapshots = store.get_all_snapshots(db_path=args.db, limit=500)
    if not all_snapshots:
        print("  No snapshots available.")
        return 1

    try:
        from_dt = resolve_time_ref(args.from_ref)
        to_dt   = resolve_time_ref(args.to_ref)
    except ValueError as exc:
        print(f"  Error: {exc}")
        return 1

    from_snap = find_snapshot_near(from_dt, all_snapshots)
    to_snap   = find_snapshot_near(to_dt, all_snapshots)

    if from_snap is None or to_snap is None:
        print("  Could not find matching snapshots for the given time references.")
        return 1

    if getattr(args, "json", False):
        _print_json(compare_snapshots(to_snap, from_snap))
        return 0

    result = compare_snapshots(to_snap, from_snap)
    if not result.get("available"):
        print(f"  {result.get('reason')}")
        return 1

    from_ts = result["previousTimestamp"] or "?"
    to_ts   = result["currentTimestamp"] or "?"
    print(f"\n  Changes:  {_D}{from_ts}{_R}  →  {_D}{to_ts}{_R}\n")

    ram  = result.get("ram", {})
    disk = result.get("disk", {})

    ram_delta  = ram.get("usedBytesDelta", 0)
    disk_delta = disk.get("usedBytesDelta", 0)
    ram_col    = _RD if ram_delta > 0 else _GR
    disk_col   = _RD if disk_delta > 0 else _GR

    print(f"  {_B}RAM{_R}   used: {ram_col}{_fmt(ram_delta)}{_R}")
    print(f"  {_B}Disk{_R}  used: {disk_col}{_fmt(disk_delta)}{_R}\n")

    apps = [a for a in result.get("applications", []) if a["status"] != "unchanged"][:8]
    if apps:
        print(f"  {_B}Applications{_R}")
        for a in apps:
            status = a["status"]
            col = _GR if status == "new" else (_RD if status == "terminated" else "")
            mem = a.get("memoryBytesDelta", 0)
            mem_str = _fmt(mem) if mem else ""
            print(f"    {col}{a['application']:<22}{_R}  {_D}{status:<12}{_R}  {mem_str}")

    folders = result.get("folders", [])[:5]
    if folders:
        print(f"\n  {_B}Folders{_R}")
        for f in folders:
            col = _RD if f["sizeBytesDelta"] > 0 else _GR
            print(f"    {f.get('path','?'):<40}  {col}{_fmt(f['sizeBytesDelta'])}{_R}")

    print()
    return 0
