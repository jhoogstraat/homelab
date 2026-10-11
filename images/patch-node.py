#!/usr/bin/env python3
"""Replace vulnerable npm packages with published fixes, preserving module paths."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

fixed = {"tar": "7.5.19", "proxy-addr": "2.0.8", "seroval": "1.6.2", "shell-quote": "1.11.0"}
roots = [Path("/app/node_modules"), Path("/usr/local/lib/node_modules")]
packages = []
for root in roots:
    for path in root.rglob("package.json"):
        try:
            package = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if package.get("name") in fixed and package.get("version") != fixed[package["name"]]:
            packages.append((path.parent, package["name"]))
for target, name in packages:
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(["npm", "install", "--prefix", directory, "--ignore-scripts", "--no-audit", "--no-fund", name + "@" + fixed[name]], check=True)
        modules = Path(directory) / "node_modules"
        installed = modules / name
        shutil.rmtree(target)
        shutil.copytree(installed, target, symlinks=True)
        # Dependencies stay nested, so existing pnpm/npm links keep resolving.
        for dependency in modules.iterdir():
            if not dependency.is_dir() or dependency.name == ".bin" or dependency == installed:
                continue
            if name.startswith("@") and dependency.name == name.split("/")[0]:
                continue
            shutil.copytree(dependency, target / "node_modules" / dependency.name, symlinks=True, dirs_exist_ok=True)
        print(f"Patched {target}: {name}@{fixed[name]}", flush=True)
