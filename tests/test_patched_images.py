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


class EsbuildImagePatchTests(unittest.TestCase):
    def test_all_native_copies_are_replaced_and_javascript_wrapper_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / 'native/esbuild'
            alias = root / 'wrapper/esbuild'
            javascript = root / 'javascript/esbuild'
            for path in (native, alias, javascript):
                path.parent.mkdir()
            native.write_bytes(b'\x7fELFvulnerable')
            alias.hardlink_to(native)
            javascript.write_text('#!/usr/bin/env node')
            replacement = root / '0.18.20'
            replacement.write_bytes(b'\x7fELFpatched')
            original_is_file = Path.is_file
            original_copyfile = __import__('shutil').copyfile
            def copyfile(source, target):
                return original_copyfile(replacement, target)
            with patch.object(Path, 'rglob', return_value=[native, alias, javascript]), \
                 patch.object(Path, 'is_file', lambda p: True if str(p) == '/tmp/esbuild/0.18.20' else original_is_file(p)), \
                 patch('subprocess.check_output', return_value='0.18.20\n'), \
                 patch('shutil.copyfile', copyfile):
                runpy.run_path(str(SCRIPT.with_name('patch-esbuild.py')), run_name='__main__')
            self.assertEqual(native.read_bytes(), replacement.read_bytes())
            self.assertEqual(alias.read_bytes(), replacement.read_bytes())
            self.assertEqual(javascript.read_text(), '#!/usr/bin/env node')
            self.assertEqual(native.stat().st_mode & 0o777, 0o755)
