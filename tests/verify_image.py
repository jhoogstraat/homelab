"""Validate packaged Quadlets using their packaged generator, including dependencies."""
import re
import subprocess
import sys
from pathlib import Path

image = sys.argv[1]
subprocess.run(["podman", "run", "--rm", "-i", image, "sha256sum", "--check", "-"],
               input="51c45e77ddad91a19e96dc8fb75295b2087c279940df2634b23baf71b6dea42c  /usr/lib/firmware/brcm/BCM4345C0.hcd\n",
               text=True, check=True)
subprocess.run(["podman", "run", "--rm", image, "test", "-s",
                "/usr/share/licenses/rpi-bluez-firmware/LICENSE.cypress"], check=True)
subprocess.run(["podman", "run", "--rm", image, "firewall-offline-cmd", "--zone=public",
                "--query-interface=wpan0"], check=True)
subprocess.run(["podman", "run", "--rm", image, "firewall-offline-cmd", "--zone=public",
                "--query-forward"], check=True)
for flag in ([], ["-g"]):
    ranges = subprocess.check_output(["podman", "run", "--rm", image,
                                      "getsubids", *flag, "containers"], text=True)
    assert any(line.split()[2:] == ["2147483647", "2147483648"]
               for line in ranges.splitlines()), ranges
result = subprocess.run(["podman", "run", "--rm", image,
                         "/usr/lib/systemd/system-generators/podman-system-generator", "--dryrun"],
                        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if re.search(r"(error|failed|unsupported|unknown key)", result.stderr, re.I):
    raise RuntimeError(result.stderr)
units = {match[0]: match[1] for match in re.findall(r"---([^\n]+)---\n(.*?)(?=\n---|\Z)", result.stdout, re.S)}
expected = set()
for quadlet in Path("quadlets").glob("*"):
    if quadlet.suffix == ".container":
        name = quadlet.stem + ".service"
    elif quadlet.suffix == ".pod":
        name = quadlet.stem + "-pod.service"
    elif quadlet.suffix == ".network":
        name = quadlet.stem + "-network.service"
    else:
        continue
    expected.add(name)
    if name not in units:
        raise RuntimeError(f"Missing generated unit: {name}")
    if quadlet.suffix != ".network":
        assert any("homelab-prepare.service" in line.split("=", 1)[1].split() for line in units[name].splitlines() if line.startswith("Requires=")), name
        assert "PartOf=homelab.target" in units[name], name
assert not {"immobot.service", "onedev.service", "n8n.service", "grafana.service", "wg-easy.service", "couchdb.service"} & units.keys()
assert units.keys() == expected, units.keys() ^ expected
assert "--stop-timeout 60 " in units["homeassistant.service"]
assert "TimeoutStopSec=100" in units["homeassistant.service"]
assert "--stop-timeout 40 " in units["depanator.service"]
assert "TimeoutStopSec=60" in units["depanator.service"]
assert "--user 1000:1000" in units["depanator.service"]
assert "--publish" not in units["depanator.service"]
for alias in ("host.docker.internal", "host.containers.internal"):
    assert re.search(r"--add-host(?:=| )" + re.escape(alias + ":10.90.0.1"),
                     units["traefik.service"]), alias
for name in ("traefik.service", "beszel-agent.service"):
    assert "podman.sock" not in units[name], name
    assert "label=disable" not in units[name], name
    assert any("socket-proxy.service" in line.split("=", 1)[1].split()
               for line in units[name].splitlines() if line.startswith("Requires=")), name
assert "--internal" in units["podman-api-network.service"]
assert "--publish" not in units["socket-proxy.service"]
assert "--cap-drop all" in units["socket-proxy.service"]
assert "--read-only" in units["socket-proxy.service"]
for name in ("cloudflared", "vaultwarden", "beszel-agent", "glance", "papra", "homepage"):
    unit = units[name + ".service"]
    assert f"/run/homelab/secrets/current/{name}:/run/secrets:ro,Z" in unit, name
    assert not re.search(r"--env-file(?:=| )[^\s]*homelab/secrets", unit), name
assert "--token-file /run/secrets/tunnel-token" in units["cloudflared.service"]
assert "ADMIN_TOKEN_FILE=/run/secrets/admin-token" in units["vaultwarden.service"]
assert "/run/homelab/secrets/current/beszel-agent:/run/secrets:ro,Z,idmap" in units["beszel-agent.service"]
assert "--userns auto" in units["beszel-pod.service"]
assert "TOKEN_FILE=/run/secrets/token" in units["beszel-agent.service"]
assert "KEY_FILE=/run/secrets/key" in units["beszel-agent.service"]
assert "TELEGRAM_BOT_TOKEN_FILE=/run/secrets/bot-token" in units["depanator.service"]
assert "/var/lib/homelab/apps/depanator/config/bot-token:/run/secrets/bot-token:ro,Z,idmap" in units["depanator.service"]
assert "/var/lib/homelab/apps/depanator/data:/data:Z,idmap" in units["depanator.service"]
assert "--health-on-failure kill" in units["depanator.service"]
assert "VNC_PASSWORD" not in units["depanator.service"]
assert "NODE_OPTIONS=--import=/run/secrets/load-env.mjs" in units["papra.service"]
assert "bun --preload /run/secrets/load-env.mjs dist/server/entry.mjs" in units["homepage.service"]
assert "--user 1000:1000" in units["homepage.service"]
print(f"Validated {len(expected)} packaged Quadlet units")
subprocess.run(["podman", "run", "--rm", image, "/bin/bash", "-euc",
                "mkdir -p /tmp/units; /usr/lib/systemd/system-generators/podman-system-generator /tmp/units; "
                "SYSTEMD_UNIT_PATH=/tmp/units:/usr/lib/systemd/system systemd-analyze verify "
                "/tmp/units/*.service /usr/lib/systemd/system/homelab*.service "
                "/usr/lib/systemd/system/homelab.target /usr/lib/systemd/system/homelab*.timer "
                "/usr/lib/systemd/system/podman-auto-update.timer "
                "/usr/lib/systemd/system/bootc-fetch-apply-updates.timer "
                "/usr/lib/systemd/system/chrony-wait.service"], check=True)
