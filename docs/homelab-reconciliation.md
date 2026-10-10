# Host, applications and storage ownership

The operating mode is: publish infrastructure changes through Git, configure each application through its simplest supported interface, and recover device state from encrypted backups. There is no Ansible sync in normal operation.

## Reconciliation

The ARM64 host image derives directly from Fedora's published `fedora-bootc:45` base, as selected for this migration. The inspected Pi runs Fedora IoT 44, so cutover also upgrades the host major version. Fedora 45 was still beta on 2026-10-04 ([Fedora announcement](https://discussion.fedoraproject.org/t/fedora-linux-45-beta-released/202136)); this is an explicit operator choice. DNF layers host packages, including Pi firmware/U-Boot packages; SOPS comes from its versioned upstream binary image. This removes the custom IoT rootfs compositor and its extra namespace requirements. It does not install or replace a running Pi's firmware/bootloader; verify the existing Fedora IoT boot chain during cutover. A fresh SD-card image installer is outside this change.

At boot, `homelab-prepare.service` materializes Git-owned environment files into `/var/lib/homelab/environment`, atomically selects a complete decrypted secret generation, and seeds missing application config files. Every container/pod requires successful initialization. This avoids booting partially decrypted deployments. The generated environment copy permits SELinux labeling; container mounts of Git-owned files remain read-only. Device application config is never reseeded when it exists.

Quadlets and systemd provide startup, dependencies and process restart. Applications retain their existing process restart policies; this is not a claim that every application has a functional health check. The Beszel containers and pod have explicit boot activation.

Timers use the host's Europe/Berlin timezone:

| Time | Operation |
| --- | --- |
| Daily 02:00 | Consistent encrypted application backup |
| Daily 03:00 | Check tracked application tags; when updates exist, take another backup before Podman auto-update |
| Sunday 04:00 | Back up, then `bootc upgrade --apply`; may reboot for a new host deployment |

A process lock serializes these operations. Timers do not catch up at boot. Missing/unreachable/uninitialized backup configuration prevents automatic updates. An S3 connectivity failure detected before backup never stops apps. Upload failure restarts the apps and prevents updates. A durable, root-only restart manifest and systemd `ExecStopPost` recover only previously running apps after terminated maintenance; `homelab-recover.service` also attempts recovery at boot. Recovery intent remains until services pass readiness checks. Manual maintenance must use the same helper, or stop the timers first.

Application image changes follow Podman's native registry comparison and rollback behavior. Tags retain their existing policies (`latest`, `stable`, major versions and `latest-rootless`); these policies can include breaking database migrations. Recovery metadata records image digests and bootc status. Container rollback and OS rollback do not undo database changes: restoring pre-update data is required when a schema migration cannot be reversed. Host updates still need an image and possibly a reboot. Most app changes need neither.

References: [bootc filesystem persistence](https://bootc.dev/bootc/bootc-filesystem.7.html), [Fedora base-image interfaces](https://gitlab.com/fedora/bootc/base-images), [Podman auto-update and rollback](https://docs.podman.io/en/latest/markdown/podman-auto-update.1.html), [SOPS release](https://github.com/getsops/sops/releases/tag/v3.13.3).

## Configuration ownership

Choose the configuration method per application and setting. Use an existing UI when it supports the setting; otherwise use the documented configuration file or environment variable. There is no requirement that everything be browser-editable, use environment variables, or support S3 directly. The common storage/backup layout preserves those different native formats without translating them into a new configuration system.

| Application or setting | Simplest supported method |
| --- | --- |
| AdGuard, Beszel hub, Vaultwarden admin settings, Papra documents | Existing application UI, with its state persisted and backed up |
| Glance dashboard | Edit native `glance.yml` on the device; Glance reloads valid file changes |
| Home Assistant | UI for supported integrations/settings; native YAML for settings requiring files |
| Papra instance options | Documented Papra environment variables through local `app.env`; restart the affected container |
| Traefik and registry hosting | Native static configuration/environment and Quadlet routing/mounts in Git |
| Cloudflare tunnel settings | Cloudflare dashboard; connector credentials remain protected on the device |
| Custom homepage | Application source for compiled content; documented environment for runtime connections |
| Matter/Thread settings | Existing server or Home Assistant management interface; hardware/network parameters in Git |

| Owner | Examples | Change mechanism |
| --- | --- | --- |
| Git / host image | Images and tags, networks, ports, proxy routes/TLS provider, hardware, deployment URLs, SSH/firewall policy, encrypted connection secrets | PR, CI, bootc update |
| Seed on first install | AdGuard YAML, HA YAML, Glance dashboard, Papra `app.env` | Copied only if absent |
| Device / application | Users, dashboards, workflows, documents, peers, integrations, pairing keys, all databases | App UI/API, or local files when the app has no editor |
| Device / operator | age key, S3 endpoint/credentials, restic password, optional registry authentication and local enablement overrides | Root-only local provisioning; no image rebuild |

App environment preferences requiring a restart live in `/var/lib/homelab/apps/<app>/config/app.env` where supported. Restart that service after editing. Glance and HA YAML-only settings require file edits; neither changing ownership nor using an agent creates a browser editor. Traefik remains Git-owned infrastructure. Cloudflare dashboard settings remain remote account state. Homepage content is compiled into its own application image, which can update independently of the host.

The host uses normal persistent `/etc`, not transient `/etc`. bootc's merge preserves device identities, storage/network configuration and credentials. Local `/etc` overrides therefore need deliberate management; bootc does not continually discard them. Legacy `/etc/containers/systemd` definitions must be retired because they override image Quadlets. The migration helper archives only filenames belonging to this repo, leaving unrelated units alone.

## Storage decision

Keep a uniform application root at `/var/lib/homelab/apps`. Bind mounts remain appropriate: they expose explicit, auditable storage and preserve ownership with idmapped mounts. Named Podman volumes would still live on the SD card and require the same consistency procedure. They are not a backup or an independent storage layer.

Use a USB SSD for this root when available, mounted by filesystem UUID before initialization. Add a `RequiresMountsFor=/var/lib/homelab` dependency and never fall back to an empty SD-card directory when the SSD is absent. This reduces SD write pressure; remote backups still protect against local device failure.

The working baseline supports the existing filesystem: stop all running writers, back up the complete application tree directly with restic, then restart. Applications are stopped for the entire scan/upload; the initial backup can be long. Retention/pruning happens after restart. We do not add a second full staging copy on the SD card, nor a new filesystem migration as a prerequisite. A later SSD/Btrfs implementation can quiesce writers briefly, snapshot the complete root, resume, and upload the snapshot; that requires explicit implementation and testing and is not enabled here.

S3 is the remote backup target, not a mounted replacement for local database storage. SQLite and application files need local locking and filesystem semantics. Avoid s3fs/rclone filesystem adapters for these volumes. Restic provides encryption, deduplication, incremental uploads, retention and integrity checks over a standard S3 API.

Only use native S3 drivers for live object data. Papra supports native S3 documents and a documented migration tool; its SQLite DB remains local. Registry has a native S3 driver. Both are optional and would introduce live network dependencies, so this migration leaves them local. Beszel has native S3 backup support. HA's native AWS S3 backup integration excludes generic compatible servers, so the host backup handles it. Full details and primary sources are in the application inventories.

Use distinct prefixes/buckets and credentials if live app objects are introduced later. Objects in a primary S3 store still need independent backups. Hosting the sole backup repository on one remote S3 server improves local recovery but does not protect against that server's loss; replicate/version/protect it separately as appropriate.

## Acceptance evidence

Repository tests cover config preservation, atomic secret rotation, unreachable backup targets, backup failure recovery, guarded updates, and retired app handling. The ARM64 image must build, pass bootc lint and generate every Quadlet. Real backup/restore tests verify a SQLite database and binary attachment through restic.

The final ARM64 build passed 13 bootc lint checks with one warning: the Pi firmware package supplies files under `/boot/efi`. They are not automatically installed on an existing Pi by bootc; compatibility with its existing boot chain must be checked before cutover. No bootloader shim or broad container privileges are introduced.

Remaining device acceptance is explicit: boot the image on the existing Pi, confirm mounted filesystem and UID/SELinux behavior, preserve UI changes through restart, check hardware/network integrations, then restore representative application data from the actual S3 endpoint. These checks require the device and future S3 service; no remote endpoint is fabricated in this repository.
