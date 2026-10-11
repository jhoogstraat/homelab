import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader("depanator", str(Path(__file__).resolve().parents[1] / "scripts/depanator"))
spec = importlib.util.spec_from_loader(loader.name, loader)
depanator = importlib.util.module_from_spec(spec)
loader.exec_module(depanator)


class SetupTests(unittest.TestCase):
    def test_setup_encrypts_credentials_and_keeps_only_chat_id_in_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wizard = root / "wizard"
            wizard.mkdir()
            (wizard / "config.json").write_text(json.dumps({"llm": {"backend": "codex"}}))
            (wizard / "secrets.env").write_text("TELEGRAM_BOT_TOKEN=123:private-token\nTELEGRAM_CHAT_ID=456\nVNC_PASSWORD=abcdefgh\n")
            with patch.object(depanator, "APP", root / "apps/depanator"), patch.object(depanator.homelab, "ROOT", root), patch.object(depanator.homelab, "command", return_value=subprocess.CompletedProcess([], 0, stdout=b"encrypted")) as encrypt, patch.object(depanator.homelab, "stage_secrets", return_value=root / "generation"), patch.object(depanator.homelab, "select_secrets"):
                depanator.provision(wizard)
                config = (root / "apps/depanator/config/config.json").read_text()
                self.assertNotIn("private-token", config)
                self.assertNotIn("abcdefgh", config)
                self.assertEqual(json.loads(config)["notification"]["chatId"], "456")
                self.assertEqual((root / "device-secrets/depanator.enc.env").read_bytes(), b"encrypted")
                self.assertIn(b"TELEGRAM_BOT_TOKEN=123:private-token", encrypt.call_args.kwargs["input"])
                self.assertNotIn("private-token", str(encrypt.call_args.args))
                self.assertEqual((root / "device-secrets").stat().st_mode & 0o777, 0o700)

    def test_encryption_failure_does_not_publish_config_or_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config.json").write_text('{"llm":{"backend":"codex"}}')
            (root / "secrets.env").write_text("TELEGRAM_BOT_TOKEN=123:token\nTELEGRAM_CHAT_ID=456\nVNC_PASSWORD=abcdefgh\n")
            with patch.object(depanator, "APP", root / "apps/depanator"), patch.object(depanator.homelab, "ROOT", root), patch.object(depanator.homelab, "command", side_effect=subprocess.CalledProcessError(1, "sops")):
                with self.assertRaises(subprocess.CalledProcessError):
                    depanator.provision(root)
            self.assertFalse((root / "apps/depanator/config/config.json").exists())
            self.assertFalse((root / "device-secrets/depanator.enc.env").exists())
