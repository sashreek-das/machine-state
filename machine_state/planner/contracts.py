"""Tool contract definitions.

Every callable tool exposed to the planner must be registered here.
A tool defines:
  - its name and description
  - allowed parameters with types, constraints, and defaults
  - whether it is safe (read-only, non-destructive)
  - output schema description (human-readable, for AI consumption)

The runtime ONLY executes tools that exist in this registry.
No arbitrary commands or runtime access is permitted outside these contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ParameterType = Literal["string", "integer", "float", "boolean"]


@dataclass
class ParameterSpec:
    type: ParameterType
    required: bool = False
    description: str = ""
    default: Any = None
    enum: list[Any] | None = None
    min_value: float | None = None
    max_value: float | None = None


@dataclass
class ToolSchema:
    parameters: dict[str, ParameterSpec] = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    description: str
    schema: ToolSchema
    safe: bool = True
    output_description: str = ""


# ── Tool Registry ──────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, Tool] = {

    "get_machine_health": Tool(
        name="get_machine_health",
        description="Returns a full machine health assessment combining RAM, disk, pressure, and capability flags.",
        schema=ToolSchema(),
        safe=True,
        output_description="overallHealthy, capabilities (canRunHeavyApp, canInstallLargeApp...), pressure state, recommendations",
    ),

    "get_pressure_summary": Tool(
        name="get_pressure_summary",
        description="Returns the current semantic pressure state for RAM and disk over a recent snapshot window.",
        schema=ToolSchema(parameters={
            "window": ParameterSpec(
                type="integer",
                required=False,
                description="Number of recent snapshots to analyze.",
                default=6,
                min_value=1,
                max_value=50,
            ),
        }),
        safe=True,
        output_description="RAM state (Healthy/Elevated/High/Critical/Sustained Critical), disk state, top contributors, urgency",
    ),

    "get_system_storage": Tool(
        name="get_system_storage",
        description="Returns a categorized storage breakdown with cleanup candidates.",
        schema=ToolSchema(),
        safe=True,
        output_description="freeGB, usedGB, status, categories with sizes, cleanupCandidates, cleanupPotentialGB",
    ),

    "get_application_usage": Tool(
        name="get_application_usage",
        description="Returns a ranked list of applications by memory usage and presence frequency.",
        schema=ToolSchema(parameters={
            "top_n": ParameterSpec(
                type="integer",
                required=False,
                description="Number of top applications to return.",
                default=5,
                min_value=1,
                max_value=20,
            ),
        }),
        safe=True,
        output_description="List of applications with presenceRatio, averageMemoryGB, category, pressureImpact",
    ),

    "get_app_profile": Tool(
        name="get_app_profile",
        description="Returns a semantic profile for a specific named application.",
        schema=ToolSchema(parameters={
            "name": ParameterSpec(
                type="string",
                required=True,
                description="Application name to profile (e.g. 'Windsurf', 'Google Chrome').",
            ),
        }),
        safe=True,
        output_description="category, presencePattern, pressureImpact, memoryProfile (avg, peak, trend), temporalStrength",
    ),

    "check_install_compatibility": Tool(
        name="check_install_compatibility",
        description="Determines whether an application or payload of a given size can be safely installed.",
        schema=ToolSchema(parameters={
            "app_name": ParameterSpec(
                type="string",
                required=False,
                description="Well-known application name for automatic size lookup (e.g. 'xcode', 'docker').",
                default="",
            ),
            "required_gb": ParameterSpec(
                type="float",
                required=False,
                description="Required disk space in gigabytes. Used if app_name size is not known.",
                default=0.0,
                min_value=0.0,
                max_value=2000.0,
            ),
        }),
        safe=True,
        output_description="feasible, hasSafeBuffer, requiredGB, freeGB, remainingAfterInstallGB, recommendation",
    ),

    "get_activity_pattern": Tool(
        name="get_activity_pattern",
        description="Analyzes historical snapshots to identify peak usage hours, dominant apps, and behavioral patterns.",
        schema=ToolSchema(),
        safe=True,
        output_description="systemBehavior, pressurePattern, topPeakHours, dominantApplications (presence + memory)",
    ),

    "get_ram_info": Tool(
        name="get_ram_info",
        description="Returns current RAM utilization: total, used, available in bytes and GB.",
        schema=ToolSchema(),
        safe=True,
        output_description="totalGB, usedGB, availableGB, pressureRatio, canRunHeavyApp, canRunModerateApp",
    ),

    "get_disk_info": Tool(
        name="get_disk_info",
        description="Returns current disk utilization: total, used, free in bytes and GB.",
        schema=ToolSchema(),
        safe=True,
        output_description="totalGB, usedGB, freeGB, percentUsed, status (healthy/low/critical)",
    ),

    "get_top_processes": Tool(
        name="get_top_processes",
        description="Returns the top memory-consuming application groups from the latest snapshot.",
        schema=ToolSchema(parameters={
            "limit": ParameterSpec(
                type="integer",
                required=False,
                description="Maximum number of processes to return.",
                default=5,
                min_value=1,
                max_value=20,
            ),
        }),
        safe=True,
        output_description="List of {application, totalMemoryBytes, memoryGB, processCount}",
    ),

    "get_events": Tool(
        name="get_events",
        description="Returns detected system events from persistent event history.",
        schema=ToolSchema(parameters={
            "event_type": ParameterSpec(
                type="string",
                required=False,
                description="Filter by event type (e.g. 'ram_spike', 'disk_pressure_critical'). Empty = all events.",
                default="",
                enum=["", "ram_spike", "ram_pressure_critical", "disk_pressure_critical",
                      "disk_folder_growth", "disk_cache_explosion", "process_runaway",
                      "application_memory_spike"],
            ),
            "limit": ParameterSpec(
                type="integer",
                required=False,
                description="Maximum number of events to return.",
                default=10,
                min_value=1,
                max_value=100,
            ),
        }),
        safe=True,
        output_description="List of {eventType, severity, timestamp, details}",
    ),

    "get_entity_history": Tool(
        name="get_entity_history",
        description="Returns the behavioral history profile for a tracked entity (application or folder).",
        schema=ToolSchema(parameters={
            "entity_id": ParameterSpec(
                type="string",
                required=True,
                description="Entity identifier in format 'application:Name' or 'folder:/path'.",
            ),
        }),
        safe=True,
        output_description="Entity type, observation count, memory/size stats over time",
    ),

    # ── Phase 8: Predictive Intelligence ──────────────────────────────────────

    "forecast_disk_growth": Tool(
        name="forecast_disk_growth",
        description="Forecasts disk exhaustion date, growth rate in GB/day, and identifies fastest-growing folders.",
        schema=ToolSchema(parameters={
            "threshold_percent": ParameterSpec(
                type="float",
                required=False,
                description="Disk usage percentage threshold to forecast (default 95%).",
                default=95.0,
                min_value=50.0,
                max_value=100.0,
            ),
            "limit": ParameterSpec(
                type="integer",
                required=False,
                description="Number of folder hotspots to return.",
                default=5,
                min_value=1,
                max_value=20,
            ),
        }),
        safe=True,
        output_description="daysUntilThreshold, rateGBPerDay, growthHotspots, direction",
    ),

    "predict_ram_pressure": Tool(
        name="predict_ram_pressure",
        description="Predicts RAM usage trajectory and time to saturation based on historical growth trend.",
        schema=ToolSchema(),
        safe=True,
        output_description="direction, rateGBPerDay, daysToSaturation, usedGB, totalGB, recurringPressureWindows",
    ),

    "simulate_install": Tool(
        name="simulate_install",
        description="Simulates post-install disk state and long-term safety for a given installation size.",
        schema=ToolSchema(parameters={
            "required_gb": ParameterSpec(
                type="float",
                required=False,
                description="Required disk space in gigabytes.",
                default=0.0,
                min_value=0.0,
                max_value=2000.0,
            ),
        }),
        safe=True,
        output_description="remainingAfterInstallGB, feasible, hasSafeBuffer, postInstallStatus, daysUntilFullAfterInstall, safeFor30Days",
    ),

    "analyze_workload": Tool(
        name="analyze_workload",
        description="Analyzes recurring workload patterns, slowdown windows, and system trajectory classification.",
        schema=ToolSchema(),
        safe=True,
        output_description="riskLevel, trajectory, description, slowdownWindows, riskFactors",
    ),

    "get_system_trends": Tool(
        name="get_system_trends",
        description="Returns overall machine risk score, per-app memory trends, and proactive operational insights.",
        schema=ToolSchema(parameters={
            "top_n": ParameterSpec(
                type="integer",
                required=False,
                description="Number of app trends to include.",
                default=5,
                min_value=1,
                max_value=10,
            ),
        }),
        safe=True,
        output_description="riskScore (0–100), riskLevel, riskFactors, appTrends, insights",
    ),
}


def get_tool(name: str) -> Tool | None:
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[Tool]:
    return list(TOOL_REGISTRY.values())


def tool_exists(name: str) -> bool:
    return name in TOOL_REGISTRY
