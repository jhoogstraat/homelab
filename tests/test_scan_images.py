"""Keep the upstream Home Assistant acceptance separate from other scan failures."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/scan-images"
OFFICIAL_HA = "ghcr.io/home-assistant/home-assistant:2026.10.2@sha256:1edf9ce6c140826cdfcd6358802cf3466e38045cd7ed62ccf42c78980ff937ae"


class ImageSecurityPolicyTests(unittest.TestCase):
    def scan(self, app, image, severity="CRITICAL", error=False):
        report = {"Results": [{"Vulnerabilities": [{"Severity": severity}]}]}
        response = subprocess.CompletedProcess([], int(error), json.dumps(report), "scanner failed")
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                Path("quadlets").mkdir()
                Path(f"quadlets/{app}.container").write_text(f"[Container]\nImage={image}\n")
                with patch("sys.argv", [str(SCRIPT)]), \
                     patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}), \
                     patch("subprocess.run", return_value=response), redirect_stdout(StringIO()):
                    runpy.run_path(str(SCRIPT), run_name="__main__")
                return json.loads(Path("image-security.json").read_text())
            finally:
                os.chdir(previous)

    def test_official_homeassistant_is_still_scanned_and_findings_reported(self):
        records = self.scan("homeassistant", OFFICIAL_HA)
        self.assertTrue(records[0]["critical_findings_accepted"])
        self.assertEqual(records[0]["report"]["Results"][0]["Vulnerabilities"],
                         [{"Severity": "CRITICAL"}])

    def test_changed_digest_or_different_application_has_no_acceptance(self):
        for app, image in (("homeassistant", OFFICIAL_HA[:-1] + "f"),
                           ("matter", OFFICIAL_HA)):
            with self.subTest(app=app, image=image), self.assertRaises(SystemExit):
                self.scan(app, image)

    def test_accepted_image_scan_errors_still_block_publication(self):
        with self.assertRaises(SystemExit):
            self.scan("homeassistant", OFFICIAL_HA, error=True)

    def test_high_api_broker_findings_still_block_publication(self):
        with self.assertRaises(SystemExit):
            self.scan("socket-proxy", "ghcr.io/example/proxy@sha256:" + "a" * 64, "HIGH")

    def test_unpinned_homeassistant_still_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "Unpinned"):
            self.scan("homeassistant", "ghcr.io/home-assistant/home-assistant:stable")
