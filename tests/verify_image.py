"""Validate packaged Quadlets using their packaged generator, including dependencies."""
import re
import subprocess
import sys
from pathlib import Path

image = sys.argv[1]
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
assert not {"immobot.service", "onedev.service", "n8n.service", "grafana.service", "wg-easy.service"} & units.keys()
assert units.keys() == expected, units.keys() ^ expected
print(f"Validated {len(expected)} packaged Quadlet units")
subprocess.run(["podman", "run", "--rm", image, "/bin/bash", "-euc",
                "mkdir -p /tmp/units; /usr/lib/systemd/system-generators/podman-system-generator /tmp/units; "
                "SYSTEMD_UNIT_PATH=/tmp/units:/usr/lib/systemd/system systemd-analyze verify "
                "/tmp/units/*.service /usr/lib/systemd/system/homelab*.service /usr/lib/systemd/system/homelab.target"], check=True)
