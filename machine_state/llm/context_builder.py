"""Context builder for LLM consumption.

Converts structured PlanResult objects into clean, human-readable context
strings that the LLM can reason over.

Principles:
  - Never pass raw snapshots or byte values to the LLM
  - Convert all sizes to GB with 2 decimal places
  - Convert all scores to labeled states
  - Omit fields that are None or unavailable
  - Keep the context focused and minimal — only what the LLM needs
"""

from __future__ import annotations

from typing import Any


def _gb(value: Any) -> str:
    if value is None:
        return "unknown"
    try:
        return f"{float(value):.2f} GB"
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any) -> str:
    if value is None:
        return "unknown"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _label(d: dict[str, Any], key: str, fallback: str = "unknown") -> str:
    return str(d.get(key) or fallback)


# ── Per-intent context formatters ──────────────────────────────────────────────

def _fmt_pressure(data: dict[str, Any]) -> str:
    lines = []
    overall = data.get("overall", {})
    if overall:
        lines.append(f"Overall pressure: {_label(overall, 'label')} — {_label(overall, 'meaning')}")
        lines.append(f"Urgency: {_label(overall, 'urgency')}")

    ram = data.get("ram", {})
    if ram.get("available"):
        lines.append(
            f"RAM: {_label(ram, 'label')} (score {_pct(ram.get('scorePercent'))}) "
            f"— sustained={ram.get('sustained', False)}"
        )
        lines.append(f"RAM recommendation: {_label(ram, 'recommendation')}")

    disk = data.get("disk", {})
    if disk.get("available"):
        lines.append(
            f"Disk: {_label(disk, 'label')} (score {_pct(disk.get('scorePercent'))}) "
            f"— {_gb(disk.get('freeGB'))} free of {_gb(disk.get('totalGB'))}"
        )
        lines.append(f"Disk recommendation: {_label(disk, 'recommendation')}")

    contributors = data.get("topContributors", [])
    if contributors:
        lines.append("Top memory consumers:")
        for c in contributors[:3]:
            app = c.get("application", "unknown")
            mem = _gb(c.get("memoryGB"))
            pct = _pct(c.get("ramPercent"))
            lines.append(f"  • {app}: {mem} ({pct} of RAM)")

    return "\n".join(lines)


def _fmt_capabilities(data: dict[str, Any]) -> str:
    lines = []
    caps = data.get("capabilities", {})
    if caps:
        lines.append(f"Can run heavy app (needs 4 GB free RAM): {caps.get('canRunHeavyApp')}")
        lines.append(f"Can run moderate app (needs 1 GB free RAM): {caps.get('canRunModerateApp')}")
        lines.append(f"Can install large app (needs 10 GB disk): {caps.get('canInstallLargeApp')}")
        lines.append(f"Can install small app (needs 5 GB disk): {caps.get('canInstallSmallApp')}")
        lines.append(f"System overall healthy: {caps.get('systemHealthy')}")

    ram = data.get("ram", {})
    if ram.get("available"):
        lines.append(
            f"RAM: {_gb(ram.get('availableGB'))} available of {_gb(ram.get('totalGB'))} total "
            f"({_pct(ram.get('pressureRatio', 0) * 100 if ram.get('pressureRatio') else None)} used)"
        )

    disk = data.get("disk", {})
    if disk:
        lines.append(
            f"Disk: {_gb(disk.get('freeGB'))} free of {_gb(disk.get('totalGB'))} total "
            f"({_pct(disk.get('percentUsed'))} used)"
        )

    recs = data.get("recommendations", [])
    if recs:
        lines.append("Recommendations: " + "; ".join(r for r in recs if r))

    return "\n".join(lines)


def _fmt_storage(data: dict[str, Any]) -> str:
    lines = []

    if data.get("freeGB") is not None:
        total = data.get("totalGB")
        if total:
            lines.append(f"Free disk space: {_gb(data.get('freeGB'))} of {_gb(total)}")
        else:
            lines.append(f"Free disk space: {_gb(data.get('freeGB'))}")

    if data.get("status"):
        lines.append(f"Status: {_label(data, 'status')}")

    safe = data.get("safeForLargeInstall")
    if safe is not None:
        lines.append(f"Safe for large install (>10 GB free): {safe}")

    # Handle both flattened aggregated format and raw nested format
    cleanup_gb = data.get("cleanupPotentialGB")
    candidates = data.get("cleanupCandidates", [])
    categories = data.get("topCategories", [])

    # Also handle raw nested breakdown format
    breakdown = data.get("breakdown", {})
    if breakdown.get("available"):
        cleanup_gb = cleanup_gb or breakdown.get("cleanupPotentialGB")
        candidates = candidates or breakdown.get("cleanupCandidates", [])
        categories = categories or breakdown.get("categories", [])

    if cleanup_gb:
        lines.append(f"Cleanup potential: {_gb(cleanup_gb)}")
    if candidates:
        lines.append(f"Safe to clean: {', '.join(candidates)}")
    if categories:
        lines.append("Storage by category:")
        for cat in categories[:6]:
            safe_flag = " (safe to clean)" if cat.get("cleanupSafe") else ""
            lines.append(f"  • {cat.get('label', '?')}: {_gb(cat.get('sizeGB'))}{safe_flag}")

    return "\n".join(lines)


def _fmt_activity(data: dict[str, Any]) -> str:
    lines = [
        f"System behavior: {_label(data, 'systemBehaviorLabel')}",
        f"Pressure pattern: {_label(data, 'pressurePatternLabel')}",
    ]
    peak = data.get("topPeakHours", [])
    if peak:
        lines.append(f"Peak usage hours: {', '.join(str(h) for h in peak)}")
    apps = data.get("dominantApplications", [])
    if apps:
        lines.append("Most-used applications:")
        for app in apps[:5]:
            name = app.get("application", "?")
            presence = _pct(app.get("presenceRatio", 0) * 100)
            mem = _gb(app.get("averageMemoryGB"))
            lines.append(f"  • {name}: present {presence} of the time, avg {mem} RAM")
    return "\n".join(lines)


def _fmt_app_profile(data: dict[str, Any]) -> str:
    lines = [
        f"Application: {_label(data, 'name')}",
        f"Category: {_label(data, 'category')}",
        f"Presence pattern: {_label(data, 'presencePattern')}",
        f"Pressure impact: {_label(data, 'pressureImpact')}",
    ]
    mem = data.get("memoryProfile", {})
    if mem.get("available"):
        lines.append(
            f"Memory: avg {_gb(mem.get('averageGB'))}, peak {_gb(mem.get('peakGB'))}, "
            f"trend: {_label(mem, 'trend')} (over {mem.get('observationCount', '?')} observations)"
        )
    return "\n".join(lines)


def _fmt_ram(data: dict[str, Any]) -> str:
    return "\n".join([
        f"Total RAM: {_gb(data.get('totalGB'))}",
        f"Used RAM: {_gb(data.get('usedGB'))}",
        f"Available RAM: {_gb(data.get('availableGB'))}",
        f"Pressure: {_pct(data.get('pressureRatio', 0) * 100 if data.get('pressureRatio') else None)}",
        f"Can run heavy app: {data.get('canRunHeavyApp')}",
        f"Can run moderate app: {data.get('canRunModerateApp')}",
    ])


def _fmt_disk(data: dict[str, Any]) -> str:
    return "\n".join([
        f"Total disk: {_gb(data.get('totalGB'))}",
        f"Used disk: {_gb(data.get('usedGB'))}",
        f"Free disk: {_gb(data.get('freeGB'))}",
        f"Percent used: {_pct(data.get('percentUsed'))}",
        f"Status: {_label(data, 'status')}",
        f"Cleanup potential: {_gb(data.get('cleanupPotentialGB'))}",
    ])


def _fmt_install(data: dict[str, Any]) -> str:
    lines = [
        f"Required space: {_gb(data.get('requiredGB'))}",
        f"Available space: {_gb(data.get('freeGB'))}",
        f"Feasible: {data.get('feasible')}",
        f"Has 5 GB safety buffer: {data.get('hasSafeBuffer')}",
        f"Space remaining after install: {_gb(data.get('remainingAfterInstallGB'))}",
        f"Assessment: {_label(data, 'recommendation')}",
    ]
    if data.get("storageStatus"):
        lines.append(f"Disk status: {data['storageStatus']}")
    if data.get("cleanupPotentialGB"):
        lines.append(f"Cleanup potential if needed: {_gb(data['cleanupPotentialGB'])}")
    return "\n".join(lines)


def _fmt_slowdown(data: dict[str, Any]) -> str:
    lines = [
        f"Primary cause: {_label(data, 'primaryCause')}",
        f"Pressure state: {_label(data, 'pressureState')}",
        f"Meaning: {_label(data, 'pressureMeaning')}",
    ]
    consumers = data.get("topMemoryConsumers", [])
    if consumers:
        lines.append("Top memory consumers right now:")
        for c in consumers[:3]:
            lines.append(
                f"  • {c.get('application', '?')}: "
                f"{_gb(c.get('memoryGB'))} ({_pct(c.get('ramPercent'))} of RAM)"
            )
    behavior = data.get("systemBehavior")
    if behavior:
        lines.append(f"System behavior pattern: {behavior}")
    pattern = data.get("pressurePattern")
    if pattern:
        lines.append(f"Pressure trend: {pattern}")
    events = data.get("recentEvents", [])
    critical_events = [e for e in events if e.get("severity") in ("critical", "warning")]
    if critical_events:
        lines.append("Recent alerts:")
        for e in critical_events[:3]:
            lines.append(f"  • {e.get('type', 'unknown')} ({e.get('severity', '?')})")
    recs = data.get("recommendations", [])
    if recs:
        lines.append("Recommendations: " + "; ".join(r for r in recs if r))
    return "\n".join(lines)


def _fmt_disk_forecast(data: dict[str, Any]) -> str:
    lines = []
    exhaustion = data.get("exhaustion", {})
    if exhaustion.get("available"):
        if exhaustion.get("alreadyExceeded"):
            lines.append(f"Disk has already exceeded {exhaustion.get('thresholdPercent')}% usage.")
        elif exhaustion.get("daysUntilThreshold") is not None:
            lines.append(
                f"Disk forecast: {exhaustion.get('daysUntilThreshold')} days until "
                f"{exhaustion.get('thresholdPercent')}% full."
            )
        if exhaustion.get("rateGBPerDay") is not None:
            lines.append(f"Disk growth rate: {exhaustion.get('rateGBPerDay')} GB/day")
        if exhaustion.get("direction"):
            lines.append(f"Trend direction: {exhaustion.get('direction')}")

    hotspots = data.get("growthHotspots", [])
    if hotspots:
        lines.append("Fastest-growing folders:")
        for h in hotspots[:5]:
            parts = [f"  • {h.get('name', '?')}"]
            if h.get("deltaGB"):
                parts.append(f"grew {h.get('deltaGB')} GB")
            if h.get("rateGBPerDay"):
                parts.append(f"at {h.get('rateGBPerDay')} GB/day")
            lines.append(" — ".join(parts))

    rate = data.get("growthRate", {})
    if rate.get("available") and not exhaustion.get("available"):
        lines.append(f"Disk trend: {_label(rate, 'direction')} at {rate.get('rateGBPerDay')} GB/day")

    return "\n".join(lines)


def _fmt_pressure_forecast(data: dict[str, Any]) -> str:
    lines = []
    traj = data.get("trajectory", {})
    if traj.get("available"):
        lines.append(f"RAM trajectory: {_label(traj, 'direction')}")
        if traj.get("rateGBPerDay") is not None:
            lines.append(f"RAM growth rate: {traj.get('rateGBPerDay')} GB/day")
        if traj.get("usedGB") is not None and traj.get("totalGB") is not None:
            lines.append(f"Current: {_gb(traj.get('usedGB'))} used of {_gb(traj.get('totalGB'))}")
        if traj.get("daysToSaturation") is not None:
            lines.append(f"Estimated days to RAM saturation (95%): {traj.get('daysToSaturation')}")
        elif traj.get("direction") == "flat":
            lines.append("RAM usage is stable — no saturation risk detected.")

    windows = data.get("recurringPressureWindows", {})
    if windows.get("available"):
        high = windows.get("highPressureHours", [])
        if high:
            hours_str = ", ".join(f"{h['hour']}:00" for h in high[:3])
            lines.append(f"Recurring high-pressure hours: {hours_str}")
        else:
            lines.append("No recurring high-pressure windows detected.")

    return "\n".join(lines)


def _fmt_install_impact(data: dict[str, Any]) -> str:
    lines = []
    impact = data.get("impact", {})
    if impact.get("available"):
        lines.append(f"Required: {_gb(impact.get('requiredGB'))}")
        lines.append(f"Current free: {_gb(impact.get('currentFreeGB'))}")
        lines.append(f"Remaining after install: {_gb(impact.get('remainingAfterInstallGB'))}")
        lines.append(f"Feasible: {impact.get('feasible')}")
        lines.append(f"Post-install status: {_label(impact, 'postInstallStatus')}")
        if impact.get("recommendation"):
            lines.append(f"Recommendation: {impact.get('recommendation')}")
        if impact.get("daysUntilFullAfterInstall") is not None:
            lines.append(f"Days until full at current growth rate: {impact.get('daysUntilFullAfterInstall')}")
        if impact.get("longTermWarning"):
            lines.append(f"Long-term warning: {impact.get('longTermWarning')}")

    long_term = data.get("longTerm", {})
    if long_term.get("available"):
        lines.append(f"Safe for 30 days after install: {long_term.get('safeFor30Days')}")
        if long_term.get("projectedGrowthGB"):
            lines.append(f"Projected disk growth in 30 days: {_gb(long_term.get('projectedGrowthGB'))}")
        if long_term.get("reason"):
            lines.append(f"Long-term assessment: {long_term.get('reason')}")

    return "\n".join(lines)


def _fmt_workload_analysis(data: dict[str, Any]) -> str:
    lines = []
    summary = data.get("summary", {})
    if summary.get("available"):
        lines.append(f"Risk level: {_label(summary, 'riskLevel')}")
        lines.append(f"Workload trajectory: {_label(summary, 'trajectory')}")
        if summary.get("description"):
            lines.append(f"Description: {summary.get('description')}")
        if summary.get("riskFactors"):
            lines.append("Risk factors: " + "; ".join(summary.get("riskFactors", [])))

    windows_data = data.get("slowdownWindows", {})
    if windows_data.get("available"):
        windows = windows_data.get("slowdownWindows", [])
        if windows:
            lines.append("Recurring slowdown windows:")
            for w in windows[:3]:
                avg_pct = round(w.get("avgPressureRatio", 0) * 100, 1)
                lines.append(f"  • {w.get('hour')}:00 — {w.get('label')} ({avg_pct}% avg RAM pressure)")
        else:
            lines.append("No recurring slowdown windows detected.")

    return "\n".join(lines)


def _fmt_trend_analysis(data: dict[str, Any]) -> str:
    lines = []
    risk = data.get("riskScore", {})
    if risk.get("available"):
        lines.append(f"Overall risk: {_label(risk, 'riskLevel')} (score: {risk.get('riskScore')}/100)")
        if risk.get("riskFactors"):
            lines.append("Risk factors:")
            for f in risk.get("riskFactors", []):
                lines.append(f"  • {f}")

    app_trends = data.get("appTrends", [])
    if app_trends:
        lines.append("App memory trends:")
        for trend in app_trends[:5]:
            lines.append(
                f"  • {trend.get('application', '?')}: {trend.get('trend', '?')} "
                f"(avg {_gb(trend.get('averageGB'))}, peak {_gb(trend.get('peakGB'))})"
            )

    insights = data.get("insights", [])
    if insights:
        lines.append("Proactive insights:")
        for ins in insights[:4]:
            sev = (ins.get("severity") or "info").upper()
            lines.append(f"  • [{sev}] {ins.get('message', '?')}")

    return "\n".join(lines)


def _fmt_restart_safety(data: dict[str, Any]) -> str:
    safe = data.get("safeToRestart")
    lines = [
        f"Safe to restart: {safe}",
        f"Pressure state: {_label(data, 'pressureLabel')} — {_label(data, 'pressureMeaning')}",
        f"Overall healthy: {data.get('overallHealthy')}",
    ]
    if data.get("ramRecommendation"):
        lines.append(f"RAM: {data['ramRecommendation']}")
    if data.get("diskRecommendation"):
        lines.append(f"Disk: {data['diskRecommendation']}")
    processes = data.get("topProcesses", [])
    if processes:
        lines.append("Active processes that will be interrupted:")
        for p in processes:
            lines.append(
                f"  • {p.get('application', '?')}: "
                f"{_gb(p.get('memoryGB'))} ({_pct(p.get('ramPercent'))} of RAM)"
            )
    return "\n".join(lines)


def _fmt_health(data: dict[str, Any]) -> str:
    lines = [
        f"Overall healthy: {data.get('overallHealthy')}",
        f"Pressure state: {_label(data, 'pressureLabel')}",
    ]
    caps = data.get("capabilities", {})
    if caps:
        lines.append(f"Can run heavy app: {caps.get('canRunHeavyApp')}")
        lines.append(f"Can run moderate app: {caps.get('canRunModerateApp')}")
        lines.append(f"Can install large app: {caps.get('canInstallLargeApp')}")
    recs = data.get("recommendations", [])
    if recs:
        lines.append("Recommendations: " + "; ".join(r for r in recs if r))
    return "\n".join(lines)


# ── Public interface ───────────────────────────────────────────────────────────

_FORMATTERS: dict[str, Any] = {
    "slowdown_analysis": _fmt_slowdown,
    "install_feasibility": _fmt_install,
    "compatibility_check": _fmt_capabilities,
    "health_check": _fmt_health,
    "pressure_analysis": _fmt_pressure,
    "storage_cleanup_advice": _fmt_storage,
    "activity_analysis": _fmt_activity,
    "app_profile_query": _fmt_app_profile,
    "ram_query": _fmt_ram,
    "disk_query": _fmt_disk,
    "restart_safety": _fmt_restart_safety,
    # Phase 8
    "disk_forecast": _fmt_disk_forecast,
    "pressure_forecast": _fmt_pressure_forecast,
    "install_impact": _fmt_install_impact,
    "workload_analysis": _fmt_workload_analysis,
    "trend_analysis": _fmt_trend_analysis,
}


def build_context(intent: str, aggregated: dict[str, Any]) -> str:
    """Build a clean, LLM-ready context string from plan execution results.

    The context is factual, human-readable, and contains only what the LLM
    needs to answer the user's question. Raw bytes and internal IDs are excluded.
    """
    formatter = _FORMATTERS.get(intent)
    if formatter:
        body = formatter(aggregated)
    else:
        # Generic fallback: render key-value pairs
        body = "\n".join(f"{k}: {v}" for k, v in aggregated.items() if v is not None)

    return f"[SYSTEM STATE — {intent.upper().replace('_', ' ')}]\n{body}"
