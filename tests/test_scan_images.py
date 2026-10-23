"""One scan policy for every Quadlet image: block only what a change makes worse."""
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
OLD = "ghcr.io/example/app:1@sha256:" + "a" * 64
NEW = "ghcr.io/example/app:2@sha256:" + "b" * 64
CVE1 = {"VulnerabilityID": "CVE-1", "Severity": "CRITICAL"}
CVE2 = {"VulnerabilityID": "CVE-2", "Severity": "CRITICAL", "FixedVersion": "2"}


class ImageSecurityPolicyTests(unittest.TestCase):
    def scan(self, image, baseline=None, findings=None, error=False):
        """Run the scanner on one Quadlet; baseline is the published pin (None: new app).
        findings maps an image to the vulnerabilities Trivy reports for it."""
        findings = findings or {}

        def run(args, **kwargs):
            if args[0] == "git" and "show" in args:
                out, code = (f"[Container]\nImage={baseline}\n", 0) if baseline else ("", 128)
            elif args[0] == "git":
                out, code = "", 0
            else:
                report = {"Results": [{"Vulnerabilities": findings.get(args[-1])}]}
                out, code = json.dumps(report), int(error)
            return subprocess.CompletedProcess(args, code, out, "scanner failed")

        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                Path("quadlets/nested").mkdir(parents=True)
                Path("quadlets/nested/app.container").write_text(f"[Container]\nImage={image}\n")
                with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": "", "SCAN_BASELINE": "abc"}), \
                     patch("subprocess.run", side_effect=run), redirect_stdout(StringIO()):
                    try:
                        runpy.run_path(str(SCRIPT), run_name="__main__")
                        blocked = False
                    except SystemExit:
                        blocked = True
                return blocked, json.loads(Path("image-security.json").read_text())
            finally:
                os.chdir(previous)

    def test_deployed_image_never_blocks(self):
        blocked, records = self.scan(OLD, baseline=OLD, findings={OLD: [CVE1, CVE2]})
        self.assertFalse(blocked)
        self.assertEqual(records[0]["blocking"], [])

    def test_repin_blocks_only_new_criticals(self):
        blocked, records = self.scan(NEW, baseline=OLD, findings={OLD: [CVE1], NEW: [CVE1, CVE2]})
        self.assertTrue(blocked)
        self.assertEqual(records[0]["blocking"], ["CVE-2"])
        self.assertFalse(self.scan(NEW, baseline=OLD, findings={OLD: [CVE1, CVE2], NEW: [CVE1]})[0])

    def test_new_app_blocks_on_any_critical(self):
        self.assertTrue(self.scan(NEW, findings={NEW: [CVE1]})[0])
        high = {"VulnerabilityID": "CVE-3", "Severity": "HIGH", "FixedVersion": "2"}
        self.assertFalse(self.scan(NEW, findings={NEW: [high]})[0])

    def test_scan_errors_and_unpinned_images_block(self):
        self.assertTrue(self.scan(OLD, baseline=OLD, error=True)[0])
        self.assertTrue(self.scan("ghcr.io/example/app:latest")[0])


if __name__ == "__main__":
    unittest.main()
