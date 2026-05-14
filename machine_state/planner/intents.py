"""Intent detection and classification.

Maps a natural language query to a structured intent with:
  - intent name
  - ordered list of tools to call
  - parameters extracted from the query

Intent detection is fully deterministic (regex-based).
No LLM involvement at this stage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Intent:
    name: str
    description: str
    tools: list[str]
    parameters: dict[str, Any] = field(default_factory=dict)


# ── Parameter extractors ───────────────────────────────────────────────────────

def _extract_app_name(query: str) -> str:
    """Extract an application name from install/profile queries."""
    patterns = [
        r"\binstall\s+['\"]?([A-Za-z0-9][A-Za-z0-9 ._+-]{1,40}?)['\"]?(?:\s*\?|$)",
        r"\brun\s+['\"]?([A-Za-z0-9][A-Za-z0-9 ._+-]{1,40}?)['\"]?(?:\s*\?|$)",
        r"\babout\s+['\"]?([A-Za-z0-9][A-Za-z0-9 ._+-]{1,40}?)['\"]?(?:\s*\?|$)",
        r"\bfor\s+['\"]?([A-Za-z0-9][A-Za-z0-9 ._+-]{1,40}?)['\"]?(?:\s*\?|$)",
        r"\bprofile\s+(?:of\s+)?['\"]?([A-Za-z0-9][A-Za-z0-9 ._+-]{1,40}?)['\"]?(?:\s*\?|$)",
        r"\bapp(?:lication)?\s+['\"]?([A-Za-z0-9][A-Za-z0-9 ._+-]{1,40}?)['\"]?(?:\s*\?|$)",
        r"\btell\s+me\s+about\s+['\"]?([A-Za-z0-9][A-Za-z0-9 ._+-]{1,40}?)['\"]?(?:\s*\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip(".")
    return ""


def _extract_gb(query: str) -> float:
    """Extract a GB value from a query."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:gb|gigabyte)", query, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 0.0


def _extract_window(query: str) -> int:
    """Extract a snapshot window size from a query."""
    match = re.search(r"(?:last|past|over)\s+(\d+)\s+(?:snapshot|hour|minute|reading)", query, re.IGNORECASE)
    if match:
        return max(1, min(50, int(match.group(1))))
    return 6


# ── Intent patterns ────────────────────────────────────────────────────────────
# Each pattern: (intent_name, compiled_regex, tools_list)

_PATTERNS: list[tuple[str, re.Pattern[str], list[str]]] = [

    # install feasibility: "can I install X", "will X fit", "enough space for X"
    (
        "install_feasibility",
        re.compile(
            r"\b(?:can\s+i\s+install|will\s+.+\s+fit|enough\s+(?:space|room|disk)|"
            r"install\s+.+\?|space\s+for\s+.+\?|fit\s+.+\?)\b",
            re.IGNORECASE,
        ),
        ["check_install_compatibility", "get_system_storage"],
    ),

    # compatibility check: "can I run X", "will X work on my machine"
    # Excludes "will X run out" (handled by pressure_forecast)
    (
        "compatibility_check",
        re.compile(
            r"\b(?:can\s+i\s+run|will\s+.+\s+(?:work|run(?!\s+out))|"
            r"(?:run|play|launch)\s+.+\s+on\s+(?:my|this)\s+(?:machine|mac|computer))\b",
            re.IGNORECASE,
        ),
        ["get_machine_health", "get_ram_info", "get_disk_info"],
    ),

    # slowdown / performance analysis: "why is my machine slow", "why is performance bad"
    (
        "slowdown_analysis",
        re.compile(
            r"\b(?:why\s+is\s+(?:my\s+)?(?:machine|mac|computer|system)\s+slow|"
            r"why\s+is\s+(?:performance|everything)\s+(?:slow|bad|laggy)|"
            r"what\s+is\s+(?:slowing|hogging|using\s+all)|"
            r"machine\s+(?:slow|lagging|sluggish|unresponsive))\b",
            re.IGNORECASE,
        ),
        ["get_pressure_summary", "get_top_processes", "get_activity_pattern", "get_events"],
    ),

    # system health: "is my system healthy", "how is my system"
    (
        "health_check",
        re.compile(
            r"\b(?:(?:is\s+(?:my\s+)?)?system\s+healthy|how\s+is\s+(?:my\s+)?(?:system|machine|mac)|"
            r"system\s+(?:status|state|summary)|machine\s+(?:health|status|ok|fine)|"
            r"overall\s+(?:health|status))\b",
            re.IGNORECASE,
        ),
        ["get_machine_health"],
    ),

    # pressure analysis: "what's my RAM pressure", "memory pressure", "disk pressure"
    (
        "pressure_analysis",
        re.compile(
            r"\b(?:(?:ram|memory|disk|storage)\s+pressure|"
            r"pressure\s+(?:state|status|level|summary)|"
            r"how\s+(?:much\s+)?(?:memory|ram|disk)\s+pressure)\b",
            re.IGNORECASE,
        ),
        ["get_pressure_summary", "get_top_processes"],
    ),

    # storage cleanup: "what can I clean up", "free up space", "storage breakdown"
    (
        "storage_cleanup_advice",
        re.compile(
            r"\b(?:clean\s*up|free\s+(?:up\s+)?(?:space|storage|disk)|"
            r"what\s+(?:to\s+)?(?:delete|remove|clear)|storage\s+breakdown|"
            r"disk\s+(?:categories|breakdown|usage\s+by))\b",
            re.IGNORECASE,
        ),
        ["get_system_storage"],
    ),

    # app usage / activity: "what apps do I use", "most used apps", "dominant applications"
    (
        "activity_analysis",
        re.compile(
            r"\b(?:what\s+apps?\s+(?:do\s+i\s+use|am\s+i\s+using|run\s+most)|"
            r"most\s+(?:used|heavy|common)\s+apps?|dominant\s+app|"
            r"peak\s+(?:hours|usage\s+time)|usage\s+pattern|activity\s+pattern)\b",
            re.IGNORECASE,
        ),
        ["get_activity_pattern", "get_application_usage"],
    ),

    # app profile: "tell me about Windsurf", "profile of Chrome", "how much memory does X use"
    # Must come BEFORE ram_query because "how much memory does X" is more specific
    (
        "app_profile_query",
        re.compile(
            r"\b(?:tell\s+me\s+about|profile\s+(?:of\s+)?|app(?:lication)?\s+profile\s+(?:for|of\s+)?|"
            r"info(?:rmation)?\s+(?:about|on|for)\s+|how\s+(?:much\s+)?(?:memory|ram)\s+does\s+)\b",
            re.IGNORECASE,
        ),
        ["get_app_profile", "get_application_usage"],
    ),

    # RAM query: "how much RAM", "memory available", "RAM usage"
    # Uses negative lookahead to avoid matching "how much memory does X use" (app_profile)
    (
        "ram_query",
        re.compile(
            r"\b(?:how\s+much\s+(?:ram|memory)(?!\s+does)|(?:ram|memory)\s+(?:available|free|used|usage)|"
            r"available\s+(?:ram|memory)|free\s+(?:ram|memory))\b",
            re.IGNORECASE,
        ),
        ["get_ram_info"],
    ),

    # Disk query: "how much disk space", "storage space", "disk usage"
    # Excludes named-entity queries like "taken by X" or "used by X" (handled by query.py)
    (
        "disk_query",
        re.compile(
            r"\b(?:how\s+much\s+(?:disk|storage|space)(?!\s+(?:is\s+)?(?:taken|used)\s+by)|"
            r"(?:disk|storage)\s+(?:space|usage|available|free)|"
            r"free\s+(?:disk|storage)\s+space|(?:disk|storage)\s+(?:status|info))\b",
            re.IGNORECASE,
        ),
        ["get_disk_info", "get_system_storage"],
    ),

    # ── Phase 8: Predictive intents ────────────────────────────────────────────

    # Disk forecast: "when will my disk fill up", "disk growth rate", "disk exhaustion"
    (
        "disk_forecast",
        re.compile(
            r"\b(?:when\s+will\s+(?:my\s+)?disk\s+(?:fill|be\s+full|run\s+out)|"
            r"disk\s+(?:exhaustion|growth\s+rate|growth\s+forecast|forecast|filling\s+up)|"
            r"how\s+fast\s+is\s+(?:my\s+)?disk\s+(?:filling|growing)|"
            r"disk\s+running\s+out|how\s+long\s+(?:until|till|before)\s+(?:my\s+)?disk)\b",
            re.IGNORECASE,
        ),
        ["forecast_disk_growth"],
    ),

    # Pressure forecast: "RAM trajectory", "will RAM fill up", "memory forecast"
    (
        "pressure_forecast",
        re.compile(
            r"\b(?:(?:ram|memory)\s+trajectory|"
            r"(?:ram|memory)\s+(?:forecast|prediction|trend\s+over)|"
            r"when\s+will\s+(?:ram|memory)\s+(?:fill|run\s+out|be\s+full)|"
            r"predict\s+(?:ram|memory)\s+(?:usage|pressure)|"
            r"how\s+fast\s+is\s+(?:ram|memory)\s+(?:growing|increasing))\b",
            re.IGNORECASE,
        ),
        ["predict_ram_pressure"],
    ),

    # Install impact: "what happens if I install", "simulate install", "after installing"
    (
        "install_impact",
        re.compile(
            r"\b(?:what\s+happens\s+(?:if|after)\s+i\s+install|"
            r"simulate\s+install|"
            r"impact\s+of\s+installing|"
            r"after\s+installing\s+.+\s+(?:will|how)|"
            r"long[- ]term\s+(?:disk|space)\s+(?:after|impact))\b",
            re.IGNORECASE,
        ),
        ["simulate_install", "forecast_disk_growth"],
    ),

    # Workload patterns: "workload patterns", "recurring slowdowns", "system trajectory"
    (
        "workload_analysis",
        re.compile(
            r"\b(?:workload\s+(?:pattern|analysis|risk)|"
            r"system\s+trajectory|"
            r"recurring\s+slowdown|"
            r"when\s+does\s+(?:my\s+)?(?:system|machine|mac)\s+(?:get|become|feel|slow)\s+slow|"
            r"what\s+time\s+(?:of\s+(?:day\s+)?)?is\s+(?:my\s+)?(?:system|machine)\s+slow|"
            r"usage\s+trajectory|"
            r"show\s+(?:me\s+)?workload|"
            r"recurring\s+(?:slowdowns?|pressure|high\s+usage)|"
            r"(?:slowdowns?\s+on\s+(?:my\s+)?(?:system|machine|mac)))\b",
            re.IGNORECASE,
        ),
        ["analyze_workload"],
    ),

    # Restart / shutdown safety: "is it safe to restart", "can I reboot", "safe to shut down"
    (
        "restart_safety",
        re.compile(
            r"\b(?:(?:is\s+it\s+)?safe\s+to\s+(?:restart|reboot|shut\s*down|turn\s+off)|"
            r"can\s+i\s+(?:restart|reboot|shut\s*down|turn\s+off)|"
            r"should\s+i\s+(?:restart|reboot|shut\s*down)|"
            r"(?:restart|reboot|shut\s*down)\s+(?:now|right\s+now|my\s+(?:mac|machine|computer)))\b",
            re.IGNORECASE,
        ),
        ["get_machine_health", "get_pressure_summary", "get_top_processes"],
    ),

    # Trend analysis: "system trends", "overall risk", "proactive insights"
    (
        "trend_analysis",
        re.compile(
            r"\b(?:system\s+(?:trends|risk\s+score|risk\s+assessment)|"
            r"(?:overall\s+)?risk\s+(?:score|assessment|level)|"
            r"proactive\s+(?:insights?|tips?|advice|warnings?)|"
            r"what\s+should\s+i\s+(?:know|watch|worry)\s+about|"
            r"predictive\s+(?:health|summary|insights?))\b",
            re.IGNORECASE,
        ),
        ["get_system_trends", "analyze_workload"],
    ),
]

# ── Fallback intent ────────────────────────────────────────────────────────────

_FALLBACK = Intent(
    name="unknown",
    description="No specific intent detected. Falls back to query.py.",
    tools=[],
)


# ── Parameter builders for each intent ────────────────────────────────────────

def _build_parameters(intent_name: str, query: str) -> dict[str, Any]:
    """Extract intent-specific parameters from the raw query."""
    params: dict[str, Any] = {}

    if intent_name == "install_feasibility":
        app_name = _extract_app_name(query)
        required_gb = _extract_gb(query)
        params["check_install_compatibility"] = {
            "app_name": app_name,
            "required_gb": required_gb,
        }

    elif intent_name == "compatibility_check":
        app_name = _extract_app_name(query)
        params["_app_name"] = app_name  # context for aggregation

    elif intent_name == "slowdown_analysis":
        params["get_pressure_summary"] = {"window": _extract_window(query)}
        params["get_top_processes"] = {"limit": 5}
        params["get_events"] = {"limit": 10}

    elif intent_name == "pressure_analysis":
        params["get_pressure_summary"] = {"window": _extract_window(query)}
        params["get_top_processes"] = {"limit": 5}

    elif intent_name == "app_profile_query":
        name = _extract_app_name(query)
        if name:
            params["get_app_profile"] = {"name": name}
        params["get_application_usage"] = {"top_n": 5}

    elif intent_name == "activity_analysis":
        params["get_application_usage"] = {"top_n": 5}

    elif intent_name == "get_top_processes":
        params["get_top_processes"] = {"limit": 5}

    elif intent_name == "install_impact":
        required_gb = _extract_gb(query)
        params["simulate_install"] = {"required_gb": required_gb}
        params["forecast_disk_growth"] = {"threshold_percent": 95.0, "limit": 5}

    elif intent_name == "disk_forecast":
        params["forecast_disk_growth"] = {"threshold_percent": 95.0, "limit": 5}

    elif intent_name == "trend_analysis":
        params["get_system_trends"] = {"top_n": 5}

    return params


# ── Public interface ───────────────────────────────────────────────────────────

def detect_intent(query: str) -> Intent:
    """Map a natural language query to a structured Intent.

    Matching is done in priority order — first match wins.
    Returns a fallback intent if no pattern matches.
    """
    lowered = query.lower()

    for intent_name, pattern, tools in _PATTERNS:
        if pattern.search(lowered):
            params = _build_parameters(intent_name, query)
            return Intent(
                name=intent_name,
                description=_DESCRIPTIONS.get(intent_name, ""),
                tools=tools,
                parameters=params,
            )

    return _FALLBACK


_DESCRIPTIONS: dict[str, str] = {
    "install_feasibility": "Determines if an application can be safely installed given current disk state.",
    "compatibility_check": "Checks if the machine has sufficient resources to run an application.",
    "slowdown_analysis": "Diagnoses why the machine is slow by analyzing pressure, processes, and events.",
    "health_check": "Provides a complete machine health assessment.",
    "pressure_analysis": "Reports the current RAM and disk pressure state.",
    "storage_cleanup_advice": "Identifies storage categories that can be cleaned up.",
    "activity_analysis": "Analyzes usage patterns: peak hours, dominant apps, behavioral classification.",
    "app_profile_query": "Provides a semantic profile for a specific named application.",
    "ram_query": "Returns current RAM utilization.",
    "disk_query": "Returns current disk space utilization.",
    "restart_safety": "Evaluates whether it is safe to restart or shut down the machine right now.",
    "unknown": "No intent matched. Will delegate to query.py.",
    "disk_forecast": "Forecasts when disk will be exhausted and identifies fastest-growing folders.",
    "pressure_forecast": "Predicts RAM saturation trajectory and recurring high-pressure windows.",
    "install_impact": "Simulates post-install disk state and long-term safety.",
    "workload_analysis": "Analyzes recurring workload patterns and identifies slowdown windows.",
    "trend_analysis": "Returns overall risk score, app memory trends, and proactive operational insights.",
}
