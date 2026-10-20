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
        environment = patch.dict(os.environ, {})
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("CREDENTIALS_DIRECTORY", None)
        for directory in (self.source / "environment/traefik", self.source / "defaults/glance",
                          self.source / "defaults/adguard",
                          self.source / "secrets", self.quadlets, self.run,
                          self.state / "apps", self.state / "credentials"):
            directory.mkdir(parents=True)
        (self.quadlets / "glance.container").write_text("[Container]\nImage=example:latest\n")
        (self.source / "defaults/glance/glance.yml").write_text("seed")
        (self.source / "environment/traefik/traefik.yml").write_text("first release")
        self.secret_values = {
            name: {key: "secret" for key in keys} for name, keys in homelab.SECRET_KEYS.items()
        }
        self.secret_values["adguard"].update(ADGUARD_USERNAME="test-user",
                                            ADGUARD_PASSWORD_HASH="$2a$10$" + "a" * 53)
        for name in homelab.SECRET_KEYS:
            (self.source / f"secrets/{name}.enc.env").write_text("ciphertext")
        (self.source / "secret-loader.mjs").write_bytes(
            (SCRIPT.parent.parent / "configs/secret-loader.mjs").read_bytes())
        (self.source / "defaults/adguard/AdGuardHome.yaml").write_text(
            "users:\n  - name: ${ADGUARD_USERNAME}\n    password: ${ADGUARD_PASSWORD_HASH}\n")
        key = self.state / "credentials/age.key"
        key.write_text("test key")
        key.chmod(0o600)
        key.parent.chmod(0o700)
        for name, value in (("backup.env", "RESTIC_REPOSITORY=test"),
                            ("restic-password", "test-only-password"),
                            ("s3-credentials", "[default]\naws_access_key_id = dummy\naws_secret_access_key = dummy\n")):
            path = key.parent / name
            path.write_text(value)
            path.chmod(0o600)
        self.calls = []

    def fake_command(self, *args, **kwargs):
        self.calls.append(args)
        output = b""
        if args[0] == "sops":
            name = Path(args[-1]).name.removesuffix(".enc.env")
            output = json.dumps(self.secret_values[name]).encode()
        elif args[:2] == ("podman", "ps"):
            output = b"" if "{{.ID}}" in args else b"[]"
        elif args[:3] == ("podman", "auto-update", "--dry-run"):
            output = b'[{"Updated":"pending"}]'
        elif args[:2] == ("systemctl", "show"):
            output = b"\n\n".join([b"ActiveState=inactive\nResult=success"] * len(args[4:]))
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
        self.assertEqual((self.run / "secrets/current/glance/adguard-password").read_text(), "secret")
        self.assertEqual((self.run / "secrets/current/glance/adguard-password").stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.state / "secrets").exists())

    def test_failed_secret_rotation_keeps_complete_previous_set(self):
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
        previous = (self.run / "secrets/current").readlink()
        (self.source / "secrets/cloudflared.enc.env").write_text("rotated ciphertext")
        with patch.object(homelab, "command", side_effect=subprocess.CalledProcessError(1, "sops")):
            with self.assertRaises(subprocess.CalledProcessError):
                homelab.prepare()
        self.assertEqual((self.run / "secrets/current").readlink(), previous)

    def test_optional_device_secrets_are_validated_staged_and_backed_up(self):
        device = self.state / "device-secrets/depanator.enc.env"
        device.parent.mkdir(mode=0o700)
        device.write_text("ciphertext")
        device.chmod(0o600)
        self.secret_values["depanator"] = {"TELEGRAM_BOT_TOKEN": "123:test", "VNC_PASSWORD": "12345678"}
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
            token = self.run / "secrets/current/depanator/telegram-bot-token"
            self.assertEqual(token.read_text(), "123:test")
            self.assertEqual(token.stat().st_mode & 0o777, 0o600)
            self.assertIn(str(device.parent), homelab.device_sources())
            previous = (self.run / "secrets/current").readlink()
            device.write_text("changed ciphertext")
            self.secret_values["depanator"]["VNC_PASSWORD"] = "too-short"
            with self.assertRaisesRegex(RuntimeError, "Depanator secrets"):
                homelab.prepare()
            self.assertEqual((self.run / "secrets/current").readlink(), previous)

    def test_absent_optional_secrets_preserve_existing_inventory_and_exposed_inputs_fail(self):
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
            self.assertFalse((self.run / "secrets/current/depanator").exists())
            device = self.state / "device-secrets/depanator.enc.env"
            device.parent.mkdir(mode=0o700)
            device.write_text("ciphertext")
            device.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "credential"):
                homelab.prepare()

    def test_dangling_device_secret_symlinks_are_rejected(self):
        device = self.state / "device-secrets/depanator.enc.env"
        device.parent.mkdir(mode=0o700)
        device.symlink_to(device.parent / "absent")
        with patch.object(homelab, "command", self.fake_command):
            with self.assertRaisesRegex(RuntimeError, "credential"):
                homelab.prepare()

    def test_device_quadlets_join_maintenance_without_duplicate_units(self):
        legacy = Path(self.directory.name) / "device-quadlets"
        legacy.mkdir()
        for name in ("depanator", "glance"):
            (legacy / f"{name}.container").write_text("[Container]\n")
        with patch.object(homelab, "LEGACY_QUADLETS", legacy):
            self.assertIn("depanator.service", homelab.units())
            self.assertEqual(homelab.units().count("glance.service"), 1)

    def test_prepare_closes_existing_state_directory_permissions(self):
        (self.state / "apps").chmod(0o755)
        (self.state / "credentials").chmod(0o755)
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
        for path in (self.state / "apps", self.state / "credentials", self.run / "secrets/generations"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    def test_incomplete_restic_snapshot_blocks_pruning_and_update(self):
        def partial_upload(*args, **kwargs):
            result = self.fake_command(*args, **kwargs)
            if args[:2] == ("restic", "backup"):
                raise subprocess.CalledProcessError(3, args)
            return result
        with patch.object(homelab, "command", partial_upload), patch.object(homelab.subprocess, "run", self.active):
            with self.assertRaises(subprocess.CalledProcessError):
                homelab.update_apps()
        self.assertIn(("systemctl", "start", "glance.service"), self.calls)
        self.assertNotIn(("podman", "auto-update"), self.calls)
        self.assertFalse(any(call[:2] == ("restic", "forget") for call in self.calls))

    def test_prepare_rejects_exposed_age_key_before_decryption(self):
        (self.state / "credentials/age.key").chmod(0o644)
        with patch.object(homelab, "command", self.fake_command):
            with self.assertRaisesRegex(RuntimeError, "root-only credential"):
                homelab.prepare()
        self.assertFalse(any(call[0] == "sops" for call in self.calls))

    def test_service_credentials_do_not_fall_back_when_missing(self):
        directory = self.run / "credentials"
        directory.mkdir(mode=0o700)
        with patch.dict(os.environ, CREDENTIALS_DIRECTORY=str(directory)), patch.object(homelab, "command", self.fake_command):
            with self.assertRaisesRegex(RuntimeError, "credential"):
                homelab.prepare()
        self.assertFalse(any(call[0] == "sops" for call in self.calls))

    def test_symlink_age_identity_is_rejected(self):
        key = self.state / "credentials/age.key"
        key.rename(key.with_suffix(".backup"))
        key.symlink_to(key.with_suffix(".backup"))
        with self.assertRaisesRegex(RuntimeError, "credential"):
            homelab.credential("age.key")

    def test_invalid_secret_entries_do_not_publish_or_expose_values(self):
        for bad in (None, {"TUNNEL_TOKEN": "secret", "UNKNOWN": "private-value"},
                    {"TUNNEL_TOKEN": ""}, {"TUNNEL_TOKEN": 123},
                    {"TUNNEL_TOKEN": "private-value\ud800"}):
            with self.subTest(bad=bad), patch.object(homelab, "command", self.fake_command):
                self.secret_values["cloudflared"] = bad
                with self.assertRaisesRegex(RuntimeError, "Invalid secret entries for cloudflared") as error:
                    homelab.prepare()
                self.assertNotIn("private-value", str(error.exception))
                self.assertFalse((self.run / "secrets/current").exists())

    def test_bad_seed_cannot_switch_existing_secret_generation(self):
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
            previous = (self.run / "secrets/current").readlink()
            (self.source / "secrets/adguard.enc.env").write_text("new")
            self.secret_values["adguard"]["ADGUARD_PASSWORD_HASH"] = "not-bcrypt"
            with self.assertRaisesRegex(RuntimeError, "bcrypt"):
                homelab.prepare()
        self.assertEqual((self.run / "secrets/current").readlink(), previous)

    def test_loader_changes_build_a_fresh_generation_and_incomplete_sets_fail(self):
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
            previous = (self.run / "secrets/current").readlink()
            with (self.source / "secret-loader.mjs").open("a") as output:
                output.write("\n// changed delivery\n")
            homelab.prepare()
            self.assertNotEqual((self.run / "secrets/current").readlink(), previous)
            (self.run / "secrets/current/homepage/env.json").unlink()
            with self.assertRaisesRegex(RuntimeError, "credential"):
                homelab.prepare()

    def test_glance_placeholder_migration_preserves_includes_and_adguard_state(self):
        glance = self.state / "apps/glance/config"
        glance.mkdir(parents=True)
        includes = glance / "includes"
        includes.mkdir()
        content = b"# preference\nusername: ${ADGUARD_USERNAME}\npassword: ${ADGUARD_PASSWORD}\ntitle: Mine\n"
        (includes / "dns.yml").write_bytes(content)
        adguard = self.state / "apps/adguard/config/AdGuardHome.yaml"
        adguard.parent.mkdir(parents=True)
        adguard.write_text("device-owned users")
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
        self.assertEqual((includes / "dns.yml").read_bytes(), content.replace(
            b"${ADGUARD_USERNAME}", b"${secret:adguard-username}").replace(
            b"${ADGUARD_PASSWORD}", b"${secret:adguard-password}"))
        self.assertEqual(adguard.read_text(), "device-owned users")
        self.assertFalse((self.run / "secrets/current/glance/adguard-password-hash").exists())

    def test_rotation_restarts_only_active_units_and_retains_previous(self):
        with patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", self.active):
            homelab.prepare()
            previous = (self.run / "secrets/current").resolve()
            (self.source / "secrets/cloudflared.enc.env").write_text("new")
            self.calls.clear()
            homelab.rotate_secrets()
        self.assertNotEqual((self.run / "secrets/current").resolve(), previous)
        self.assertTrue(previous.exists())
        self.assertEqual([call for call in self.calls if call[:2] in (("systemctl", "stop"), ("systemctl", "start"))],
                         [("systemctl", "stop", "glance.service"), ("systemctl", "start", "glance.service")])
        self.assertIsNone(homelab.paused_units())

    def test_failed_rotation_readiness_recreates_old_set(self):
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
        previous = (self.run / "secrets/current").resolve()
        (self.source / "secrets/cloudflared.enc.env").write_text("new")
        with patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", self.active), patch.object(homelab, "wait_ready", side_effect=[RuntimeError("Not ready"), None]):
            with self.assertRaisesRegex(RuntimeError, "Not ready"):
                homelab.rotate_secrets()
        self.assertEqual((self.run / "secrets/current").resolve(), previous)
        self.assertEqual(self.calls.count(("systemctl", "stop", "glance.service")), 2)
        self.assertEqual(self.calls.count(("systemctl", "start", "glance.service")), 2)
        self.assertIsNone(homelab.paused_units())

    def test_failed_rotation_recovery_keeps_durable_intent(self):
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
        previous = (self.run / "secrets/current").resolve()
        (self.source / "secrets/cloudflared.enc.env").write_text("new")
        with patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", self.active), patch.object(homelab, "wait_ready", side_effect=RuntimeError("Not ready")):
            with self.assertRaises(RuntimeError):
                homelab.rotate_secrets()
        self.assertEqual((self.run / "secrets/current").resolve(), previous)
        self.assertEqual(homelab.paused_units(), ["glance.service"])

    def test_noop_rotation_does_not_stop_apps_and_previous_intent_blocks_rotation(self):
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
            self.calls.clear()
            homelab.rotate_secrets()
            self.assertFalse(any(call[:2] == ("systemctl", "stop") for call in self.calls))
            homelab.save_paused_units(["glance.service"])
            with self.assertRaisesRegex(RuntimeError, "previous maintenance"):
                homelab.rotate_secrets()

    def test_pruning_keeps_old_generations_with_container_mounts(self):
        with patch.object(homelab, "command", self.fake_command):
            homelab.prepare()
        generations = self.run / "secrets/generations"
        old, unused = generations / ("a" * 64), generations / ("b" * 64)
        old.mkdir()
        unused.mkdir()
        def containers(*args, **kwargs):
            if args[:2] == ("podman", "ps"):
                return subprocess.CompletedProcess(args, 0, stdout=b"old-container\n")
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps([{"Source": str(old / "papra")}]).encode())
        with patch.object(homelab, "command", containers):
            homelab.prune_secrets((self.run / "secrets/current").resolve())
        self.assertTrue(old.exists())
        self.assertFalse(unused.exists())

    def test_exposed_backup_inputs_fail_before_restic_or_service_stop(self):
        for name in ("restic-password", "s3-credentials", "backup.env"):
            with self.subTest(name=name), patch.object(homelab, "command", self.fake_command):
                path = self.state / "credentials" / name
                path.chmod(0o644)
                with self.assertRaisesRegex(RuntimeError, "credential"):
                    homelab.backup()
                path.chmod(0o600)
        self.assertEqual(self.calls, [])

    def test_backup_uses_credential_files_instead_of_inherited_secret_values(self):
        with patch.dict(os.environ, RESTIC_PASSWORD="obsolete", AWS_ACCESS_KEY_ID="obsolete",
                        AWS_SECRET_ACCESS_KEY="obsolete", MINIO_SECRET_KEY="obsolete"):
            homelab.backup_credentials()
            self.assertNotIn("RESTIC_PASSWORD", os.environ)
            self.assertNotIn("AWS_SECRET_ACCESS_KEY", os.environ)
            self.assertNotIn("MINIO_SECRET_KEY", os.environ)
            self.assertEqual(os.environ["RESTIC_PASSWORD_FILE"], str(self.state / "credentials/restic-password"))
            self.assertEqual(os.environ["AWS_SHARED_CREDENTIALS_FILE"], str(self.state / "credentials/s3-credentials"))

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
        with patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", self.active):
            homelab.resume()
            homelab.resume()
        self.assertEqual(self.calls, [("systemctl", "start", "glance.service")])

    def test_pause_intent_survives_loss_of_runtime_directory(self):
        with patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", self.active):
            homelab.pause()
            manifest = self.state / "maintenance/paused-units.json"
            self.assertEqual(json.loads(manifest.read_text()), ["glance.service"])
            self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
            self.assertEqual(manifest.parent.stat().st_mode & 0o777, 0o700)
            shutil.rmtree(self.run)
            homelab.resume()
        self.assertFalse(manifest.exists())
        self.assertIn(("systemctl", "start", "glance.service"), self.calls)

    def test_failed_readiness_keeps_recovery_intent_and_blocks_updates(self):
        with patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", self.active), patch.object(homelab, "wait_ready", side_effect=RuntimeError("Not ready")):
            with self.assertRaisesRegex(RuntimeError, "Not ready"):
                homelab.update_apps()
        self.assertTrue((self.state / "maintenance/paused-units.json").exists())
        self.assertNotIn(("podman", "auto-update"), self.calls)
        self.assertFalse(any(call[:2] == ("restic", "forget") for call in self.calls))

    def test_legacy_runtime_intent_is_promoted_before_failed_restart(self):
        (self.run / "paused-units.json").write_text(json.dumps(["glance.service"]))
        with patch.object(homelab, "command", side_effect=subprocess.CalledProcessError(1, "systemctl")):
            with self.assertRaises(subprocess.CalledProcessError):
                homelab.resume()
        shutil.rmtree(self.run)
        with patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", self.active):
            homelab.resume()
        self.assertFalse((self.state / "maintenance/paused-units.json").exists())
        self.assertIn(("systemctl", "start", "glance.service"), self.calls)

    def test_unclean_stop_prevents_upload_and_recovers_services(self):
        (self.quadlets / "homeassistant.container").write_text("[Container]\n")
        def stopped(*args, **kwargs):
            result = self.fake_command(*args, **kwargs)
            if args[:2] == ("systemctl", "show"):
                result.stdout = b"ActiveState=failed\nResult=exit-code\n"
            return result
        active = lambda args, **kwargs: subprocess.CompletedProcess(args, 0 if args[-1] == "homeassistant.service" else 3)
        with patch.object(homelab, "command", stopped), patch.object(homelab.subprocess, "run", active), patch.object(homelab, "unit_ready", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "cleanly"):
                homelab.backup()
        self.assertFalse(any(call[:2] == ("restic", "backup") for call in self.calls))
        self.assertIn(("systemctl", "start", "homeassistant.service"), self.calls)

    def test_nonzero_exit_of_stopped_writer_preserves_existing_backup_policy(self):
        def stopped(*args, **kwargs):
            result = self.fake_command(*args, **kwargs)
            if args[:2] == ("systemctl", "show"):
                result.stdout = b"ActiveState=failed\nResult=exit-code\n"
            return result
        with patch.object(homelab, "command", stopped), patch.object(homelab.subprocess, "run", self.active):
            homelab.backup()
        self.assertTrue(any(call[:2] == ("restic", "backup") for call in self.calls))

    def test_thread_must_be_attached_not_merely_running(self):
        def state(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=b"detached\nDone\n")
        with patch.object(homelab.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), patch.object(homelab, "command", state):
            self.assertFalse(homelab.unit_ready("otbr.service"))
        with patch.object(homelab, "unit_ready", side_effect=[False, True]), patch.object(homelab.time, "sleep"):
            homelab.wait_ready(["otbr.service"])

    def test_cold_start_can_exceed_two_minutes(self):
        with patch.object(homelab, "unit_ready", side_effect=[False, False, True]), patch.object(homelab.time, "monotonic", side_effect=[0, 125, 250]), patch.object(homelab.time, "sleep"):
            homelab.wait_ready(["homeassistant.service"])

    def test_readiness_timeout_preserves_the_failed_service_name(self):
        with patch.object(homelab, "unit_ready", return_value=False), patch.object(homelab.time, "monotonic", side_effect=[0, 1, 3]), patch.object(homelab.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "homeassistant.service"):
                homelab.wait_ready(["homeassistant.service"], timeout=2)

    def test_retired_app_is_quiesced_when_it_still_runs(self):
        for name in homelab.RETIRED:
            with self.subTest(app=name):
                self.calls.clear()
                def retired_active(args, **kwargs):
                    return subprocess.CompletedProcess(args, 0 if args[-1] == name + ".service" else 3)
                with patch.object(homelab, "command", self.fake_command), patch.object(homelab.subprocess, "run", retired_active):
                    homelab.pause()
                    homelab.resume()
                self.assertEqual([call for call in self.calls if call[:2] != ("systemctl", "show")],
                                 [("systemctl", "stop", name + ".service"),
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
                          old_data / "wg-easy", old_config / "wg-easy",
                          old_data / "couchdb", old_config / "couchdb"):
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
                if args[-1] in ("n8n.service", "onedev.service", "grafana.service", "wg-easy.service", "couchdb.service"):
                    return subprocess.CompletedProcess(args, 0)
                return self.active(args, **kwargs)
            self.calls.append(tuple(args))
            output = b"\n\n".join([b"ActiveState=inactive\nResult=success"] * len(args[4:])) if tuple(args[:2]) == ("systemctl", "show") else b""
            return subprocess.CompletedProcess(args, 0, stdout=output)

        with patch.object(homelab.subprocess, "run", run):
            homelab.migrate(old_data, old_config, old_secrets)
        self.assertEqual((self.state / "apps/homeassistant/config/configuration.yaml").read_text(), "existing HA config")
        self.assertEqual((self.state / "apps/glance/config/glance.yml").read_text(), "device preference")
        for name, folder in (("beszel-ui", "data"), ("beszel-agent", "data"), ("papra", "ingestion")):
            self.assertEqual((self.state / "apps" / name / folder / ".state").read_bytes(), b"preserve hidden state")
        self.assertTrue((old_data / "homeassistant/configuration.yaml").exists())
        self.assertTrue((self.state / "maintenance/paused-units.json").exists())
        self.assertNotIn(("systemctl", "start", "glance.service"), self.calls)
        archive = self.state / "apps/_retired/immobot/legacy-image.tar"
        self.assertEqual(archive.read_bytes(), b"archived writable layer")
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        self.assertLess(self.calls.index(("podman", "commit", "--pause=true", "--quiet", "immobot")), self.calls.index(("systemctl", "stop", "couchdb.service", "glance.service", "grafana.service", "n8n.service", "onedev.service", "wg-easy.service")))
        for app in ("onedev", "n8n", "grafana", "wg-easy", "couchdb"):
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

    def test_device_backup_includes_persistent_security_override_tree(self):
        config = self.state / "maintenance/security/socket-proxy/haproxy.cfg"
        config.parent.mkdir(parents=True)
        config.write_text("restricted API")
        self.assertIn(str(self.state / "maintenance"), homelab.device_sources())

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
        security_config = self.state / "maintenance/security/haproxy.cfg"
        security_config.parent.mkdir(parents=True)
        security_config.write_text("restricted API")
        repository = str(Path(self.directory.name) / "repository")
        real_run = subprocess.run
        real_command = homelab.command

        def run(*args, **kwargs):
            if args[0][0] == "systemctl":
                self.calls.append(tuple(args[0]))
                return self.active(args[0], **kwargs) if "is-active" in args[0] else subprocess.CompletedProcess(args[0], 0, stdout=b"ActiveState=inactive\nResult=success")
            return real_run(*args, **kwargs)

        with patch.dict(os.environ, RESTIC_REPOSITORY=repository, RESTIC_PASSWORD="test-only-password", RESTIC_CACHE_DIR=str(Path(self.directory.name) / "cache")), patch.object(homelab.subprocess, "run", run), patch.object(homelab, "capture_recovery"), patch.object(homelab, "device_sources", return_value=[str(self.state / "maintenance")]):
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
        restored_config = restored / security_config.relative_to(security_config.anchor)
        self.assertEqual(restored_config.read_text(), "restricted API")
        for manifest in homelab.pause_manifests():
            self.assertFalse((restored / manifest.relative_to(manifest.anchor)).exists())
        self.assertIn(("systemctl", "stop", "glance.service"), self.calls)
        self.assertIn(("systemctl", "start", "glance.service"), self.calls)


if __name__ == "__main__":
    unittest.main()
