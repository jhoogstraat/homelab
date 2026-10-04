# Migration and operation

These are operator procedures for the Pi. Do not reformat the existing SD card. Keep an independent copy of current data and the old boot deployment until restoration has been verified. The PR changes files; it does not deploy to the device.

## One-time cutover from Fedora IoT / Ansible

1. Publish the reviewed ARM64 image from `main`. Inspect `bootc status --json`, `rpm-ostree status`, `findmnt /var`, available space, current containers/units and the Pi's bootloader configuration. A running IoT install may not yet have `bootc`; install it using that system's supported package layering and reboot first if needed. Verify the existing Fedora boot chain can switch to the standard bootc base. Keep physical access and the previous boot deployment available. Generic build/lint is not a Pi boot test.
2. On the Pi, check out this reviewed repository to an operator directory. Inventory **actual** bind mounts using `sudo podman inspect <container>`; these commands assume the old `/opt/containers/{data,config,secrets}` layout. The helper resolves symlinks, covering the former `/var/opt/containers` aliases. Adjust `migrate` arguments if inspection differs. Look for external writers to Papra ingestion or other volumes and stop them, too. Confirm space for a second complete data copy plus an immobot image archive.
3. Stop automatic maintenance and migrate while old apps are quiesced:

   ```sh
   sudo systemctl stop podman-auto-update.timer bootc-fetch-apply-updates.timer
   sudo env HOMELAB_QUADLETS="$PWD/quadlets" "$PWD/scripts/homelab" migrate
   ```

   Migration preserves numeric ownership, ACLs, non-SELinux xattrs, hidden files and existing configuration. It copies Beszel's split directories, Papra data/ingestion, HA's full config, and mutable AdGuard/Glance/CouchDB configuration. Grafana/Papra local environment preferences are preserved. Immobot config/data and its writable layer/image, if present, are archived under `apps/_retired/immobot`; legacy decrypted secrets are archived root-only. SELinux labels are recreated by the new host/container mounts rather than copying obsolete container labels. The immobot image archive is a filesystem recovery point captured before stop, not an app-specific logical database export. Source directories are retained. **Successful migration leaves legacy applications stopped** to prevent subsequent writes from diverging from the copy. On failure it attempts to resume them. To abort before retiring units, run `sudo "$PWD/scripts/homelab" resume`; discard/rename the incomplete destination before retrying a full migration.
4. Provision `/var/lib/homelab/credentials/age.key` from your password manager using a private local file, owned root:root, mode 0600, parent mode 0700. Do not put the key in Git or chat. If GHCR is private, provision host registry credentials using the supported bootc registry-auth location. Set up the backup repository below before enabling automatic maintenance. Keep independent copies of its password, age key and S3 recovery credentials outside the Pi.
5. Retire the repo-owned legacy Quadlets, which otherwise take priority over the new image:

   ```sh
   sudo env HOMELAB_QUADLETS="$PWD/quadlets" "$PWD/scripts/homelab" retire-legacy
   sudo bootc switch ghcr.io/jhoogstraat/homelab:latest
   sudo systemctl reboot
   ```

   The helper archives known `.container`, `.pod` and `.network` files from `/etc/containers/systemd` under `recovery/legacy-quadlets`, including immobot, and leaves unrelated overrides alone. Inspect repo-owned `.container.d` or generic drop-ins from earlier manual customization separately; these also override image settings and are not automatically deleted. No old Ansible sync should run after this point. Remove any obsolete immobot enablement symlink if it remains (`systemctl disable immobot.service` before retiring its definition is sufficient).
6. On the new boot, inspect `bootc status`, `systemctl status homelab-prepare homelab.target`, `podman ps`, and `journalctl -u homelab-prepare`. Compare with `recovery/cutover-active-units.json`. Fifteen services (including the Beszel pod) start by default; Home Assistant, homepage, Matter and OTBR remain optional. If previously enabled on this device, deliberately enable them with a local Quadlet install drop-in or a Git change. Confirm DNS at `192.168.0.3`, TLS, routing, SQL writes and all integrations. Verify any Thread radio device/interface is correct before enabling OTBR. The repository retains existing static addresses and network assumptions.
7. Change a representative setting in each UI, restart its service and verify persistence. Glance/HA file settings are edited locally. Verify a complete backup and a restore drill before relying on scheduled updates. Optional Cockpit password login is configured locally with `sudo passwd cockpit`; the image no longer contains a preset password hash. Preserve any needed local host configuration through persistent `/etc`.

If switching fails before reboot, restore the archived Quadlets to `/etc/containers/systemd`, run `systemctl daemon-reload`, and start the units listed in `recovery/cutover-active-units.json`. Originals remain intact. After boot, `bootc rollback` can restore the previous OS deployment. The old Quadlets and data directories are needed to resume the old application layout; restore their archived definitions deliberately. Once new apps have written data, the original directories are stale: roll back application data only from a chosen consistent backup, with compatible image versions. Do not delete original data/archives until that recovery path has been exercised.

## Configure the future S3 backup server

No S3 endpoint is configured yet. Apps can start without one; automatic backups/updates fail closed until provisioning is complete.

Create a dedicated private bucket/prefix and scoped S3 credentials. Restic needs ListBucket plus GetObject, PutObject and DeleteObject for backup/pruning. Use HTTPS with normal certificate validation and the provider's required region. With a private CA, provide the CA through restic's supported certificate configuration; do not disable TLS verification. Preserve the remote S3 server's own data independently.

Keep the maintenance timers stopped until the first successful backup and restore drill; after cutover stop the newly enabled timers again while completing acceptance.

Copy `configs/backup.env.example` locally to `/var/lib/homelab/credentials/backup.env`, set actual endpoint, bucket/prefix, region and access keys, then set root:root 0600. Store a high-entropy restic password in `/var/lib/homelab/credentials/restic-password` with the same permissions. The example is a template, not a working destination. The repository password is required for restore and cannot be recovered merely from S3 credentials.

Use the same environment for manual restic commands:

```sh
sudo -i
set -a
. /var/lib/homelab/credentials/backup.env
set +a
restic init                      # once, only for a new dedicated repository
restic snapshots
systemctl start homelab-backup.service
journalctl -u homelab-backup.service
restic check
```

Verify a snapshot with tag `homelab`, then restore it to an isolated directory. Never run `restic init` over an existing repository. Scheduled retention is seven daily, four weekly and twelve monthly snapshots, scoped by host and tag; pruning runs after apps restart. If server-side object retention blocks deletion, coordinate restic pruning with its policy instead of silently ignoring errors.

The backup includes all of `apps`, root-only credentials, recovery metadata, Bluetooth pairings, NetworkManager connection profiles, machine identity, SSH host keys and existing local Quadlet/registry-auth files, fstab and the storage dependency drop-in. Ciphertext and environment defaults are recovered from the host image. Secrets are encrypted in the restic repository, including the password file inside the snapshot; an independent password copy is essential to unlock it. Cloudflare account state and other remote SaaS settings require independent account recovery.

A failed upload or a killed backup triggers service recovery. For direct command-line maintenance, use `/usr/libexec/homelab backup`, `update-apps` or `update-host` **with the backup environment loaded**; systemd invocation is preferred because it also supplies termination recovery. Inspect logs for failures; a timer alone is not an alerting system. Beszel can monitor service/availability failures after configuring alerts in its UI. For an interrupted manual helper, inspect and run `homelab resume` rather than deleting its recovery manifest.

## Restore drill and disaster recovery

1. Preserve the restic password and S3 credentials on a separate trusted system. Load the environment above. Choose a specific successful snapshot using `restic snapshots --tag homelab`, then `restic restore <snapshot-id> --target /var/tmp/homelab-restore`. Run `restic check --read-data-subset=10%` periodically and a full `restic check --read-data` when practical. A successful upload is not a restore drill.
2. Inspect the restored `var/lib/homelab/recovery/{bootc.json,images.json,active-units.json}`. For a new device, install a compatible Fedora/Pi boot environment and the recorded host image, then restore credentials/state **before starting homelab services**. Do not copy another device's machine identity/SSH keys to a second machine still online. The cold snapshot contains the complete SQLite files, attachments, encryption keys and config together.
3. Stop maintenance timers and `homelab.target` plus any manually started app units on the destination. Ensure no external process writes to the app root. Restore to a fresh local destination with `rsync -aHAX --numeric-ids --filter="-x security.selinux"` from the staged tree, preserving old state separately. Restore `/var/lib/homelab/{apps,credentials,recovery}`. Restore relevant `/etc` and Bluetooth state deliberately, with root-only permissions; `restorecon -RF /var/lib/homelab /var/lib/bluetooth` resets host SELinux labels, and Quadlet `:Z` applies container labels at startup.
4. Before starting app state created by an older version, hold the corresponding image to a recorded RepoDigest. For example, create `/etc/containers/systemd/vaultwarden.container.d/90-recovery.conf` containing:

   ```ini
   [Container]
   Image=docker.io/vaultwarden/server@sha256:<recorded-digest>
   AutoUpdate=
   ```

   Use the **actual repository and digest** from `images.json`. Do this for each app needing an older image; do not let `latest` migrate restored databases before validating them. Pre-pull these exact images. A digest records identity, not guaranteed registry availability: retain needed custom images externally or in the backed-up registry, and start that registry first if an image depends on it. If no pullable digest was recorded, recover the matching retained image before proceeding.
5. Run `systemctl start homelab-prepare.service` (restart it if already completed), `systemctl daemon-reload`, then start the recorded app set excluding retired immobot. Verify authentication, configuration persistence, n8n credential decryption/workflows, Vaultwarden attachments and login, Papra original document download, OneDev repositories, CouchDB documents, Grafana dashboards, AdGuard rules, WireGuard peers, Beszel reconnection and HA/Matter/Thread pairings as applicable. Glance content, Traefik certificates and homepage Spotify refresh tokens should also survive. Never connect a second restored HA/Matter instance to the same real devices during a test.
6. Take a new successful backup. Only after verification and any explicit app migration should you remove image holds, reload systemd and re-enable timers. Restore time depends on data size, S3 throughput and image availability; measure it rather than assume it.

## Moving application storage to an SSD

Mount a prepared local POSIX filesystem by UUID at `/var/lib/homelab`, stop all apps/maintenance, and copy the entire root with `rsync -aHAX --numeric-ids --filter="-x security.selinux"`, preserving credentials and ownership. Add a local `homelab-prepare.service.d/storage.conf`:

```ini
[Unit]
RequiresMountsFor=/var/lib/homelab
```

Keep the corresponding mount mandatory, verify it before startup, restore labels, test application writes and perform another remote restore drill. Back up the mount configuration independently. Moving storage does not change container mount targets or require an app image rebuild. No SSD, filesystem format or Btrfs snapshot automation is assumed by this PR.
