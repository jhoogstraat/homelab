"""One scan policy for every Quadlet image, with no per-application exceptions."""
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
PINNED = "ghcr.io/example/app:1@sha256:" + "a" * 64


class ImageSecurityPolicyTests(unittest.TestCase):
    def scan(self, image=PINNED, vulnerability=None, error=False):
        report = {"Results": [{"Vulnerabilities": [vulnerability] if vulnerability else None}]}
        response = subprocess.CompletedProcess([], int(error), json.dumps(report), "scanner failed")
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                Path("quadlets/nested").mkdir(parents=True)
                Path("quadlets/nested/app.container").write_text(f"[Container]\nImage={image}\n")
                with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}), \
                     patch("subprocess.run", return_value=response), redirect_stdout(StringIO()):
                    try:
                        runpy.run_path(str(SCRIPT), run_name="__main__")
                        blocked = False
                    except SystemExit:
                        blocked = True
                return blocked, json.loads(Path("image-security.json").read_text())
            finally:
                os.chdir(previous)

    def test_fixable_critical_blocks(self):
        blocked, records = self.scan(vulnerability={
            "VulnerabilityID": "CVE-1", "Severity": "CRITICAL", "FixedVersion": "2"})
        self.assertTrue(blocked)
        self.assertEqual(records[0]["blocking"], ["CVE-1"])

    def test_unfixed_critical_and_high_are_reported_only(self):
        for vulnerability in ({"VulnerabilityID": "CVE-2", "Severity": "CRITICAL"},
                              {"VulnerabilityID": "CVE-3", "Severity": "HIGH", "FixedVersion": "2"}):
            with self.subTest(vulnerability=vulnerability):
                blocked, records = self.scan(vulnerability=vulnerability)
                self.assertFalse(blocked)
                self.assertEqual(records[0]["report"]["Results"][0]["Vulnerabilities"],
                                 [vulnerability])

    def test_scan_errors_and_unpinned_images_block(self):
        self.assertTrue(self.scan(error=True)[0])
        self.assertTrue(self.scan(image="ghcr.io/example/app:latest")[0])


if __name__ == "__main__":
    unittest.main()
