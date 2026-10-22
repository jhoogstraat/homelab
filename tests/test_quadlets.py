import re
import unittest
from pathlib import Path

QUADLETS = Path(__file__).resolve().parents[1] / "quadlets"


class HomelabNetworkTest(unittest.TestCase):
    def test_homelab_members_pin_unique_addresses(self):
        # A dynamic lease can take another unit's static address if it starts first.
        seen = {}
        for path in sorted(p for p in QUADLETS.iterdir() if p.suffix in (".container", ".pod")):
            for line in path.read_text().splitlines():
                if line.startswith("Network=homelab.network"):
                    match = re.fullmatch(r"Network=homelab\.network:ip=(10\.90\.0\.\d+)", line)
                    self.assertIsNotNone(match, f"{path.name} must pin an address")
                    self.assertNotIn(match[1], seen, f"{path.name} reuses {seen.get(match[1])}'s address")
                    seen[match[1]] = path.name
        self.assertIn("traefik.container", seen.values())


if __name__ == "__main__":
    unittest.main()
