# Machine State Model MVP

Local-first deterministic machine state model with snapshot storage, query routing, and Phase 3 temporal analysis:

- Collect OS-level machine data
- Build structured snapshots
- Store snapshots in SQLite
- Query the latest stored snapshot via CLI
- Analyze trends, causal signals, relationships, and forecasts over stored history

## Requirements

- Python 3.10+
- Node.js and npm only for the `npm run ...` wrappers

## CLI

Collect a snapshot:

```bash
npm run collect -- --project "$PWD"
```

Collect a broader system snapshot with top-level filesystem inventory:

```bash
npm run collect -- --full-system
```

Tune recursive system indexing depth when needed:

```bash
npm run collect -- --full-system --system-max-depth 4
```

Ask a question against the latest stored snapshot:

```bash
npm run ask -- "How much disk space do I have?"
```

Ask time-aware questions using stored history:

```bash
npm run ask -- "How has RAM usage changed over time?"
npm run ask -- "Why is RAM usage high?"
npm run ask -- "Which folders are growing over time?"
npm run ask -- "When will disk be full?"
```

Example deterministic query outputs now return:

- `singleAnswer`
- `supportingEvidence`
- `domain`
- `operation`

Examples:

```bash
npm run ask -- "What percent of disk is used?"
npm run ask -- "Which process is using the most memory?"
npm run ask -- "Show top 5 contributors in the project"
```

Run an individual inspection tool:

```bash
npm run tool -- ram
npm run tool -- largest-items --path "$PWD"
npm run tool -- system-inventory --path /
```

## Notes

- Queries only read the latest stored snapshot.
- The query layer is deterministic and keyword-based.
- Intent is mapped to simple operations such as `max`, `top_n`, `remaining`, and `percent_used`.
- No live system scan happens during `ask`.
- Phase 3 history answers read a configurable stored history window via `--history-limit`.
- `--full-system` adds a recursive directory index rooted at `/` with safe exclusions for volatile/system-managed paths.
- The default `--system-max-depth 4` is intended to capture folders like `/Users/<name>/Developer` and the immediate projects inside it.
