import contextlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/homelab"
loader = importlib.machinery.SourceFileLoader("homelab", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
homelab = importlib.util.module_from_spec(spec)
loader.exec_module(homelab)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.state, self.source, self.quadlets, self.run = [root / name for name in
                                                          ("state", "source", "quadlets", "run")]
        self.patch = patch.multiple(homelab, ROOT=self.state, SOURCE=self.source,
                                    QUADLETS=self.quadlets, RUN=self.run)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        for directory in (self.source / "environment/traefik", self.source / "defaults/glance",
                          self.source / "defaults/adguard",
                          self.source / "secrets", self.quadlets, self.run,
                          self.state / "apps", self.state / "credentials"):
            directory.mkdir(parents=True)
        (self.quadlets / "glance.container").write_text("[Container]\nImage=example:latest\n")
        (self.source / "defaults/glance/glance.yml").write_text("seed")
        (self.source / "environment/traefik/traefik.yml").write_text("first release")
        (self.source / "secrets/glance.enc.env").write_text("ciphertext")
        (self.source / "secrets/adguard.enc.env").write_text("ciphertext")
        (self.source / "defaults/adguard/AdGuardHome.yaml").write_text(
            "users:\n  - name: ${ADGUARD_USERNAME}\n    password: ${ADGUARD_PASSWORD_HASH}\n")
        key = self.state / "credentials/age.key"
        key.write_text("test key")
        key.chmod(0o600)
        self.calls = []

    def fake_command(self, *args, **kwargs):
        self.calls.append(args)
        output = b""
        if args[0] == "sops":
            output = b"TOKEN=secret\n"
            if "json" in args:
                output = json.dumps({"ADGUARD_USERNAME": "test-user",
                                     "ADGUARD_PASSWORD_HASH": "$2a$10$" + "a" * 53}).encode()
        elif args[:2] == ("podman", "ps"):
            output = b"[]"
        elif args[:3] == ("podman", "auto-update", "--dry-run"):
            output = b'[{"Updated":"pending"}]'
        return subprocess.CompletedProcess(args, 0, stdout=output)

    def active(self, args, **kwargs):
        return subprocess.CompletedProcess(args, 0 if args[-1] == "glance.service" else 3)

    def test_redeploy_preserves_device_config_but_updates_host_config(self):
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
            config = self.state / "apps/glance/config/glance.yml"
            config.write_text("device edits")
            (self.source / "defaults/glance/glance.yml").write_text("new seed")
            (self.source / "environment/traefik/traefik.yml").write_text("new routing")
            homelab.prepare()
        self.assertEqual(config.read_text(), "device edits")
        self.assertEqual((self.state / "environment/traefik/traefik.yml").read_text(), "new routing")
        self.assertEqual((self.state / "secrets/glance.env").read_text(), "TOKEN=secret\n")
        self.assertEqual((self.state / "secrets/glance.env").stat().st_mode & 0o777, 0o600)

    def test_failed_secret_rotation_keeps_complete_previous_set(self):
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
        previous = (self.state / "secrets").readlink()
        (self.source / "secrets/glance.enc.env").write_text("rotated ciphertext")
        with patch.object(homelab, "command", side_effect=subprocess.CalledProcessError(1, "sops")):
            with self.assertRaises(subprocess.CalledProcessError):
                homelab.prepare()
        self.assertEqual((self.state / "secrets").readlink(), previous)

    @unittest.skipUnless(os.geteuid() == 0, "Root required for container file ownership")
    def test_couchdb_deployment_config_keeps_service_ownership_after_rotation(self):
        source = self.source / "environment/couchdb/10-initalize-secure.ini"
        source.parent.mkdir()
        source.write_text("[couchdb]\nsingle_node = true\n")
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
            source.write_text("[couchdb]\nsingle_node = true\nmax_document_size = 50000000\n")
            homelab.prepare()
        deployed = self.state / source.relative_to(self.source)
        self.assertEqual(deployed.read_text(), source.read_text())
        self.assertEqual((deployed.stat().st_uid, deployed.stat().st_gid), (5984, 5984))
        self.assertEqual(deployed.stat().st_mode & 0o777, 0o644)
        self.assertEqual((self.state / "secrets/glance.env").read_text(), "TOKEN=secret\n")

    def test_unreachable_repository_never_stops_applications(self):
        with patch.object(homelab, "command", side_effect=subprocess.CalledProcessError(1, "restic")):
            with self.assertRaises(subprocess.CalledProcessError):
                homelab.backup()
        self.assertFalse((self.run / "paused-units.json").exists())

    def test_recovery_inventory_ignores_image_less_pod_infrastructure(self):
        def inventory(*args, **kwargs):
            result = self.fake_command(*args, **kwargs)
            if args[:2] == ("podman", "ps"):
                result.stdout = json.dumps([
                    {"Names": ["beszel-infra"], "ImageID": "", "Image": "", "IsInfra": True},
                    {"Names": ["beszel-ui"], "ImageID": "sha256:app", "Image": "beszel:latest", "IsInfra": False},
                ]).encode()
            elif args[:3] == ("podman", "image", "inspect"):
                self.assertEqual(args[3], "sha256:app")
                result.stdout = json.dumps([{"Id": "sha256:app", "RepoDigests": ["beszel@sha256:app"]}]).encode()
            return result
        with patch.object(homelab, "command", inventory):
            homelab.capture_recovery(["beszel-pod.service", "beszel-ui.service"])
        records = json.loads((self.state / "recovery/images.json").read_text())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["names"], ["beszel-ui"])
        self.assertEqual(records[0]["digests"], ["beszel@sha256:app"])

    def test_backup_failure_restarts_only_previously_running_apps(self):
        def fail_upload(*args, **kwargs):
            result = self.fake_command(*args, **kwargs)
            if args[:2] == ("restic", "backup"):
                raise subprocess.CalledProcessError(1, args)
            return result
        with patch.object(homelab, "command", fail_upload), patch.object(homelab.subprocess, "run", self.active):
            with self.assertRaises(subprocess.CalledProcessError):
                homelab.update_apps()
        self.assertIn(("systemctl", "stop", "glance.service"), self.calls)
        self.assertIn(("systemctl", "start", "glance.service"), self.calls)
        self.assertNotIn(("podman", "auto-update"), self.calls)
        self.assertFalse(any(call[:2] == ("restic", "forget") for call in self.calls))
        self.assertFalse((self.run / "paused-units.json").exists())

    def test_update_without_new_images_does_not_interrupt_apps(self):
        with patch.object(homelab, "command", return_value=subprocess.CompletedProcess([], 0, stdout=b"[]")):
            homelab.update_apps()
        self.assertFalse((self.run / "paused-units.json").exists())

    def test_backup_happens_between_stop_and_start_and_before_update(self):
        with patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", self.active):
            homelab.update_apps()
        stop = self.calls.index(("systemctl", "stop", "glance.service"))
        backup = next(i for i, call in enumerate(self.calls) if call[:2] == ("restic", "backup"))
        start = self.calls.index(("systemctl", "start", "glance.service"))
        update = self.calls.index(("podman", "auto-update"))
        self.assertLess(stop, backup)
        self.assertLess(backup, start)
        self.assertLess(start, update)

    def test_recovery_after_killed_backup_is_repeatable(self):
        (self.run / "paused-units.json").write_text(json.dumps(["glance.service"]))
        with patch.object(homelab, "command", self.fake_command):
            homelab.resume()
            homelab.resume()
        self.assertEqual(self.calls, [("systemctl", "start", "glance.service")])

    def test_retired_app_is_quiesced_when_it_still_runs(self):
        for name in homelab.RETIRED:
            with self.subTest(app=name):
                self.calls.clear()
                def retired_active(args, **kwargs):
                    return subprocess.CompletedProcess(args, 0 if args[-1] == name + ".service" else 3)
                with patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", retired_active):
                    homelab.pause()
                    homelab.resume()
                self.assertEqual(self.calls, [("systemctl", "stop", name + ".service"),
                                             ("systemctl", "start", name + ".service")])


    def test_no_autoupdate_records_does_not_interrupt_apps(self):
        with patch.object(homelab, "command", return_value=subprocess.CompletedProcess([], 0, stdout=b"")):
            homelab.update_apps()
        self.assertFalse((self.run / "paused-units.json").exists())

    def test_retirement_preserves_unrelated_override_and_archives_known_units(self):
        legacy = Path(self.directory.name) / "legacy"
        legacy.mkdir()
        (legacy / "glance.container").write_text("old deployment")
        for name in homelab.RETIRED:
            (legacy / (name + ".container")).write_text("old " + name)
        (legacy / "other.container").write_text("unrelated")
        (self.state / "apps/glance").mkdir()
        with patch.object(homelab, "LEGACY_QUADLETS", legacy), patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", self.active):
            homelab.retire_legacy()
        self.assertEqual((legacy / "other.container").read_text(), "unrelated")
        self.assertFalse((legacy / "glance.container").exists())
        for name in homelab.RETIRED:
            self.assertFalse((legacy / (name + ".container")).exists())
            self.assertEqual((self.state / "recovery/legacy-quadlets" / (name + ".container")).read_text(), "old " + name)
        self.assertNotIn(("systemctl", "start", "glance.service"), self.calls)

    @unittest.skipUnless(sys.platform == "linux" and shutil.which("rsync"), "Linux rsync required for migration")
    def test_migration_preserves_old_state_and_leaves_writers_stopped(self):
        legacy = Path(self.directory.name) / "legacy"
        old_data, old_config, old_secrets = [legacy / name for name in ("data", "config", "secrets")]
        for directory in (old_data / "homeassistant", old_data / "beszel/data", old_data / "beszel/agent",
                          old_data / "papra/data", old_data / "papra/ingestion", old_config / "glance", old_secrets,
                          old_data / "onedev/site", old_data / "n8n", old_config / "onedev", old_config / "n8n",
                          old_data / "grafana", old_config / "grafana",
                          old_data / "wg-easy", old_config / "wg-easy"):
            directory.mkdir(parents=True)
            (directory / ".state").write_bytes(b"preserve hidden state")
        (old_config / "glance/glance.yml").write_text("device preference")
        (old_data / "homeassistant/configuration.yaml").write_text("existing HA config")
        (old_data / "n8n/config").write_text('{"encryptionKey":"test-key"}')
        for name in ("homeassistant", "beszel-ui", "beszel-agent", "papra"):
            (self.quadlets / (name + ".container")).write_text("[Container]\n")
        real_run = subprocess.run

        def run(args, **kwargs):
            if args[0] == "rsync":
                return real_run(args, **kwargs)
            if args[:3] == ["podman", "container", "exists"]:
                return subprocess.CompletedProcess(args, 0)
            if tuple(args[:2]) == ("podman", "commit"):
                self.calls.append(tuple(args))
                return subprocess.CompletedProcess(args, 0, stdout=b"sha256:test-image\n")
            if tuple(args[:2]) == ("podman", "save"):
                Path(args[args.index("--output") + 1]).write_bytes(b"archived writable layer")
            if args[0] == "systemctl" and "is-active" in args:
                if args[-1] in ("n8n.service", "onedev.service", "grafana.service", "wg-easy.service"):
                    return subprocess.CompletedProcess(args, 0)
                return self.active(args, **kwargs)
            self.calls.append(tuple(args))
            return subprocess.CompletedProcess(args, 0)

        with patch.object(homelab.subprocess, "run", run):
            homelab.migrate(old_data, old_config, old_secrets)
        self.assertEqual((self.state / "apps/homeassistant/config/configuration.yaml").read_text(), "existing HA config")
        self.assertEqual((self.state / "apps/glance/config/glance.yml").read_text(), "device preference")
        for name, folder in (("beszel-ui", "data"), ("beszel-agent", "data"), ("papra", "ingestion")):
            self.assertEqual((self.state / "apps" / name / folder / ".state").read_bytes(), b"preserve hidden state")
        self.assertTrue((old_data / "homeassistant/configuration.yaml").exists())
        self.assertTrue((self.run / "paused-units.json").exists())
        self.assertNotIn(("systemctl", "start", "glance.service"), self.calls)
        archive = self.state / "apps/_retired/immobot/legacy-image.tar"
        self.assertEqual(archive.read_bytes(), b"archived writable layer")
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        self.assertLess(self.calls.index(("podman", "commit", "--pause=true", "--quiet", "immobot")), self.calls.index(("systemctl", "stop", "glance.service", "grafana.service", "n8n.service", "onedev.service", "wg-easy.service")))
        for app in ("onedev", "n8n", "grafana", "wg-easy"):
            retired = self.state / "apps/_retired" / app
            self.assertEqual((retired / "config/.state").read_bytes(), b"preserve hidden state")
            self.assertEqual(retired.stat().st_mode & 0o777, 0o700)
            self.assertFalse((self.state / "apps" / app).exists())
        self.assertEqual((self.state / "apps/_retired/onedev/data/site/.state").read_bytes(), b"preserve hidden state")
        self.assertEqual((self.state / "apps/_retired/n8n/data/config").read_text(), '{"encryptionKey":"test-key"}')
        self.assertTrue((old_data / "onedev/site/.state").exists())
        self.assertTrue((old_data / "n8n/config").exists())
        with self.assertRaises(RuntimeError):
            homelab.migrate(old_data, old_config, old_secrets)

    @unittest.skipUnless(shutil.which("restic"), "restic required for real backup/restore")
    def test_real_restic_restore_recovers_database_attachment_and_credentials(self):
        data = self.state / "apps/glance/data"
        data.mkdir(parents=True)
        database = data / "app.db"
        with contextlib.closing(sqlite3.connect(database)) as connection:
            connection.execute("create table settings (value text)")
            connection.execute("insert into settings values ('device preference')")
            connection.commit()
        attachment = data / "attachment.bin"
        attachment.write_bytes(bytes(range(256)) * 4)
        (self.state / "recovery").mkdir()
        repository = str(Path(self.directory.name) / "repository")
        real_run = subprocess.run
        real_command = homelab.command

        def run(*args, **kwargs):
            if args[0][0] == "systemctl":
                self.calls.append(tuple(args[0]))
                return self.active(args[0], **kwargs) if "is-active" in args[0] else subprocess.CompletedProcess(args[0], 0)
            return real_run(*args, **kwargs)

        with patch.dict(os.environ, RESTIC_REPOSITORY=repository, RESTIC_PASSWORD="test-only-password", RESTIC_CACHE_DIR=str(Path(self.directory.name) / "cache")), patch.object(homelab.subprocess, "run", run), patch.object(homelab, "capture_recovery"), patch.object(homelab, "device_sources", return_value=[]):
            real_command("restic", "init", stdout=subprocess.DEVNULL)
            homelab.backup()
            attachment.unlink()
            database.unlink()
            restored = Path(self.directory.name) / "restored"
            real_command("restic", "restore", "latest", "--target", str(restored), stdout=subprocess.DEVNULL)
            real_command("restic", "check", "--read-data", stdout=subprocess.DEVNULL)
        restored_data = restored / data.relative_to(data.anchor)
        self.assertEqual((restored_data / "attachment.bin").read_bytes(), bytes(range(256)) * 4)
        with contextlib.closing(sqlite3.connect(restored_data / "app.db")) as connection:
            self.assertEqual(connection.execute("pragma integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("select value from settings").fetchone()[0], "device preference")
        restored_key = restored / (self.state / "credentials/age.key").relative_to(self.state.anchor)
        self.assertEqual(restored_key.read_text(), "test key")
        self.assertEqual(restored_key.stat().st_mode & 0o777, 0o600)
        self.assertIn(("systemctl", "stop", "glance.service"), self.calls)
        self.assertIn(("systemctl", "start", "glance.service"), self.calls)


if __name__ == "__main__":
    unittest.main()
