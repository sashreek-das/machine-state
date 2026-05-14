"""Interactive first-run setup wizard.

Guides the user through choosing an LLM provider, entering an API key (for
cloud providers), or downloading an Ollama model (for local inference).

Writes the result to ~/.machine-state/config.json via machine_state.config.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from . import config

_DIVIDER = "─" * 54

_PROVIDERS: list[tuple[str, str]] = [
    ("anthropic", "Anthropic  (Claude)            — API key required"),
    ("openai",    "OpenAI     (GPT)               — API key required"),
    ("gemini",    "Google     (Gemini)            — API key required"),
    ("ollama",    "Ollama     (local, no API key) — runs on your machine"),
]

# Curated list of models that work well on Mac.
# (name, approx_size, description)
_OLLAMA_CATALOGUE: list[tuple[str, str, str]] = [
    ("qwen3:8b",    "~5.2 GB", "fast, strong reasoning        (recommended)"),
    ("llama3.2:3b", "~2.0 GB", "smallest, fastest responses"),
    ("llama3.1:8b", "~4.7 GB", "balanced quality / speed"),
    ("mistral:7b",  "~4.1 GB", "good instruction following"),
    ("phi4",        "~9.1 GB", "Microsoft — high quality, needs more RAM"),
    ("gemma3:4b",   "~3.3 GB", "Google — lightweight"),
]

_ENV_VAR: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai":    "OPENAI_API_KEY",
    "gemini":    "GOOGLE_API_KEY",
}

_MODEL_HINT: dict[str, str] = {
    "anthropic": "e.g. claude-sonnet-4-6  (leave blank for default)",
    "openai":    "e.g. gpt-4o             (leave blank for default)",
    "gemini":    "e.g. gemini-2.0-flash   (leave blank for default)",
}


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _print(text: str = "") -> None:
    print(f"  {text}")


def _ask(prompt: str) -> str:
    try:
        return input(f"\n  {prompt} ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\n  Setup cancelled.")
        sys.exit(0)


def _menu(options: list[str], prompt: str = "Enter number") -> int:
    """Numbered menu. Returns 0-based index of chosen item."""
    print()
    for i, opt in enumerate(options, 1):
        _print(f"{i})  {opt}")
    while True:
        raw = _ask(f"{prompt}:")
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        _print(f"Please enter a number between 1 and {len(options)}.")


# ── Ollama helpers ────────────────────────────────────────────────────────────

def _ollama_running(base_url: str = "http://localhost:11434") -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _ollama_installed_models(base_url: str = "http://localhost:11434") -> list[str]:
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as r:
            body = json.loads(r.read().decode())
        return [m["name"] for m in body.get("models", [])]
    except Exception:
        return []


def _start_ollama(bin_path: str) -> bool:
    """Try to start `ollama serve` in the background. Returns True if it comes up."""
    subprocess.Popen(
        [bin_path, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(10):
        time.sleep(0.5)
        if _ollama_running():
            return True
    return False


# ── Provider-specific setup ───────────────────────────────────────────────────

def _setup_cloud(provider: str) -> int:
    env_var = _ENV_VAR[provider]
    _print(f"\nPaste your {env_var}:")
    key = _ask("API key:")
    if not key:
        _print("No key entered. Re-run `machine-state setup` when ready.")
        return 0

    model_raw = _ask(f"Model ({_MODEL_HINT[provider]}):")
    cfg: dict[str, Any] = {"provider": provider, "api_key": key}
    if model_raw:
        cfg["model"] = model_raw

    config.save(cfg)
    _print()
    _print("Saved. Try it with:  machine-state chat \"how is my RAM looking?\"")
    return 0


def _setup_ollama() -> int:
    bin_path = shutil.which("ollama")
    if not bin_path:
        _print()
        _print("Ollama is not installed.")
        _print("Install it with:  brew install ollama")
        _print("Then re-run:      machine-state setup")
        return 1

    _print(f"\nFound Ollama at {bin_path}")

    if not _ollama_running():
        _print("Ollama is not running — starting it now...")
        if not _start_ollama(bin_path):
            _print("Could not start Ollama automatically.")
            _print("Run `ollama serve` in another terminal, then re-run setup.")
            return 1

    _print("Ollama is running.")

    installed = _ollama_installed_models()
    if installed:
        _print(f"\nInstalled models: {', '.join(installed)}")

    # Build model menu
    catalogue_labels = [
        f"{name:<20} {size:<10} {desc}"
        for name, size, desc in _OLLAMA_CATALOGUE
    ]
    extra_labels: list[str] = []
    if installed:
        extra_labels.append("Use an already-installed model")
    extra_labels.append("Enter a model name manually")

    _print("\nSelect a model to use:")
    choice = _menu(catalogue_labels + extra_labels)

    if choice < len(_OLLAMA_CATALOGUE):
        model = _OLLAMA_CATALOGUE[choice][0]
    elif installed and choice == len(_OLLAMA_CATALOGUE):
        # "Use already-installed"
        inst_choice = _menu(installed, "Select model")
        model = installed[inst_choice]
    else:
        model = _ask("Model name (e.g. llama3.2:3b):")
        if not model:
            _print("No model entered. Re-run `machine-state setup` when ready.")
            return 0

    if model in installed:
        _print(f"\n{model} is already installed.")
    else:
        _print(f"\nDownloading {model} — this may take a few minutes...")
        result = subprocess.run([bin_path, "pull", model], check=False)
        if result.returncode != 0:
            _print(f"\nDownload failed. Check the model name and try again.")
            return 1
        _print(f"\n{model} is ready.")

    config.save({"provider": "ollama", "model": model})
    _print()
    _print("Saved. Try it with:  machine-state chat \"how is my RAM looking?\"")
    _print()
    _print("Note: Ollama must be running for `chat` to work. Keep `ollama serve`")
    _print("      running, or install the Ollama Mac app for automatic startup.")
    return 0


# ── Post-config steps ─────────────────────────────────────────────────────────

def _has_snapshots() -> bool:
    try:
        from . import store
        return len(store.get_recent_snapshots(limit=1)) > 0
    except Exception:
        return False


def _initial_collection(bin_path: str) -> bool:
    """Run a full system snapshot; returns True on success."""
    result = subprocess.run(
        [bin_path, "collect", "--full-system",
         "--system-max-depth", "4", "--system-item-limit", "25"],
        capture_output=True,
    )
    return result.returncode == 0


def _start_scheduler(bin_path: str) -> str:
    """Start the background scheduler. Returns 'started', 'already_running', or 'failed'."""
    result = subprocess.run(
        [bin_path, "scheduler", "start"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "failed"
    if "already_running" in result.stdout:
        return "already_running"
    return "started"


# ── Entry point ───────────────────────────────────────────────────────────────

def run_setup() -> int:
    bin_path = shutil.which("machine-state") or sys.argv[0]

    print()
    _print("machine-state  •  setup")
    _print(_DIVIDER)
    _print()
    _print("This wizard configures the LLM provider used by `machine-state chat`.")
    _print("Your API key (if any) is stored only in ~/.machine-state/config.json.")

    cfg = config.load()
    if cfg:
        current = cfg.get("provider", "?")
        model = cfg.get("model", "")
        label = f"{current}" + (f" / {model}" if model else "")
        _print(f"\nCurrent provider: {label}")

    provider_labels = [label for _, label in _PROVIDERS] + ["Skip — configure later"]
    _print("\nChoose an LLM provider:")
    choice = _menu(provider_labels)

    if choice == len(_PROVIDERS):
        _print()
        _print("Skipped. Re-run `machine-state setup` whenever you are ready.")
    else:
        provider_name = _PROVIDERS[choice][0]
        if provider_name == "ollama":
            _setup_ollama()
        else:
            _setup_cloud(provider_name)

    # ── Initial snapshot ───────────────────────────────────────────────────────
    print()
    _print(_DIVIDER)
    _print()
    if _has_snapshots():
        _print("Existing snapshots found — skipping initial collection.")
    else:
        _print("Taking an initial snapshot of your machine...")
        _print("(Collects RAM, disk, processes, and installed applications.)")
        if _initial_collection(bin_path):
            _print("Snapshot complete.")
        else:
            _print("Snapshot failed — run `machine-state collect --full-system` manually.")

    # ── Start scheduler ────────────────────────────────────────────────────────
    print()
    _print("Starting background scheduler...")
    status = _start_scheduler(bin_path)
    if status == "started":
        _print("Scheduler running. It will collect snapshots automatically.")
    elif status == "already_running":
        _print("Scheduler is already running.")
    else:
        _print("Could not start scheduler automatically.")
        _print("Run `machine-state scheduler start` when ready.")

    print()
    _print(_DIVIDER)
    _print()
    _print("Setup complete. The scheduler starts automatically on every login.")
    _print("Run `machine-state chat \"<question>\"` to ask about your machine.")
    print()
    return 0
