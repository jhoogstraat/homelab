"""Linux/rootful smoke checks with isolated fixtures and no external networking."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid


def command(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


image = sys.argv[1]
name = "depanator-check-" + uuid.uuid4().hex[:8]
with tempfile.TemporaryDirectory(prefix=name) as temporary:
    root = Path(temporary)
    for directory in ("config", "data", "secrets"):
        (root / directory).mkdir(mode=0o700)
    (root / "config/config.json").write_text(json.dumps({
        "accountEmail": "fixture@example.com", "searchUrl": "https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-mieten",
        "preferences": "Fixture only", "persona": {"vorname": "Fixture", "nachname": "Only", "email": "fixture@example.com"},
        "notification": {"chatId": "123"}, "llm": {"backend": "codex"}, "dataDir": "/data",
    }))
    (root / "secrets/vnc-password").write_text("test1234")
    (root / "secrets/telegram-bot-token").write_text("123:offline-fixture")
    for path in root.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
    mapping = "Z,idmap=uids=@0-1000-1;gids=@0-1000-1"
    base = ["podman", "run", "--pull=never", "--network=none", "--userns=auto", "--user=1000:1000",
            "--shm-size=256m", "--stop-timeout=40",
            "-e", "VNC_PASSWORD_FILE=/run/secrets/vnc-password",
            "-e", "TELEGRAM_BOT_TOKEN_FILE=/run/secrets/telegram-bot-token",
            "-v", f"{root / 'config'}:/config:ro,{mapping}",
            "-v", f"{root / 'data'}:/data:{mapping}",
            "-v", f"{root / 'secrets'}:/run/secrets:ro,{mapping}"]
    command(*base, "--rm", "--entrypoint=bun", image, "-e",
            "const fs=require('fs'); fs.chmodSync('/data',448); fs.writeFileSync('/data/private','persisted',{mode:384}); fs.readFileSync('/config/config.json'); fs.readFileSync('/run/secrets/vnc-password');")
    command(*base, "--rm", "--entrypoint=bun", image, "-e",
            "if(require('fs').readFileSync('/data/private','utf8')!=='persisted')process.exit(1)")
    assert (root / "data/private").stat().st_uid == 0
    assert (root / "data/private").stat().st_mode & 0o777 == 0o600
    print("Verified cross-namespace private file access and host ownership", flush=True)
    try:
        command(*base, "-d", "--name", name, image, "start", stdout=subprocess.DEVNULL)
        probe = "const r=await fetch('http://127.0.0.1:6080/vnc.html',{signal:AbortSignal.timeout(2000)});if(!r.ok)process.exit(1)"
        for attempt in range(30):
            result = subprocess.run(["podman", "exec", name, "bun", "-e", probe],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Viewer did not become ready")
        details = json.loads(subprocess.check_output(["podman", "inspect", name]))[0]
        assert all("test1234" not in item and "offline-fixture" not in item for item in details["Config"]["Env"])
        started = time.monotonic()
        command("podman", "stop", "--time=40", name, stdout=subprocess.DEVNULL)
        details = json.loads(subprocess.check_output(["podman", "inspect", name]))[0]
        assert details["State"]["ExitCode"] == 0, details["State"]["ExitCode"]
        print(f"Verified viewer, private metadata and clean stop in {time.monotonic() - started:.2f}s", flush=True)
    finally:
        subprocess.run(["podman", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    marker = root / "data/reconciliation-required"
    marker.write_text("Fixture restore gate")
    result = subprocess.run([*base, "--rm", image, "start"], capture_output=True, text=True)
    assert result.returncode != 0 and "reconciliation required" in result.stderr.lower(), result.stderr
    print("Verified restore gate prevents agent startup", flush=True)
