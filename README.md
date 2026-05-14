# machine-state

A local-first machine awareness daemon for macOS. Collects OS-level snapshots on a background schedule, detects system events, tracks behavioral history, and answers natural language questions about your machine — entirely on-device, with no cloud dependency.

---

## What it does

- **Continuous monitoring** — background scheduler collects RAM, disk, processes, and filesystem state on a tiered interval (5 min / 15 min / 60 min)
- **Event detection** — detects RAM spikes, disk pressure, runaway processes, and folder explosions as they happen
- **Predictive intelligence** — forecasts disk exhaustion, RAM saturation, workload patterns, and install impact from historical trends
- **Natural language chat** — ask questions in plain English; the LLM selects the right tools, runs them against real data, and explains what it found
- **Works fully local** — pair with Ollama and nothing ever leaves your machine

---

## Installation

```bash
brew tap sashreek-das/machine-state
brew install machine-state
```

The installer creates `~/.machine-state/`, installs a LaunchAgent, and starts the scheduler automatically on every login.

---

## Setup

Run the interactive setup wizard once after installing:

```bash
machine-state setup
```

The wizard:
1. Lets you choose an LLM provider (Ollama, Anthropic, OpenAI, or Gemini)
2. For Ollama: checks/starts the server, lists models, and downloads your choice
3. For cloud providers: reads your API key from the environment or prompts for it
4. Takes an initial full-system snapshot
5. Starts the background scheduler

Configuration is saved to `~/.machine-state/config.json`.

---

## Usage

### Ask a question

```bash
machine-state chat "how is my RAM looking"
machine-state chat "why does my mac feel slow"
machine-state chat "when will my disk run out"
machine-state chat "can I install Xcode"
machine-state chat "which app is using the most memory"
machine-state chat "is it safe to restart right now"
```

The `--verbose` flag shows intent, provider, and token count:

```bash
machine-state chat "what should I be worried about" --verbose
```

### Check current state

```bash
machine-state pressure              # live RAM and disk pressure state
machine-state events                # recent detected events
machine-state events --domain ram   # filter by domain
machine-state memory heavy-apps     # apps consistently using high memory
machine-state memory growing-folders
machine-state memory cleanup        # storage cleanup candidates
```

### Forecasting

```bash
machine-state forecast disk         # days until disk fills, growth hotspots
machine-state forecast ram          # RAM trajectory, saturation estimate
machine-state forecast workload     # slowdown windows, risk level
machine-state forecast trends       # overall risk score + proactive insights
machine-state forecast install --size-gb 50   # simulate installing a 50 GB app
```

### Scheduler

```bash
machine-state scheduler status
machine-state scheduler stop
machine-state scheduler start
machine-state scheduler run-once    # immediate one-shot collection
```

### Manual data collection

```bash
machine-state collect
machine-state collect --project ~/Developer --project ~/Downloads
machine-state collect --full-system --system-max-depth 4
```

### Semantic analysis

```bash
machine-state semantic summary
machine-state semantic pressure
machine-state semantic storage
machine-state semantic app --name "Chrome"
machine-state semantic capability --install-size-gb 15
machine-state semantic activity
```

### Entity history

```bash
machine-state entity-history                    # list all tracked entities
machine-state entity-history application:Xcode  # history for a specific app
```

### Planner (debug / exploration)

```bash
machine-state plan tools                        # list all 17 registered tool contracts
machine-state plan detect "why is my mac slow"  # show detected intent
machine-state plan run "how much free disk do I have"
```

---

## How it works

```
scheduler (background)
  └── incremental collector (domain-aware: ram/proc 5min, disk/projects 15min, inventory 60min)
       └── SQLite snapshot store
            ├── event detector  (7 rule-based event types)
            ├── entity history  (per-app, per-folder behavioral profiles)
            └── system memory   (rebuilt every N collections)

machine-state chat "<query>"
  └── LLM call 1: tool selection
       └── select from 17 registered tools, validate args against contracts
            └── execute plan against SQLite data (deterministic)
                 └── LLM call 2: explain results in natural language
```

The runtime (snapshot, store, pressure, events, forecasting) is fully deterministic — no LLM involvement, no network calls, reproducible output for identical inputs. The LLM layer only touches sanitized structured data, never raw snapshots or system files.

---

## LLM providers

| Provider | Default model | Requires |
|---|---|---|
| Ollama | qwen3:8b | Ollama installed locally |
| Anthropic | claude-sonnet-4-6 | `ANTHROPIC_API_KEY` |
| OpenAI | gpt-4o-mini | `OPENAI_API_KEY` |
| Google Gemini | gemini-2.0-flash | `GOOGLE_API_KEY` |

Override per-query with `--provider` and `--model`.

---

## Detected events

| Event | Trigger |
|---|---|
| `ram_spike` | RAM grew ≥15% between snapshots |
| `ram_pressure_critical` | RAM usage ≥95% |
| `disk_pressure_critical` | Disk usage ≥95% |
| `disk_folder_growth` | Folder grew ≥100 MB |
| `disk_cache_explosion` | Folder grew ≥500 MB |
| `process_runaway` | Single process using ≥40% of total RAM |
| `application_memory_spike` | App grew ≥50 MB between snapshots |

---

## Storage

All data lives in `~/.machine-state/`:

| File | Purpose |
|---|---|
| `machine-state.db` | SQLite — snapshots, events, entity history, system memory |
| `config.json` | LLM provider and model configuration |
| `scheduler.pid` | Daemon PID (managed automatically) |
| `scheduler.log` | Scheduler loop output |

---

## Requirements

- macOS (Apple Silicon)
- Python 3.10+ (bundled in the binary — no separate install needed)
- For Ollama: `brew install ollama`
