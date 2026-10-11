#!/usr/bin/env python3
"""Replace every retained native esbuild copy without changing its API version."""
from pathlib import Path
import shutil
import subprocess

for binary in Path("/app/node_modules").rglob("esbuild"):
    if not binary.is_file():
        continue
    with binary.open("rb") as source:
        if source.read(4) != b"\x7fELF":
            continue
    version = subprocess.check_output([str(binary), "--version"], text=True).strip()
    replacement = Path("/tmp/esbuild") / version
    if not replacement.is_file():
        raise RuntimeError(f"Missing rebuilt esbuild {version}: {binary}")
    shutil.copyfile(replacement, binary)
    binary.chmod(0o755)
    print(f"Rebuilt {binary}: esbuild {version}", flush=True)
