# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for machine-state.
# Build: pyinstaller machine_state.spec
# Output: dist/machine-state  (single self-contained binary)

import os
from pathlib import Path

prompts_dir = Path("machine_state/llm/prompts")
prompt_datas = [
    (str(f), "machine_state/llm/prompts")
    for f in prompts_dir.glob("*.txt")
]

a = Analysis(
    ["machine_state/cli/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=prompt_datas,
    hiddenimports=[
        # Subpackages that are imported dynamically (lazy imports inside functions)
        "machine_state.llm.providers.anthropic",
        "machine_state.llm.providers.openai",
        "machine_state.llm.providers.gemini",
        "machine_state.llm.providers.ollama",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # These are only needed if the user opts into the chat command.
        # Excluding them keeps the binary lean; users who need them install
        # the Python package instead (pip install machine-state-model[anthropic]).
        "anthropic",
        "openai",
        "google.generativeai",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="machine-state",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,   # inherit from the build machine (arm64 or x86_64)
    codesign_identity=None,
    entitlements_file=None,
)
