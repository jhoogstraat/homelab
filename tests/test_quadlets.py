import re
import unittest
from pathlib import Path

QUADLETS = Path(__file__).resolve().parents[1] / "quadlets"


class HomelabNetworkTest(unittest.TestCase):
    def test_network_members_pin_unique_addresses(self):
        # A dynamic lease can take another unit's static address if it starts first.
        networks = {
            "homelab.network": (r"Network=homelab\.network:ip=(10\.90\.0\.\d+)", {}),
            "public.network": (r"Network=public\.network:ip=(10\.92\.0\.\d+)", {}),
        }
        for path in sorted(p for p in QUADLETS.iterdir() if p.suffix in (".container", ".pod")):
            for line in path.read_text().splitlines():
                for net, (pattern, seen) in networks.items():
                    if line.startswith(f"Network={net}"):
                        match = re.fullmatch(pattern, line)
                        self.assertIsNotNone(match, f"{path.name} must pin an address on {net}")
                        self.assertNotIn(match[1], seen, f"{path.name} reuses {seen.get(match[1])}'s address")
                        seen[match[1]] = path.name
        for net, (_, seen) in networks.items():
            self.assertIn("traefik.container", seen.values(), f"traefik must join {net}")
        self.assertNotIn("podman-api.network", (QUADLETS / "beszel-ui.container").read_text())


if __name__ == "__main__":
    unittest.main()
