"""Exercise the actual loader, including literal values and child-process inheritance."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which("node"), "Node.js required for loader integration")
class SecretLoaderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.loader = self.root / "load-env.mjs"
        shutil.copyfile(Path(__file__).resolve().parents[1] / "configs/secret-loader.mjs", self.loader)
        self.environment = dict(os.environ)
        for name in ("NODE_OPTIONS", "HOMELAB_LOADER_PROBE"):
            self.environment.pop(name, None)

    def run_loader(self, content, code="", **environment):
        (self.root / "env.json").write_text(content)
        return subprocess.run([shutil.which("node"), "--import", str(self.loader), "-e", code],
                              env=dict(self.environment, **environment), capture_output=True, text=True)

    def test_exact_values_and_inherited_loader(self):
        value = "literal $ # ' \" \\ and\nnewline"
        code = 'if(process.env.HOMELAB_LOADER_PROBE!==JSON.parse(require("fs").readFileSync(process.argv[1])).HOMELAB_LOADER_PROBE)process.exit(2)'
        (self.root / "env.json").write_text(json.dumps({"HOMELAB_LOADER_PROBE": value}))
        result = subprocess.run([shutil.which("node"), "-e", code, str(self.root / "env.json")],
                                env=dict(self.environment, NODE_OPTIONS=f"--import={self.loader}"),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_loader(json.dumps({"HOMELAB_LOADER_PROBE": value}),
                                 HOMELAB_LOADER_PROBE=value)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_conflicts_and_malformed_json_fail_without_disclosing_values(self):
        cases = [(json.dumps({"HOMELAB_LOADER_PROBE": "private-value"}), {"HOMELAB_LOADER_PROBE": "other"}),
                 ('{"HOMELAB_LOADER_PROBE": private-value}', {}),
                 ('null', {}), ('[]', {}), ('{"BAD-NAME": "private-value"}', {}),
                 ('{"HOMELAB_LOADER_PROBE": 123}', {})]
        for content, environment in cases:
            with self.subTest(content=content):
                result = self.run_loader(content, **environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("private-value", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
