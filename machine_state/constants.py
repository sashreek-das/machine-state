"""Single source of truth for all threshold constants and tuneable defaults.

Every numeric threshold, magic number, and configurable limit in the
machine_state package must live here. No module may define its own copy.

Groups:
  - Storage units (for readable size expressions)
  - RAM pressure levels
  - Disk pressure levels
  - Pressure engine behaviour
  - Event detection thresholds
  - Memory analysis thresholds
  - Install / capability thresholds
  - Forecasting defaults
  - Analysis window / count defaults
"""

from __future__ import annotations

# ── Storage unit multipliers ──────────────────────────────────────────────────

KB: int = 1024
MB: int = 1024 * KB
GB: int = 1024 * MB

# ── RAM pressure levels ───────────────────────────────────────────────────────
# These are the authoritative thresholds used by ALL modules.
# "used / total" ratio at which each level is triggered.

RAM_PRESSURE_MODERATE: float = 0.50   # above this → "moderate"
RAM_PRESSURE_HIGH: float     = 0.75   # above this → "high"
RAM_PRESSURE_CRITICAL: float = 0.90   # above this → "critical"

# ── Disk pressure levels ──────────────────────────────────────────────────────

DISK_PRESSURE_MODERATE: float = 0.65  # above this → "moderate"
DISK_PRESSURE_HIGH: float     = 0.85  # above this → "high"
DISK_PRESSURE_CRITICAL: float = 0.92  # above this → "critical"

# Forecast warning threshold: predict disk exhaustion when usage will hit this.
DISK_FORECAST_THRESHOLD_PCT: float = 95.0

# ── Pressure engine behaviour ─────────────────────────────────────────────────

# Fraction of the snapshot window that must show HIGH pressure for the
# condition to be declared "sustained" (reduces false positives from spikes).
SUSTAINED_PRESSURE_RATIO: float = 0.60

# Number of most-recent snapshots used for live pressure calculation.
PRESSURE_WINDOW_SIZE: int = 6

# ── RAM event detection thresholds ───────────────────────────────────────────

# Minimum between-snapshot growth ratio to emit a ram_spike event.
RAM_SPIKE_RATIO: float = 0.10         # 10% growth

# Fraction of total RAM a single process must consume to be "runaway".
PROCESS_RUNAWAY_RATIO: float = 0.40   # 40% of total RAM

# Application memory growth between snapshots that emits application_memory_spike.
APP_MEMORY_SPIKE_BYTES: int = 200 * MB

# ── Disk event detection thresholds ──────────────────────────────────────────

# Directory growth between consecutive snapshots that emits disk_folder_growth.
FOLDER_GROWTH_EVENT_BYTES: int = 512 * MB

# Directory growth between consecutive snapshots that emits disk_cache_explosion.
CACHE_EXPLOSION_EVENT_BYTES: int = 1 * GB

# ── Long-term memory analysis thresholds ─────────────────────────────────────

# Minimum average memory for an application to be classified "historically heavy".
HEAVY_APP_MIN_BYTES: int = 100 * MB

# Minimum total growth for a folder to be recorded as "growing" in system memory.
GROWING_FOLDER_MIN_DELTA_BYTES: int = 50 * MB

# Minimum folder size to appear in cleanup candidates.
CLEANUP_CANDIDATE_MIN_BYTES: int = 500 * MB

# Minimum between-snapshot RAM growth ratio to count as a spike in the pattern.
RAM_SPIKE_PATTERN_RATIO: float = 0.10  # mirrors RAM_SPIKE_RATIO; kept explicit for clarity

# Number of recent spike timestamps to retain in the pattern record.
RAM_SPIKE_RECENT_LIMIT: int = 5

# Maximum number of cleanup candidates to surface.
CLEANUP_CANDIDATES_MAX: int = 20

# ── Install / capability thresholds ──────────────────────────────────────────

# Minimum free space to keep after any install (safety buffer).
INSTALL_SAFE_BUFFER_BYTES: int = 5 * GB

# Free space above which a machine is "safe for large installs".
LARGE_INSTALL_THRESHOLD_BYTES: int = 10 * GB

# Minimum free RAM required to run a RAM-heavy application.
RAM_HEAVY_APP_FREE_MIN_BYTES: int = 4 * GB

# Minimum free RAM required to run a moderate application.
RAM_MODERATE_APP_FREE_MIN_BYTES: int = 1 * GB

# Minimum free disk percentage; below this the install risk is "critical".
INSTALL_CRITICAL_FREE_PCT: float = 5.0

# ── Forecasting defaults ──────────────────────────────────────────────────────

# Default folder growth forecast target: 2× current size + 10 GB floor.
FOLDER_GROWTH_FORECAST_MULTIPLIER: float = 2.0
FOLDER_GROWTH_FORECAST_FLOOR_BYTES: int = 10 * GB

# ── Analysis window and count defaults ───────────────────────────────────────

# Default number of snapshots to load for time-series history queries.
DEFAULT_HISTORY_LIMIT: int = 12

# Default number of top items to surface in ranked lists.
DEFAULT_TOP_N: int = 10

# Default number of top contributors shown in process pressure analysis.
TOP_PROCESS_CONTRIBUTORS: int = 5

# Maximum number of temporal relationship entries to return.
MAX_TEMPORAL_RELATIONSHIPS: int = 50

# ── Trend analysis pressure labels ───────────────────────────────────────────
# Human-readable label boundaries used by forecasting/trend_analysis.py.
# These intentionally mirror RAM_PRESSURE_* and DISK_PRESSURE_* above.

TREND_RAM_ELEVATED: float  = RAM_PRESSURE_HIGH       # >= 0.75 → "elevated"
TREND_RAM_HIGH: float      = 0.80                    # >= 0.80 → "high"
TREND_RAM_CRITICAL: float  = RAM_PRESSURE_CRITICAL   # >= 0.90 → "critical"

TREND_DISK_MODERATE: float = DISK_PRESSURE_MODERATE  # >= 0.65
TREND_DISK_HIGH: float     = DISK_PRESSURE_HIGH      # >= 0.85
TREND_DISK_CRITICAL: float = DISK_FORECAST_THRESHOLD_PCT / 100.0  # >= 0.95

# ── Workload pattern thresholds ───────────────────────────────────────────────

WORKLOAD_ELEVATED_PRESSURE: float = 0.70   # >= 70% → "elevated" workload window
WORKLOAD_HIGH_PRESSURE: float     = 0.80   # >= 80% → "high" workload window
WORKLOAD_CRITICAL_PRESSURE: float = RAM_PRESSURE_CRITICAL  # >= 0.90 → "critical"

# ── Application classification thresholds ─────────────────────────────────────

APP_HEAVY_THRESHOLD_BYTES: int    = 500 * MB   # avg memory above which an app is "heavy"
APP_MODERATE_THRESHOLD_BYTES: int = 100 * MB   # avg memory above which an app is "moderate"

# Presence ratios for application classification (fraction of snapshots app appears in)
APP_ALWAYS_ON_RATIO: float  = 0.85  # present in 85%+ → "always on"
APP_FREQUENT_RATIO: float   = 0.40  # present in 40%+ → "frequent"

# ── Notification engine thresholds ───────────────────────────────────────────

# Disk fill ETA below which a notification is emitted.
NOTIFICATION_DISK_FILL_HOURS: float = 72.0   # 3 days

# RAM threshold above which a notification is emitted.
NOTIFICATION_RAM_CRITICAL: float = RAM_PRESSURE_CRITICAL

# ── Trend rate thresholds ─────────────────────────────────────────────────────

# Rate above which a disk growth trend is labelled "Rapidly Growing".
TREND_RAPID_GROWTH_BYTES_PER_HOUR: int = 500 * MB

# ── Semantic pressure state boundaries ───────────────────────────────────────
# Used by semantic/pressure.py to classify scores into named states.
# These are the explicit boundary values for each state transition.

SEMANTIC_RAM_SUSTAINED_CRITICAL: float = 0.95  # score above this → sustained_critical
SEMANTIC_RAM_CRITICAL: float           = 0.85  # score above this → critical
SEMANTIC_RAM_HIGH: float               = 0.70  # score above this → high
SEMANTIC_RAM_ELEVATED: float           = RAM_PRESSURE_MODERATE  # 0.50

SEMANTIC_DISK_SUSTAINED_CRITICAL: float = DISK_PRESSURE_CRITICAL  # 0.92
SEMANTIC_DISK_CRITICAL: float           = DISK_PRESSURE_HIGH       # 0.85
SEMANTIC_DISK_HIGH: float               = 0.75
SEMANTIC_DISK_ELEVATED: float           = 0.60

# RAM delta warning for trends (500 MB growth warrants a proactive insight)
RAM_DELTA_WARNING_BYTES: int = 500 * MB
