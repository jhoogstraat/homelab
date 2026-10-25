# Operations and recovery

Operator procedures for the Pi. Prefer systemd units over direct helper calls: they load credentials and run `homelab resume` after a failed or killed run.

## S3 backup repository

The Pi backs up to `s3:https://s3.hoogstraat.eu/backups/restic` on Garage (region `us-east-1`, path-style access, normal TLS verification). The bucket has a 1 TiB quota and no lifecycle expiration. Missing or unreachable backup configuration blocks host updates.

Use a dedicated private bucket/prefix and scoped credentials: ListBucket, GetObject, PutObject and DeleteObject. Keep TLS verification on; with a private CA, use restic's certificate configuration.

Recovery inputs live in `/var/lib/homelab/credentials` (root:root 0700, files 0600):

- `backup.env`: from `configs/backup.env.example`; endpoint, bucket/prefix and region only.
- `s3-credentials`: AWS shared-credentials INI from `configs/s3-credentials.example`.
- `restic-password`: high-entropy repository password.
- `age.key`: SOPS identity that decrypts `secrets/*.enc.env`.

systemd passes the password and S3 file via `LoadCredential=`; do not put keys or `RESTIC_PASSWORD_FILE` in `backup.env`. Independent copies of the restic password, S3 credentials and age key are kept privately on the operator Mac, outside Git. Without the restic password the backups cannot be read.

Manual restic session:

```sh
sudo -i
set -a; . /var/lib/homelab/credentials/backup.env; set +a
export RESTIC_PASSWORD_FILE=/var/lib/homelab/credentials/restic-password
export AWS_SHARED_CREDENTIALS_FILE=/var/lib/homelab/credentials/s3-credentials
restic snapshots --tag homelab
restic check
```

Run `restic init` only for a new, empty repository. A new device keeps its timers stopped until the first backup and restore drill pass.

## Maintenance

| Unit | Schedule | Operation |
| --- | --- | --- |
| `homelab-backup.timer` | Daily 02:00 | Cold backup, then retention: 7 daily, 4 weekly, 12 monthly (by host and tag) |
| `bootc-fetch-apply-updates.timer` | Sunday 04:00 | `update-host`: full backup, `bootc upgrade` (stage), pull every pinned app image of the staged deployment, reboot |

Updates run without manual steps. Renovate runs daily at 03:17 UTC and opens PRs for image pins in the Quadlets and Containerfiles; digest and patch updates merge on its next run once CI (host build, image scan) passes, minor and major updates wait for review. Patched images in `images/` are rebuilt and re-pinned automatically after each change ([patched application images](patched-application-images.md)). The host image rebuilds on every push to `main` and nightly at 04:17 UTC to pick up Fedora package updates (`dnf upgrade`); the nightly run skips the build when `main` already has a published image and `dnf check-update` finds nothing for it. The Pi installs the latest host image with Sunday's `update-host`. Renovate runs in GitHub Actions (`.github/workflows/renovate.yaml`) with the `RENOVATE_TOKEN` secret, a fine-grained PAT for this repository with read/write Contents, Commit statuses, Issues, Pull requests and Workflows; renew it before it expires. `podman-auto-update.timer` is disabled.

A backup stops writers for the whole restic scan/upload, then resumes them. Home Assistant gets 60 s to stop cleanly; an unclean stop or remaining writer aborts the capture. Recovery intent is written to `/var/lib/homelab/maintenance/paused-units.json` before stopping anything and is excluded from backups. `homelab-recover.service` replays it at boot. Recovery waits up to 300 s for units to be active, HA HTTP, a Matter `get_nodes` reply and an attached OTBR role; failure keeps the intent and blocks pruning and updates. Do not delete the manifest to bypass a failed restart; inspect the journal and run `sudo /usr/libexec/homelab resume`.

Backups cover `/var/lib/homelab/{apps,credentials,recovery,maintenance}`, Bluetooth pairings, NetworkManager profiles, machine ID, SSH host keys, `/etc/containers/systemd`, registry auth and fstab. Ciphertext and defaults come from the host image. Cloudflare and other SaaS state need their own account recovery.

Secret changes: update the ciphertext in Git, ship the image, then `sudo systemctl start homelab-secrets-rotate.service` (or reboot). Runtime files land in `/run/homelab/secrets/current/<app>`.

## Restore and restore drill

1. Load the restic session above, pick a snapshot and restore it to an isolated directory: `restic restore <id> --target /var/tmp/homelab-restore`. Run `restic check --read-data-subset=10%` periodically. An upload is not a restore drill.
2. Inspect `var/lib/homelab/recovery/{bootc.json,images.json,active-units.json}`. On a new device, boot the recorded host image and restore credentials and state **before** starting homelab services. Never put a second machine online with the same machine ID/SSH keys.
3. Stop the timers, `homelab.target` and any app units. Copy with `rsync -aHAX --numeric-ids --filter="-x security.selinux"`, keeping old state aside. Exclude `maintenance/paused-units.json` from older snapshots; it belongs to the source run. Restore `/etc` and Bluetooth state deliberately, then `restorecon -RF /var/lib/homelab /var/lib/bluetooth`.
4. If Depanator data was restored, run `sudo /usr/libexec/depanator restore-gate` before any start or resume; see [Depanator](depanator.md#backup-and-restore).
5. Snapshots from before 2026-10-11 may contain `${ADGUARD_USERNAME}`/`${ADGUARD_PASSWORD}` in the Glance YAML; replace them with `${secret:adguard-username}`/`${secret:adguard-password}`.
6. If restored state is older than the current pins, hold the matching digest from `images.json` with a drop-in such as `/etc/containers/systemd/vaultwarden.container.d/90-recovery.conf` (`[Container]` `Image=<repo>@sha256:<digest>`) and pre-pull it.
7. Start `homelab-prepare.service`, `systemctl daemon-reload`, then the recorded apps. Verify logins, Vaultwarden attachments, Papra downloads, AdGuard rules, Beszel reconnection and HA/Matter/Thread pairings. Never connect a second restored HA/Matter instance to the real devices.
8. Take a new backup, then remove holds and re-enable the timers.

Snapshots made before the retired apps (Immobot, OneDev, n8n, Grafana, wg-easy, CouchDB) were deleted still contain them under `apps/_retired` until retention expires them.

## Moving application storage to an SSD

Mount a local POSIX filesystem by UUID at `/var/lib/homelab`, stop all apps and maintenance, and copy the whole root with `rsync -aHAX --numeric-ids --filter="-x security.selinux"`. Add `homelab-prepare.service.d/storage.conf`:

```ini
[Unit]
RequiresMountsFor=/var/lib/homelab
```

Keep the mount mandatory, restore labels, test writes and run another restore drill. Container mount targets and images do not change.
