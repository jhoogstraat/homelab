# Migration and operation

These are operator procedures for the Pi. Do not reformat the existing SD card. Keep an independent copy of current data and the old boot deployment until restoration has been verified. The PR changes files; it does not deploy to the device.

## One-time cutover from Fedora IoT / Ansible

1. Publish the reviewed ARM64 image from `main`. Inspect `bootc status --json`, `rpm-ostree status`, `findmnt /var`, available space, current containers/units and the Pi's bootloader configuration. A running IoT install may not yet have `bootc`; install it using that system's supported package layering and reboot first if needed. Verify the existing Fedora boot chain can switch to the standard bootc base. Keep physical access and the previous boot deployment available. Generic build/lint is not a Pi boot test.
2. On the Pi, check out this reviewed repository to an operator directory. Inventory **actual** bind mounts using `sudo podman inspect <container>`; these commands assume the old `/opt/containers/{data,config,secrets}` layout. The helper resolves symlinks, covering the former `/var/opt/containers` aliases. Adjust `migrate` arguments if inspection differs. Look for external writers to Papra ingestion or other volumes and stop them, too. Confirm space for a second complete data copy plus an immobot image archive.
3. Provision `/var/lib/homelab/credentials/age.key` from your password manager using a private local file, owned root:root, mode 0600, parent mode 0700. Verify it decrypts the image's packaged secrets **before stopping applications**, especially if Bitwarden CLI connects to this Pi's Vaultwarden. Do not put the key in Git or chat. If GHCR is private, provision host registry credentials using the supported bootc registry-auth location. Set up the backup repository below before enabling automatic maintenance. Keep independent copies of its password, age key and S3 recovery credentials outside the Pi.
4. Stop automatic maintenance and migrate while old apps are quiesced:

   ```sh
   sudo systemctl stop podman-auto-update.timer bootc-fetch-apply-updates.timer
   sudo env HOMELAB_QUADLETS="$PWD/quadlets" "$PWD/scripts/homelab" migrate
   ```

   Migration preserves numeric ownership, ACLs, non-SELinux xattrs, hidden files and existing configuration. It copies Beszel's split directories, Papra data/ingestion, HA's full config, and mutable AdGuard/Glance configuration. Papra local environment preferences are preserved. Immobot, OneDev, n8n, Grafana, wg-easy and CouchDB config/data are archived under `apps/_retired/<app>`, including OneDev repositories/database and n8n workflows, encrypted credentials and encryption key. Immobot's writable layer/image is additionally captured if present; legacy decrypted secrets are archived root-only. SELinux labels are recreated by the new host/container mounts rather than copying obsolete container labels. The immobot image archive is a filesystem recovery point captured before stop, not an app-specific logical database export. Source directories are retained. **Successful migration leaves legacy applications stopped** to prevent subsequent writes from diverging from the copy. On failure it attempts to resume them. To abort before retiring units, run `sudo "$PWD/scripts/homelab" resume`; discard/rename the incomplete destination before retrying a full migration.
5. Retire the repo-owned legacy Quadlets, which otherwise take priority over the new image:

   ```sh
   sudo env HOMELAB_QUADLETS="$PWD/quadlets" "$PWD/scripts/homelab" retire-legacy
   ```

   For a compatible deployment without RPM layering, stage the image with `sudo bootc switch ghcr.io/jhoogstraat/homelab:latest`. If `bootc status --json` reports `status.booted.incompatible`, use rpm-ostree for this one-time transition ([bootc status documentation](https://bootc.dev/bootc/man/bootc-status.8.html)). The Pi inspected on 2026-10-04 has the following seven layered packages, all included in the target image. Remove those overlays as part of the container rebase:

   ```sh
   sudo rpm-ostree rebase \
     --uninstall=bluez --uninstall=cockpit --uninstall=cockpit-podman \
     --uninstall=htop --uninstall=ncurses --uninstall=rsync --uninstall=which \
     ostree-unverified-registry:ghcr.io/jhoogstraat/homelab:latest
   ```

   Inspect the staged deployment and ensure it matches the reviewed image before running `sudo systemctl reboot`. If the actual layer list differs, review it rather than blindly removing additional packages. After the new image boots without local RPM modifications, use bootc for future updates.

   The helper archives known `.container`, `.pod` and `.network` files from `/etc/containers/systemd` under `recovery/legacy-quadlets`, including immobot, OneDev and n8n, and leaves unrelated overrides alone. Inspect repo-owned `.container.d` or generic drop-ins from earlier manual customization separately; these also override image settings and are not automatically deleted. No old Ansible sync should run after this point. Remove obsolete enablement links for immobot, OneDev and n8n if any remain. Existing device dashboards may still link to retired services; remove those links locally, since migration preserves dashboard edits instead of overwriting them with new seeds.
6. On the new boot, inspect `bootc status`, `systemctl status homelab-prepare homelab.target`, `podman ps`, and `journalctl -u homelab-prepare`. Compare with `recovery/cutover-active-units.json`. Ten services (including the Beszel pod) start by default; Home Assistant, homepage, Matter and OTBR remain optional. If previously enabled on this device, deliberately enable them with a local Quadlet install drop-in or a Git change. Confirm DNS at `192.168.0.3`, TLS, routing, SQL writes and all integrations. Verify any Thread radio device/interface is correct before enabling OTBR. The repository retains existing static addresses and network assumptions.

   The inherited Pi fstab had a root entry with `defaults`, which made `systemd-remount-fs` try to remount the composefs root writable. After preserving `/etc/fstab` in recovery, `sudo bootc internals fixup-etc-fstab` applied bootc's native correction to the existing entry. Reload systemd and restart `systemd-remount-fs.service` to verify it succeeds; `/var` must remain writable. This addresses the [documented composefs/root-fstab incompatibility](https://bootc.dev/bootc/bootc-install.html#finding-and-configuring-the-physical-root-filesystem).
7. Change a representative setting using each app's supported UI, file or environment variable, then verify persistence through a service restart. Glance/HA file settings are edited locally; Glance normally reloads valid YAML changes without restarting. Papra server environment changes require restarting their containers. Do not add a settings editor or convert native files to environment variables just to make the apps look alike. Verify a complete backup and a restore drill before relying on scheduled updates. Optional Cockpit password login is configured locally with `sudo passwd cockpit`; the image no longer contains a preset password hash. Preserve any needed local host configuration through persistent `/etc`.

If switching fails before reboot, restore the archived Quadlets to `/etc/containers/systemd`, run `systemctl daemon-reload`, and start the units listed in `recovery/cutover-active-units.json`. Originals remain intact. After boot, `bootc rollback` can restore the previous OS deployment. The old Quadlets and data directories are needed to resume the old application layout; restore their archived definitions deliberately. Once new apps have written data, the original directories are stale: roll back application data only from a chosen consistent backup, with compatible image versions. Do not delete original data/archives until that recovery path has been exercised.

## Pi cutover verification: 2026-10-04

The Pi booted Fedora 45 from `ghcr.io/jhoogstraat/homelab:latest`, digest `sha256:0095599430d6ed0b49bf0b305bd9fd6833dd64f5eba510743f09ed745ccf7e94` (main commit `c97a229`). Bootc reports a compatible host with no local RPM overlays. The previous Fedora IoT 44 deployment is pinned for rollback, and original application directories are retained. All 16 kept application containers run with the migrated writable volumes, including the four optional applications enabled through local install drop-ins.

Verified DNS, application HTTPS with certificate validation, registry access, CouchDB health and authenticated configuration persistence through restart, the WireGuard interface, and the Thread router state. Fedora 45 requires a real non-login `containers` account for libsubid to resolve its existing ranges. CouchDB's read-only deployment file must belong to its service UID/GID so the official entrypoint can finish initialization. Both corrections are applied on the running Pi and included in the repository; WireGuard's existing web UI is routed at `https://wg.hoogstraat.de`.

The one-time age-encrypted recovery archive is at `~/Backups/homelab/2026-10-04-cutover/fedora-iot-recovery.tar.age` on the operator Mac. Validation authenticated the complete archive and restored the Vaultwarden SQLite files for a successful integrity check. This is not a scheduled Mac backup. Immobot, OneDev, n8n and the unused Valkey service are persistently masked, with recovery data retained. The three maintenance timers are also persistently masked until S3 backup and restore verification. Existing unmanaged Dockhand, HarborScale, TimescaleDB and ZeroClaw units had startup failures before cutover and remain outside this repository's managed app set.

## Retirement after cutover

Grafana and wg-easy are removed from the managed application set at the owner's
request. On an already deployed Pi, first take a successful backup, then stop
and persistently mask `grafana.service` and `wg-easy.service`. Archive their
complete directories under `apps/_retired`, preserving ownership and attributes;
keep Grafana's local secret with its archive. Remove only their monitor entries
from the device-owned Glance file, preserving other dashboard edits. The masks
keep older bootc deployments from restarting these services. Future images omit
their Quadlets, defaults and Grafana's encrypted secret. Restic continues to
include the retired state in `apps`; deleting it is a separate decision.

HarborScale was an unmanaged local pod: its API and worker were already failed.
Stop and mask `harborscale-pod.service`, `harborscale-api.service` and
`harborscale-worker.service`, and archive their three local Quadlets and referenced
available configuration/environment files in root-only recovery storage before
removing the definitions from `/etc/containers/systemd`. Both referenced HarborScale
environment files were already absent on the inspected Pi; record missing files
rather than inventing configuration. HarborScale is absent from the repository.

CouchDB was previously the Obsidian LiveSync backend, with 15,112 documents in
two non-empty application databases. The owner confirmed Obsidian now uses
iCloud and requested retirement. Back up first, stop and persistently mask
`couchdb.service`, and move its complete data/config directory to
`apps/_retired/couchdb`. Archive the Quadlet, Git-owned environment configuration,
local credentials and pre-retirement image metadata under root-only recovery
storage. Remove CouchDB from new images, including its special initialization
ownership handling, defaults and encrypted secret. Retain its archived state in
S3 backups; restoring an older host image must not restart this obsolete service.

### Legacy local services retired on 2026-10-05

The owner also retired Dockhand, TimescaleDB and ZeroClaw. These services were
unmanaged local Quadlets under `/etc/containers/systemd` and had already failed
before cutover. They were never part of this repository's application set.

Take a successful pre-retirement backup, then archive the local definitions and
any available referenced data/configuration under root-only recovery storage.
Expand Quadlet `%p` to the service name when locating their bind mounts and
environment files. On the inspected Pi, all referenced persistent application
paths were absent; record that absence in the recovery ledger. The Podman socket
mounted by Dockhand is a runtime endpoint, not application data to archive.

Persistently mask and stop `dockhand.service`, `timescaledb.service` and
`zeroclaw.service`, remove their three archived local Quadlets, and reload systemd.
Keep the HarborScale API, worker and pod masks, and clear failed state only for
these retired units with `systemctl reset-failed`. Preserve unrelated local
Quadlets, running applications and cached container images.

The recovery archive is
`/var/lib/homelab/recovery/retired-legacy-services-2026-10-05`. Follow retirement
with an encrypted restic backup, repository check and verified restoration of
the archived definitions. The completed cleanup leaves 13 retained application
containers plus the Beszel infrastructure container, with no failed systemd
units. All three automatic maintenance timers remain active.

## Configure the S3 backup server

The Pi is provisioned with `s3:https://s3.hoogstraat.eu/backups/restic` on Garage, region `us-east-1`, using path-style bucket access and normal TLS verification. The bucket has a 1 TiB quota and no lifecycle expiration. A full repository read and complete restore/content verification passed, including seven SQLite databases. Missing or unreachable backup configuration still prevents automatic updates.

Create a dedicated private bucket/prefix and scoped S3 credentials. Restic needs ListBucket plus GetObject, PutObject and DeleteObject for backup/pruning. Use HTTPS with normal certificate validation and the provider's required region. With a private CA, provide the CA through restic's supported certificate configuration; do not disable TLS verification. Preserve the remote S3 server's own data independently.

For a new device, keep maintenance timers stopped until the first successful backup and restore drill. The inspected Pi has passed this acceptance gate and all three timers are enabled. If a device has been persistently masked for cutover, release that hold only after its S3 backup and restore drill pass:

```sh
sudo systemctl unmask homelab-backup.timer podman-auto-update.timer bootc-fetch-apply-updates.timer
sudo systemctl enable --now homelab-backup.timer podman-auto-update.timer bootc-fetch-apply-updates.timer
```

Copy `configs/backup.env.example` locally to `/var/lib/homelab/credentials/backup.env`, set actual endpoint, bucket/prefix, region and access keys, then set root:root 0600. Store a high-entropy restic password in `/var/lib/homelab/credentials/restic-password` with the same permissions. The example is a template, not a working destination. The repository password is required for restore and cannot be recovered merely from S3 credentials.

The provisioned password is at `/var/lib/homelab/credentials/restic-password` on
the Pi (root:root, mode 0600). Its independent operator Mac copy is at
`~/Backups/homelab/2026-10-04-cutover/restic-recovery/restic-password`, with mode
0600 inside a mode-0700 recovery directory. That directory also contains S3
credentials and recovery instructions. These are private local files, not Git
contents. Restic's generated password unlocks S3 backups; the separate one-time
`fedora-iot-recovery.tar.age` archive uses the existing SOPS age identity.

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
5. Run `systemctl start homelab-prepare.service` (restart it if already completed), `systemctl daemon-reload`, then start the recorded app set excluding retired immobot, OneDev, n8n, Grafana, wg-easy and CouchDB. Verify authentication, configuration persistence, Vaultwarden attachments and login, Papra original document download, AdGuard rules, Beszel reconnection and HA/Matter/Thread pairings as applicable. Glance content, Traefik certificates and homepage Spotify refresh tokens should also survive. Never connect a second restored HA/Matter instance to the same real devices during a test.
6. Take a new successful backup. Only after verification and any explicit app migration should you remove image holds, reload systemd and re-enable timers. Restore time depends on data size, S3 throughput and image availability; measure it rather than assume it.

## Moving application storage to an SSD

Mount a prepared local POSIX filesystem by UUID at `/var/lib/homelab`, stop all apps/maintenance, and copy the entire root with `rsync -aHAX --numeric-ids --filter="-x security.selinux"`, preserving credentials and ownership. Add a local `homelab-prepare.service.d/storage.conf`:

```ini
[Unit]
RequiresMountsFor=/var/lib/homelab
```

Keep the corresponding mount mandatory, verify it before startup, restore labels, test application writes and perform another remote restore drill. Back up the mount configuration independently. Moving storage does not change container mount targets or require an app image rebuild. No SSD, filesystem format or Btrfs snapshot automation is assumed by this PR.
