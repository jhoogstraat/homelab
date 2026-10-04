# Homelab

A Raspberry Pi 4 running a Fedora bootc host and Podman Quadlets. Git describes how services run; application settings and data live on the device and are backed up together.

- **Host:** CI builds `ghcr.io/jhoogstraat/homelab:latest` for ARM64. Weekly bootc upgrades apply host changes and may reboot.
- **Applications:** Podman follows the tags in `quadlets/` daily. Updates replace containers without a host rebuild or reboot. A successful full backup is required before either kind of update.
- **Configuration:** `configs/environment/` is Git-owned infrastructure. `configs/defaults/` initializes device configuration once. Subsequent app UI changes or local file edits survive redeployment.
- **Storage:** `/var/lib/homelab/apps/<app>/` holds local POSIX configuration/data. Encrypted, deduplicated restic backups go to a remote S3-compatible repository. The current SD-card backup pauses services during upload; a USB SSD is the recommended storage upgrade.
- **Secrets:** only SOPS ciphertext is packaged in the image. The age key, S3 credentials and restic password are provisioned locally with root-only permissions.

Read [the architecture and ownership boundaries](docs/homelab-reconciliation.md), [migration, backup and recovery instructions](docs/operations.md), and the application inventories: [stateful services](docs/application-storage.md), [infrastructure and home automation](docs/application-storage-other.md).

Immobot is retired. Its existing state is archived during migration. Home Assistant, homepage, Matter and OTBR remain optional, matching the previous inventory.

## Repository

| Path | Purpose |
| --- | --- |
| `Containerfile` | Fedora host, packages, SSH/firewall policy and maintenance services |
| `quadlets/` | Application images, networking, mounts, hardware and routing |
| `configs/environment/` | Git-owned hosting settings, reapplied at boot |
| `configs/defaults/` | Initial application settings; never overwrite device edits |
| `secrets/*.enc.env` | Encrypted container environment files |
| `scripts/homelab` | Initialization, cold backup, guarded updates and legacy migration |
| `systemd/` | Host timers and shared application lifecycle |
| `tests/` | State preservation and failure recovery checks |

The old Ansible deployment is removed. Its last version remains in Git history at `dafdde0`; it must not keep syncing configuration after cutover.

## Development

```sh
python3 -m unittest discover -s tests -v
podman build --arch arm64 --tag homelab-bootc:build .
```

CI runs these checks on pull requests and publishes only from `main` or a manual workflow run. Linux is required to build bootc. Image build/lint and Quadlet generation do not prove that the Pi boots or that its radio devices work; the migration guide includes those checks.
