# machine-state CLI — Command Reference

All commands are run as `python3 -m machine_state.cli <command>` or `machine-state <command>` if installed.

---

## Data Collection

```bash
# Take a snapshot of the current machine state
machine-state collect

# Include specific project folders
machine-state collect --project ~/Developer/my-app --project ~/Developer/other-app

# Full system scan (slower, more detail)
machine-state collect --full-system

# Tune how many processes / folder items are captured
machine-state collect --process-limit 20 --item-limit 15

# Tune full-system scan depth and item count
machine-state collect --full-system --system-item-limit 20 --system-max-depth 5
```

---

## Quick Tools (no DB required)

```bash
# RAM usage
machine-state tool ram

# Disk usage
machine-state tool disk

# Top processes
machine-state tool processes

# Largest items in a folder
machine-state tool largest-items --path ~/Downloads --limit 10 --max-depth 3

# Full system inventory
machine-state tool system-inventory

# Project folder summary
machine-state tool project --path ~/Developer/my-app
```

---

## Scheduler (background daemon)

```bash
# Start the background scheduler
machine-state scheduler start

# Start with custom collection tuning
machine-state scheduler start --process-limit 20 --item-limit 15 --system-item-limit 20

# Stop the scheduler
machine-state scheduler stop

# Check if the scheduler is running
machine-state scheduler status

# Show next scheduled collection times per domain
machine-state scheduler schedule

# Run one collection cycle manually
machine-state scheduler run-once
```

---

## Events

```bash
# Show recent detected events (RAM spikes, disk growth, runaway processes)
machine-state events

# Filter by domain
machine-state events --domain ram
machine-state events --domain disk
machine-state events --domain processes

# Filter by event type
machine-state events --type ram_spike

# Limit results
machine-state events --limit 20
```

---

## Pressure

```bash
# Show current live pressure state
machine-state pressure

# Use a wider snapshot window (default is 6)
machine-state pressure --window 12
```

---

## Entity History

```bash
# Show behavioral history for all tracked entities
machine-state entity-history

# Show history for a specific entity by ID
machine-state entity-history <entity_id>
```

---

## Long-term Memory

```bash
# Show all memory categories
machine-state memory

# Specific memory keys
machine-state memory heavy-apps
machine-state memory growing-folders
machine-state memory ram-spikes
machine-state memory cleanup
machine-state memory slowdowns

# Recompute all memory from stored snapshots
machine-state memory --rebuild
```

---

## Temporal Relations

```bash
# Show how entity relationships have evolved across snapshots
machine-state temporal-relations
```

---

## Notifications

```bash
# Evaluate state and send macOS notifications if thresholds are exceeded
machine-state notify

# Preview what would be sent without sending
machine-state notify --dry-run
```

---

## Semantic Layer (Phase 5)

```bash
# Full semantic machine picture
machine-state semantic summary

# Semantic pressure state (Healthy / Elevated / High / Critical)
machine-state semantic pressure

# Storage breakdown by category (Downloads, Caches, Trash, etc.)
machine-state semantic storage

# Semantic profile for a specific application
machine-state semantic app --name Chrome

# What can the machine handle?
machine-state semantic capability

# Check if a specific install size fits
machine-state semantic capability --install-size-gb 25

# Check feasibility for a known app (e.g. Xcode)
machine-state semantic capability --install-app xcode

# User activity patterns
machine-state semantic activity
```

---

## Planning Layer (Phase 6)

```bash
# List all registered tool contracts
machine-state plan tools

# Detect the intent behind a natural language query
machine-state plan detect "Why is my machine slow?"

# Build an execution plan for a query (without running it)
machine-state plan build "Can I install GTA 5?"

# Build and execute a plan, returning aggregated results
machine-state plan run "What is using the most memory?"
```

---

## Forecasting (Phase 8)

```bash
# Disk exhaustion forecast + folder growth hotspots
machine-state forecast disk

# Limit number of hotspot folders returned (default 5)
machine-state forecast disk --limit 10

# RAM trajectory prediction + recurring pressure windows
machine-state forecast ram

# Workload patterns + slowdown windows
machine-state forecast workload

# Risk score + app memory trends + proactive insights
machine-state forecast trends

# Limit number of app trends returned (default 5)
machine-state forecast trends --limit 10

# Simulate install impact (how much space remains, will it cause pressure)
machine-state forecast install --size-gb 20
```

---

## Conversational Chat (Phase 7)

```bash
# Ask a natural language question (uses Anthropic by default)
machine-state chat "Why is my machine slow?"
machine-state chat "What changed since yesterday?"
machine-state chat "Can I install Xcode right now?"
machine-state chat "What is consuming the most memory?"

# Use a different LLM provider
machine-state chat "How's my disk?" --provider openai
machine-state chat "How's my disk?" --provider gemini
machine-state chat "How's my disk?" --provider ollama --model llama3

# Show intent, provider, and token info after the response
machine-state chat "Why is my machine slow?" --verbose

# Output full JSON including context and token counts
machine-state chat "Why is my machine slow?" --raw
```

---

## Legacy Query Interface

```bash
# Query stored snapshots with a natural language-style key
machine-state ask "disk usage"
machine-state ask "top processes"

# Control how many historical snapshots are considered
machine-state ask "ram usage" --history-limit 20
```
