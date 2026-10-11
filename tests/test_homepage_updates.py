import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ghcr.io/jhoogstraat/homepage:latest"
DIGEST = "ghcr.io/jhoogstraat/homepage@sha256:" + "a" * 64


class HomepageUpdatesTests(unittest.TestCase):
    def test_homepage_follows_latest_and_enables_registry_updates(self):
        definition = (ROOT / "quadlets/homepage.container").read_text().splitlines()
        self.assertIn("Image=" + IMAGE, definition)
        self.assertIn("AutoUpdate=registry", definition)
        self.assertIn("User=bun", definition)

    def scan(self, name, definition, calls):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / name
            path.write_text(definition)
            def command(args, **kwargs):
                calls.append(args)
                output = json.dumps([{"RepoDigests": [DIGEST]}]) if args[1] == "image" else '{"Results": []}'
                return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")
            with patch("pathlib.Path.glob", return_value=[path]), patch("subprocess.run", side_effect=command), patch("sys.argv", ["scan-images", "--output", str(Path(directory) / "report.json")]):
                runpy.run_path(str(ROOT / "scripts/scan-images"), run_name="__main__")

    def test_scanner_resolves_homepage_before_scanning_exact_digest(self):
        calls = []
        self.scan("homepage.container", "[Container]\nImage=" + IMAGE + "\nAutoUpdate=registry\n", calls)
        self.assertEqual(calls[0], ["podman", "pull", "--arch", "arm64", IMAGE])
        self.assertEqual(calls[-1][-1], DIGEST)

    def test_scanner_still_rejects_other_unpinned_images(self):
        calls = []
        with self.assertRaisesRegex(RuntimeError, "Unpinned application image"):
            self.scan("other.container", "[Container]\nImage=example:latest\nAutoUpdate=registry\n", calls)
        self.assertEqual(calls, [])

    def test_scanner_requires_homepage_auto_update_opt_in(self):
        with self.assertRaisesRegex(RuntimeError, "Unpinned application image"):
            self.scan("homepage.container", "[Container]\nImage=" + IMAGE + "\n", [])
