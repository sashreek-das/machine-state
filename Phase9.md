# Phase 9 — Closing the Loop: Action, Visibility, and Continuity

## Objective

The first eight phases built a machine that observes, classifies, forecasts, and converses.

Phase 9 closes the loop:

* translate insight into **action**
* make state **visible in real time**
* make the tool feel **continuous** across sessions

The machine has been watching. Now it should help.

---

# Core Principle

Every output of this phase must be:

* grounded in data already in SQLite
* deterministic and reproducible
* local-only
* actionable — not just informational

If a feature produces an output the user cannot act on, it does not belong here.

---

# Ideas and Proposed Features

---

## 1. Live TUI Dashboard — `machine-state dash`

**The biggest UX gap in the current tool.**

The user has no way to see the machine's live state without running separate CLI commands. A live dashboard fixes this.

### What it shows

```
╭──────────────────────────────────────────────────────────────────╮
│  machine state  ·  live                          [q] quit        │
╰──────────────────────────────────────────────────────────────────╯

  Health  ████████░░  74 / 100   ↓ degrading since 3h ago

  RAM      ████████░░  14.2 / 16 GB   pressure: elevated
  Disk     ██████░░░░  312 / 500 GB   pressure: normal
  CPU      ███░░░░░░░  22%             load avg: 1.4

  Top processes
  ─────────────────────────────────────────────────
  Chrome           4.1 GB    sustained high
  Xcode            2.8 GB    growing
  Slack            1.2 GB    normal

  Recent events
  ─────────────────────────────────────────────────
  14:22  RAM spike — Chrome  +1.8 GB
  13:50  Disk growth — ~/Downloads  +240 MB
  12:05  Pressure cleared

  Forecast
  ─────────────────────────────────────────────────
  Disk reaches 90% in ~6 days at current growth rate.
```

### Architecture

```text
scheduler → SQLite (every 5 min)
dash → polls SQLite directly (no subprocess)
     → renders ANSI output with cursor control
     → refreshes every 5 seconds
```

### Implementation notes

* Pure stdlib — `curses` or raw ANSI cursor control (same approach as the setup wizard)
* Reads directly from SQLite — no shell subprocesses on refresh
* Fits inside a new `machine_state/tui/` subpackage
* `machine-state dash` CLI command; supports `--interval N` (default 5s)
* Press `q` to quit, `r` to force refresh

---

## 2. Machine Health Score

**A single number that summarises the machine's condition.**

Every snapshot should produce a score from 0 to 100. This score appears in `dash`, in `pressure`, and in `chat` context.

### Scoring formula (deterministic, weights tunable via config)

| Signal | Weight |
|---|---|
| RAM pressure level | 30% |
| Disk pressure level | 25% |
| Process pressure | 15% |
| Active event count (last 1h) | 15% |
| Forecast risk (7-day) | 15% |

Each signal is normalised to 0–100 before weighting.

### Score states

| Range | Label |
|---|---|
| 85–100 | Healthy |
| 65–84 | Elevated |
| 45–64 | Degraded |
| 25–44 | Under stress |
| 0–24 | Critical |

### Storage

Persisted in a new `health_scores` table in SQLite:

```sql
CREATE TABLE IF NOT EXISTS health_scores (
    id         INTEGER PRIMARY KEY,
    ts         INTEGER NOT NULL,
    score      INTEGER NOT NULL,    -- 0-100
    label      TEXT NOT NULL,
    ram_score  INTEGER NOT NULL,
    disk_score INTEGER NOT NULL,
    proc_score INTEGER NOT NULL,
    event_score INTEGER NOT NULL,
    forecast_score INTEGER NOT NULL
);
```

### Usage

```text
machine-state health
→ Score: 74 / 100 (Elevated)
   Trend: ↓ degrading  (was 88 yesterday)
   Top drag: RAM pressure (contributing -18pts)
```

---

## 3. Smart Cleanup Engine — `machine-state cleanup`

**The most actionable feature possible.**

The machine has been tracking folder growth, cache directories, large files, and stale builds. Now surface that as a cleanup plan with expected impact.

### What it finds

| Category | Example paths | Detection method |
|---|---|---|
| App caches | `~/Library/Caches/*` | size + last-accessed time from snapshots |
| Large stale downloads | `~/Downloads/*.dmg` older than 30 days | entity_history growth tracking |
| Xcode derived data | `~/Library/Developer/Xcode/DerivedData` | path pattern + size |
| Old log files | `~/Library/Logs/**/*.log` | size + recency |
| Trash | `~/.Trash` | always surfaced |
| npm / pip caches | `~/.npm`, `~/.cache/pip` | path pattern + size |
| Simulator runtimes | `~/Library/Developer/CoreSimulator/Caches` | size only |

### Output

```text
machine-state cleanup

  Found 18.4 GB of reclaimable space:

  Category                   Size     Risk    Action
  ──────────────────────────────────────────────────
  Xcode Derived Data        11.2 GB   safe    rm -rf
  App caches (stale >30d)    4.1 GB   safe    rm -rf
  Downloads (old DMGs)       2.4 GB   review  show files
  Trash                      0.7 GB   safe    empty
  pip / npm caches           0.4 GB   safe    rm -rf

  Run with --apply to execute safe items (15.8 GB).
  Run with --dry-run to preview exact commands.
```

### Safety contract

* `--apply` only touches items marked `safe`
* `review` items are listed but never auto-deleted
* Every deletion is logged to SQLite before execution
* If a path has changed since the last snapshot, skip it

### New module

```text
machine_state/
  cleanup/
    __init__.py
    scanner.py       # classifies candidate paths from snapshot + entity_history
    estimator.py     # computes expected space recovery
    executor.py      # applies deletions with pre-flight checks
    log.py           # records what was deleted and when
```

---

## 4. Multi-Turn Chat Sessions — `machine-state chat` persistence

**Today's `chat` command is stateless. Every invocation starts cold.**

This is fine for one-off questions but breaks conversational continuity.

### Proposed change

```text
machine-state chat
→ opens an interactive session (like a REPL)

  You: how is my RAM?
  Machine: You have 14.2 GB used out of 16 GB. Chrome is the top
           contributor at 4.1 GB. Pressure is currently elevated.

  You: what about yesterday?
  Machine: Yesterday at this time RAM usage was 11.8 GB. Chrome was
           still top, but at 2.9 GB. The 1.2 GB increase is consistent
           with the growth trend tracked over the past week.

  You: quit
```

### Implementation

* Session history stored in `~/.machine-state/sessions/` as plain JSON (not SQLite — ephemeral)
* Last N turns (configurable, default 10) injected into the LLM context
* `machine-state chat --new` forces a fresh session
* `machine-state chat --history` shows past sessions
* Session files are named by date and pruned after 30 days

### Why not SQLite for sessions?

Sessions are transient conversation context, not machine state. They don't need querying, migration, or schema. Plain JSON in a dedicated directory is correct here.

---

## 5. Per-App Impact Reports — `machine-state app-report`

**The entity_history layer has been tracking application behaviour for months. Surface it.**

```text
machine-state app-report "Chrome"

  Chrome — behavioural profile (last 90 days)

  Memory
    Average footprint      3.4 GB
    Peak observed          6.1 GB  (2024-03-14 09:22)
    Growth trend           +180 MB / week
    Pressure contribution  31% of all critical RAM events

  Runtime
    Sessions observed      214
    Avg session length     4h 12m
    Longest session        11h 40m

  Impact
    Starts with machine    yes (LoginItem)
    Causes pressure        frequently — 68 of 214 sessions
    Co-occurs with         Zoom (42%), Xcode (38%), Slack (87%)

  Recommendation
    Chrome is the top RAM contributor on this machine.
    Consider limiting open tabs or using a profile-per-task approach.
```

### Data sources

All from existing tables: `entity_snapshots`, `events`, `system_memory`, `health_scores` (Phase 9)

No new collection needed — only new aggregation and presentation logic.

---

## 6. Weekly Digest — automated, written to disk

**The scheduler runs continuously. It should produce a weekly summary.**

Every Monday at first startup after midnight, write a Markdown digest to `~/.machine-state/reports/YYYY-WW.md`.

### Digest contents

```markdown
# Machine State — Week 20, 2024

## Health
Average score: 71 / 100 (Elevated)
Worst day: Thursday (score 54 — sustained RAM pressure 3h)

## Storage
Net growth this week: +4.2 GB
Fastest-growing folder: ~/Downloads (+2.1 GB)
Projected full: ~18 days at current rate

## Memory pressure
Critical events: 7
Top contributor: Chrome (5 of 7 events)

## New applications observed
Figma (installed Tuesday, 1.1 GB)

## Cleanup opportunity
18.4 GB reclaimable — run `machine-state cleanup`
```

### Integration points

* Generated by a new `digest/generator.py` module
* Triggered from `scheduler/runner.py` at the weekly boundary
* Optionally surfaced via `machine-state notify` as a macOS notification
* CLI: `machine-state digest [--week YYYY-WW]` to view past digests

---

## 7. Custom Alert Rules — `~/.machine-state/alerts.toml`

**The notification system exists but is hardcoded.**

Let users define their own thresholds.

### Format

```toml
[[rule]]
name = "extended RAM pressure"
condition = "ram_pressure == 'critical' for 30m"
message = "RAM has been critical for 30 minutes. Top: {top_process}"
cooldown_minutes = 60

[[rule]]
name = "disk near full"
condition = "disk_free_gb < 20"
message = "Only {disk_free_gb} GB remaining on disk."
cooldown_minutes = 1440

[[rule]]
name = "runaway process"
condition = "process_ram_gb > 8 sustained 10m"
message = "{process_name} is using {ram_gb} GB RAM."
cooldown_minutes = 30
```

### Architecture

```text
alerts/
  __init__.py
  loader.py       # parse and validate alerts.toml
  evaluator.py    # check each rule against current snapshot
  dispatcher.py   # call into notifications/ on match
```

The evaluator runs inside the scheduler loop after each snapshot, same as the event detector.

Conditions are a small restricted DSL — not arbitrary Python — to keep evaluation deterministic and safe.

---

## 8. `machine-state diff` — Compare any two points in time

**Time-travel queries over the snapshot history.**

```text
machine-state diff --from "7 days ago" --to now

  Changes between 2024-03-13 14:30 and 2024-03-20 14:31:

  RAM
    Used:    12.8 GB → 14.2 GB   (+1.4 GB)
    Pressure: normal → elevated

  Disk
    Used:    295 GB → 312 GB   (+17 GB)
    Fastest growth: ~/Downloads (+8.4 GB)

  Processes
    New:   Figma, TablePlus
    Gone:  Android Studio

  Health score
    83 → 74  (↓ 9 pts)

  Events in window: 14 (3 critical, 8 elevated, 3 info)
```

A `diff.py` module already exists in the package — this extends it with a proper CLI and a richer output format.

---

# Suggested Build Order

| Order | Feature | Why first |
|---|---|---|
| 1 | Health Score | Unblocks dashboard + digest |
| 2 | Live TUI Dashboard | Highest user-visible impact |
| 3 | Smart Cleanup Engine | Most actionable single feature |
| 4 | `machine-state diff` | Low effort, high value, builds on existing `diff.py` |
| 5 | Weekly Digest | Scheduler already runs; just needs the generator |
| 6 | Per-App Reports | All data exists; new aggregation only |
| 7 | Multi-Turn Chat | Requires session management design |
| 8 | Custom Alert Rules | DSL design needs care to stay safe |

---

# New Modules

```text
machine_state/
  tui/
    __init__.py
    dashboard.py     # live ANSI dashboard renderer
    widgets.py       # pressure bar, process table, event feed
  cleanup/
    __init__.py
    scanner.py
    estimator.py
    executor.py
    log.py
  alerts/
    __init__.py
    loader.py
    evaluator.py
    dispatcher.py
  digest/
    __init__.py
    generator.py
    formatter.py
```

---

# New CLI Commands

| Command | Description |
|---|---|
| `machine-state dash` | Live TUI dashboard |
| `machine-state health` | Current health score + trend |
| `machine-state cleanup [--apply] [--dry-run]` | Cleanup plan and executor |
| `machine-state app-report <name>` | Per-app behavioural profile |
| `machine-state diff --from X --to Y` | Compare two points in time |
| `machine-state digest [--week YYYY-WW]` | View weekly digest |
| `machine-state chat` (extended) | Interactive multi-turn session |

---

# What Phase 9 Does NOT Include

* No cloud sync or remote state
* No embeddings or vector search
* No new snapshot domains — Phase 9 consumes existing data only
* No destructive automation — `cleanup --apply` requires explicit opt-in
* No new LLM providers — provider layer is complete

---

# End State

After Phase 9, the tool completes its arc:

| Phase | What the machine does |
|---|---|
| 1–4 | Watches |
| 5–6 | Understands |
| 7 | Talks |
| 8 | Predicts |
| **9** | **Acts and persists** |

A user who installs `machine-state` will:

* see their machine's health live in the terminal
* get a weekly digest every Monday without asking for it
* know exactly what to delete to recover 18 GB
* ask a follow-up question in `chat` that references what they said two minutes ago
* define their own alert for when Chrome goes rogue

All of it local. All of it deterministic. All of it theirs.
