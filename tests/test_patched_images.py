import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "images/patch-node.py"


class NodeImagePatchTests(unittest.TestCase):
    def test_npm_metadata_is_not_copied_as_dependency_and_module_links_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "store/proxy-addr"
            target.mkdir(parents=True)
            package = target / "package.json"
            package.write_text('{"name":"proxy-addr","version":"2.0.7"}')
            link = root / "proxy-addr"
            link.symlink_to(target, target_is_directory=True)
            def install(args, **kwargs):
                modules = Path(args[args.index("--prefix") + 1]) / "node_modules"
                installed = modules / "proxy-addr"
                installed.mkdir(parents=True)
                (installed / "package.json").write_text('{"name":"proxy-addr","version":"2.0.8"}')
                dependency = modules / "dependency"
                dependency.mkdir()
                (dependency / "package.json").write_text('{"name":"dependency","version":"1.0.0"}')
                (modules / ".package-lock.json").write_text('{}')
                return subprocess.CompletedProcess(args, 0)
            def packages(path, pattern):
                return [package] if str(path) == "/app/node_modules" else []
            with patch.object(Path, "rglob", packages), patch("subprocess.run", install):
                runpy.run_path(str(SCRIPT), run_name="__main__")
            self.assertEqual(json.loads((link / "package.json").read_text())["version"], "2.0.8")
            self.assertTrue((link / "node_modules/dependency/package.json").is_file())
            self.assertFalse((link / "node_modules/.package-lock.json").exists())
