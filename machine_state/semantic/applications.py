"""Semantic application identity and profiling.

Transforms raw process/application data into rich semantic understanding:
- category (browser, IDE, communication, etc.)
- memory classification (heavy/moderate/light)
- pressure impact
- presence and recurrence patterns
"""

from __future__ import annotations

from typing import Any

# ── Category definitions ──────────────────────────────────────────────────────

APP_CATEGORIES: dict[str, list[str]] = {
    "browser": [
        "chrome", "google chrome", "firefox", "safari", "edge", "brave",
        "opera", "arc", "chromium",
    ],
    "ide": [
        "windsurf", "cursor", "vscode", "visual studio code", "xcode",
        "android studio", "intellij", "pycharm", "webstorm", "goland",
        "clion", "datagrip", "rubymine", "appcode", "fleet", "zed",
        "sublime text", "nova", "bbedit", "codex",
    ],
    "communication": [
        "slack", "discord", "zoom", "teams", "microsoft teams", "whatsapp",
        "telegram", "signal", "skype", "facetime", "messages",
    ],
    "media": [
        "spotify", "vlc", "quicktime", "itunes", "music", "podcasts",
        "plex", "infuse", "iina", "fstream", "handbrake",
    ],
    "productivity": [
        "notion", "obsidian", "word", "excel", "powerpoint",
        "pages", "numbers", "keynote", "1password", "bitwarden",
        "alfred", "raycast", "bartender", "magnet", "rectangle",
    ],
    "dev_tool": [
        "docker", "gopls", "node", "python", "python3", "ruby",
        "java", "gradle", "maven", "npm", "yarn", "pnpm",
        "git", "gh", "aws", "gcloud", "terraform", "kubectl",
        "postgres", "mysql", "redis", "mongodb",
        "postman", "insomnia", "charles", "proxyman", "wireshark",
    ],
    "security": [
        "kaspersky", "kaspersky anti-virus for mac", "bitdefender", "malwarebytes",
        "crowdstrike", "carbon black", "sentinelone", "avast", "norton",
        "little snitch", "lulu", "radio silence",
    ],
    "ai": [
        "claude", "chatgpt", "copilot", "ollama", "lm studio",
    ],
    "system": [
        "finder", "activity monitor", "system preferences", "system settings",
        "terminal", "iterm2", "warp", "ghostty", "spotlight",
        "windowserver", "loginwindow", "launchd", "kernel_task",
    ],
    "cloud": [
        "dropbox", "google drive", "onedrive", "icloud", "box",
        "mega", "backblaze",
    ],
    "game": [
        "steam", "epic games", "gog galaxy", "battle.net", "origin",
    ],
}

from ..constants import (
    GB,
    APP_HEAVY_THRESHOLD_BYTES,
    APP_MODERATE_THRESHOLD_BYTES,
    APP_ALWAYS_ON_RATIO,
    APP_FREQUENT_RATIO,
)


def classify_application(name: str) -> str:
    """Return the semantic category for an application name."""
    lowered = name.strip().lower()
    for category, keywords in APP_CATEGORIES.items():
        for keyword in keywords:
            if keyword in lowered or lowered in keyword:
                return category
    return "other"


def classify_memory(average_bytes: int) -> str:
    """Return memory classification based on average usage."""
    if average_bytes >= APP_HEAVY_THRESHOLD_BYTES:
        return "heavy"
    if average_bytes >= APP_MODERATE_THRESHOLD_BYTES:
        return "moderate"
    return "light"


def classify_pressure_impact(strength: float) -> str:
    """Return pressure impact classification from temporal relationship strength."""
    if strength >= 0.5:
        return "high"
    if strength >= 0.25:
        return "moderate"
    return "low"


def classify_presence_pattern(presence_ratio: float) -> str:
    """Return presence pattern from observation ratio."""
    if presence_ratio >= APP_ALWAYS_ON_RATIO:
        return "always_on"
    if presence_ratio >= APP_FREQUENT_RATIO:
        return "frequent"
    return "occasional"


def _fmt_gb(b: int) -> float:
    return round(b / GB, 2)


def build_application_semantic_profile(
    name: str,
    entity_history: dict[str, Any] | None = None,
    temporal_strength: float | None = None,
) -> dict[str, Any]:
    """Build a rich semantic profile for an application.

    Args:
        name: Application name (e.g. "Google Chrome").
        entity_history: Result from entity_history.get_application_profile().
        temporal_strength: Strength score from temporal relationships (0–1).
    """
    category = classify_application(name)

    # Memory profile from entity history
    memory_profile: dict[str, Any] = {"available": False}
    presence_pattern = "unknown"
    if entity_history and entity_history.get("available"):
        mem = entity_history.get("memory", {})
        avg_bytes = int(mem.get("averageBytes") or 0)
        peak_bytes = int(mem.get("peakBytes") or 0)
        obs = int(entity_history.get("totalObservations") or 0)
        total = int(entity_history.get("presenceCount") or obs)
        # presenceRatio: how often it appeared relative to total snapshots
        # We use presenceCount as available observations
        ratio = 1.0  # if we only have presence data, assume it was there when observed
        memory_profile = {
            "available": True,
            "classification": classify_memory(avg_bytes),
            "averageGB": _fmt_gb(avg_bytes),
            "peakGB": _fmt_gb(peak_bytes),
            "latestGB": _fmt_gb(int(mem.get("latestBytes") or 0)),
            "trend": mem.get("direction", "unknown"),
            "observationCount": obs,
        }
        presence_pattern = classify_presence_pattern(ratio)

    # Pressure impact from temporal relationships
    pressure_impact = "unknown"
    if temporal_strength is not None:
        pressure_impact = classify_pressure_impact(temporal_strength)

    return {
        "name": name,
        "category": category,
        "memoryProfile": memory_profile,
        "pressureImpact": pressure_impact,
        "presencePattern": presence_pattern,
        "temporalStrength": temporal_strength,
    }


def build_all_application_profiles(
    snapshot: dict[str, Any],
    temporal_relationships: list[dict[str, Any]] | None = None,
    entity_profiles: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build semantic profiles for all applications in the latest snapshot."""
    # Build temporal strength lookup
    strength_map: dict[str, float] = {}
    for rel in (temporal_relationships or []):
        entity_id = str(rel.get("from", ""))
        strength_map[entity_id] = float(rel.get("strength") or 0.0)

    profiles: list[dict[str, Any]] = []
    for app in snapshot.get("derived", {}).get("applications", []):
        app_name = str(app.get("application", ""))
        entity_id = f"application:{app_name.strip().lower()}"

        hist = (entity_profiles or {}).get(entity_id)
        strength = strength_map.get(entity_id)

        profile = build_application_semantic_profile(app_name, hist, strength)
        # Enrich with live data from snapshot
        profile["liveMemoryBytes"] = int(app.get("totalMemoryBytes") or 0)
        profile["liveMemoryGB"] = _fmt_gb(profile["liveMemoryBytes"])
        profile["liveProcessCount"] = int(app.get("processCount") or 0)
        profiles.append(profile)

    profiles.sort(key=lambda p: (-p["liveMemoryBytes"], p["name"]))
    return profiles


def get_heavy_applications(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter profiles to only heavy/high-impact applications."""
    return [
        p for p in profiles
        if p.get("memoryProfile", {}).get("classification") == "heavy"
        or p.get("pressureImpact") == "high"
        or p.get("liveMemoryGB", 0) >= 0.5
    ]
