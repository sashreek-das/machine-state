"""Interactive first-run setup wizard."""

from __future__ import annotations

import json
import os
import select as _sel
import shutil
import subprocess
import sys
import termios
import threading
import time
import tty
import urllib.request
from typing import Any, Callable, TypeVar

from . import config

_T = TypeVar("_T")

# ── ANSI ──────────────────────────────────────────────────────────────────────
_R  = "\033[0m"
_B  = "\033[1m"
_D  = "\033[2m"
_CY = "\033[1;36m"
_GR = "\033[1;32m"

_BOX_W = 52

_PROVIDERS: list[tuple[str, str]] = [
    ("anthropic", "Anthropic  (Claude)            — API key required"),
    ("openai",    "OpenAI     (GPT)               — API key required"),
    ("gemini",    "Google     (Gemini)            — API key required"),
    ("ollama",    "Ollama     (local, no API key) — runs on your machine"),
]

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


# ── Low-level I/O ─────────────────────────────────────────────────────────────

def _w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def _print(text: str = "") -> None:
    print(f"  {text}")


def _div() -> None:
    print(f"  {_D}{'─' * _BOX_W}{_R}")


def _banner() -> None:
    l1 = "machine state  ·  setup"
    l2 = "local-first machine awareness for macOS"
    p1 = " " * (_BOX_W - 3 - len(l1))
    p2 = " " * (_BOX_W - 3 - len(l2))
    print()
    print(f"  ╭{'─' * _BOX_W}╮")
    print(f"  │{' ' * _BOX_W}│")
    print(f"  │   {_B}{l1}{_R}{p1}│")
    print(f"  │   {_D}{l2}{_R}{p2}│")
    print(f"  │{' ' * _BOX_W}│")
    print(f"  ╰{'─' * _BOX_W}╯")
    print()


def _ask(prompt: str, *, secret: bool = False) -> str:
    try:
        if secret:
            import getpass
            return getpass.getpass(f"\n  {prompt} ").strip()
        return input(f"\n  {prompt} ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\n  Setup cancelled.")
        sys.exit(0)


def _select(options: list[str], title: str) -> int:
    """Arrow-key selector. Returns 0-based index of chosen item."""
    selected = 0
    n = len(options)
    hint = f"  {_D}↑ ↓  move   ·   enter  select{_R}"
    total = n + 2  # option lines + blank line + hint line

    _w("\033[?25l")
    print(f"\n  {_B}{title}{_R}\n")

    def _render() -> None:
        for i, opt in enumerate(options):
            if i == selected:
                sys.stdout.write(f"  {_CY}›{_R} {_B}{opt}{_R}\n")
            else:
                sys.stdout.write(f"    {_D}{opt}{_R}\n")
        sys.stdout.write(f"\n{hint}\n")
        sys.stdout.flush()

    _render()

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    interrupted = False
    try:
        tty.setraw(fd)
        while True:
            b = os.read(fd, 1)
            if b == b'\x1b':
                ready, _, _ = _sel.select([fd], [], [], 0.05)
                if ready:
                    seq = os.read(fd, 2)
                    if seq == b'[A':
                        selected = (selected - 1) % n
                    elif seq == b'[B':
                        selected = (selected + 1) % n
            elif b in (b'\r', b'\n'):
                break
            elif b == b'\x03':
                interrupted = True
                break
            _w(f"\033[{total}A\033[J")
            _render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        _w("\033[?25h")

    _w(f"\033[{total}A\033[J")
    if interrupted:
        print("\n  Setup cancelled.\n")
        sys.exit(0)
    print(f"  {_GR}✓{_R}  {options[selected]}\n")
    return selected


def _spin(label: str, task: Callable[[], _T]) -> _T:
    """Run task in a thread while showing a braille spinner."""
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    result: list[_T] = []
    exc: list[BaseException] = []
    done = threading.Event()

    def _run() -> None:
        try:
            result.append(task())
        except BaseException as e:
            exc.append(e)
        finally:
            done.set()

    threading.Thread(target=_run, daemon=True).start()
    i = 0
    while not done.wait(0.08):
        _w(f"\r  {_D}{frames[i % len(frames)]}{_R}  {label}")
        i += 1
    _w("\r\033[K")
    if exc:
        raise exc[0]
    return result[0]


# ── Ollama helpers ────────────────────────────────────────────────────────────

def _ollama_running(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def _ollama_installed_models(base_url: str) -> list[str]:
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as r:
            body = json.loads(r.read().decode())
        return [m["name"] for m in body.get("models", [])]
    except (OSError, ValueError):
        return []


def _start_ollama(bin_path: str) -> bool:
    subprocess.Popen(
        [bin_path, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(10):
        time.sleep(0.5)
        if _ollama_running("http://localhost:11434"):
            return True
    return False


def _ollama_pick_model(base_url: str, installed: list[str]) -> str | None:
    catalogue_labels = [
        f"{name:<20} {size:<10} {desc}"
        for name, size, desc in _OLLAMA_CATALOGUE
    ]
    extras: list[str] = []
    if installed:
        extras.append("Use an already-installed model")
    extras.append("Enter a model name manually")

    choice = _select(catalogue_labels + extras, "Select a model:")

    if choice < len(_OLLAMA_CATALOGUE):
        return _OLLAMA_CATALOGUE[choice][0]
    if installed and choice == len(_OLLAMA_CATALOGUE):
        inst_choice = _select(installed, "Select installed model:")
        return installed[inst_choice]
    return _ask("Model name (e.g. llama3.2:3b):") or None


# ── Provider setup ────────────────────────────────────────────────────────────

def _setup_cloud(provider: str) -> int:
    env_var = _ENV_VAR[provider]
    _print(f"Paste your {_B}{env_var}{_R} below — input is hidden:")
    key = _ask("API key:", secret=True)
    if not key:
        _print("No key entered. Re-run `machine-state setup` when ready.")
        return 0

    _print(f"Model hint: {_D}{_MODEL_HINT[provider]}{_R}")
    model_raw = _ask("Model (leave blank for default):")
    cfg: dict[str, Any] = {"provider": provider, "api_key": key}
    if model_raw:
        cfg["model"] = model_raw

    config.save(cfg)
    print()
    _print(f"{_GR}✓{_R}  Saved. Try:  machine-state chat \"how is my RAM looking?\"")
    return 0


def _setup_ollama() -> int:
    bin_path = shutil.which("ollama")
    if not bin_path:
        _print(f"{_B}Ollama is not installed.{_R}")
        _print("  Install:  brew install ollama")
        _print("  Then:     machine-state setup")
        return 1

    _print(f"Found Ollama at {_D}{bin_path}{_R}")
    raw_url = _ask("Ollama server URL (enter for http://localhost:11434):")
    base_url = raw_url or "http://localhost:11434"

    if not _ollama_running(base_url):
        _print(f"Ollama is not running at {base_url}...")
        ok = _spin("Starting Ollama...", lambda: _start_ollama(bin_path))
        if not ok:
            _print("Could not start Ollama. Run `ollama serve` and re-run setup.")
            return 1

    _print(f"{_GR}✓{_R}  Ollama running at {base_url}")
    installed = _ollama_installed_models(base_url)
    if installed:
        _print(f"  Installed: {', '.join(installed)}")

    model = _ollama_pick_model(base_url, installed)
    if not model:
        _print("No model entered. Re-run `machine-state setup` when ready.")
        return 0

    if model in installed:
        _print(f"{_GR}✓{_R}  {model} is already installed.")
    else:
        _print(f"Downloading {_B}{model}{_R} — this may take a few minutes...")
        result = subprocess.run([bin_path, "pull", model], check=False)
        if result.returncode != 0:
            _print("Download failed. Check the model name and try again.")
            return 1
        _print(f"{_GR}✓{_R}  {model} is ready.")

    config.save({"provider": "ollama", "model": model, "ollama_base_url": base_url})
    _print(f"{_GR}✓{_R}  Saved. Try:  machine-state chat \"how is my RAM looking?\"")
    return 0


# ── Post-config steps ─────────────────────────────────────────────────────────

def _has_snapshots() -> bool:
    try:
        from . import store
        return len(store.get_recent_snapshots(limit=1)) > 0
    except (ImportError, RuntimeError, OSError):
        return False


def _initial_collection(bin_path: str) -> bool:
    result = subprocess.run(
        [bin_path, "collect", "--full-system",
         "--system-max-depth", "4", "--system-item-limit", "25"],
        capture_output=True,
    )
    return result.returncode == 0


def _start_scheduler(bin_path: str) -> str:
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

    _banner()
    _print("This wizard configures the LLM provider used by `machine-state chat`.")
    _print(f"Your API key is stored only in {_D}~/.machine-state/config.json{_R}.")
    print()

    cfg = config.load()
    if cfg:
        current = cfg.get("provider", "?")
        model = cfg.get("model", "")
        label = current + (f" / {model}" if model else "")
        _print(f"Current provider: {_B}{label}{_R}")
        print()

    provider_labels = [label for _, label in _PROVIDERS] + ["Skip — configure later"]
    choice = _select(provider_labels, "Choose an LLM provider:")

    if choice < len(_PROVIDERS):
        _div()
        print()
        provider_name = _PROVIDERS[choice][0]
        if provider_name == "ollama":
            _setup_ollama()
        else:
            _setup_cloud(provider_name)
        print()

    _div()
    print()

    if _has_snapshots():
        _print(f"{_GR}✓{_R}  Existing snapshots found — skipping initial collection.")
    else:
        _print("Taking an initial snapshot of your machine...")
        ok = _spin(
            "Collecting RAM, disk, processes, and applications...",
            lambda: _initial_collection(bin_path),
        )
        if ok:
            _print(f"{_GR}✓{_R}  Snapshot complete.")
        else:
            _print("Snapshot failed — run `machine-state collect --full-system` manually.")

    print()
    status = _spin("Starting background scheduler...", lambda: _start_scheduler(bin_path))
    if status == "started":
        _print(f"{_GR}✓{_R}  Scheduler running. Snapshots collected automatically.")
    elif status == "already_running":
        _print(f"{_GR}✓{_R}  Scheduler is already running.")
    else:
        _print("Could not start scheduler — run `machine-state scheduler start` manually.")

    print()
    _div()
    print()
    _print(f"{_B}Setup complete.{_R}  The scheduler starts automatically on every login.")
    _print(f"Run  {_CY}machine-state chat{_R}  to ask about your machine.")
    print()
    return 0
