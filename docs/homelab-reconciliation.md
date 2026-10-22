# Host, applications and storage ownership

Infrastructure changes go through Git, each application is configured through its simplest supported interface, and device state is recovered from encrypted backups.

## Reconciliation

The ARM64 host image derives from Fedora's pinned `fedora-bootc:45` base. DNF layers host packages, including Pi firmware/U-Boot packages; SOPS is a patched rebuild of 3.13.3. bootc does not install firmware or bootloader files on an existing Pi.

At boot, `homelab-prepare.service` materializes Git-owned environment files into `/var/lib/homelab/environment`, atomically selects a complete decrypted secret generation under `/run/homelab/secrets`, and seeds missing application config files. Every container/pod requires successful preparation, so a partially decrypted deployment never starts. Existing device config is never reseeded.

Quadlets and systemd provide startup, dependencies and restarts. Every repo app, including Home Assistant, Matter, OTBR and homepage, is enabled through `[Install] WantedBy=homelab.target`. Every `homelab.network` member pins its address; `tests/test_quadlets.py` enforces this.

Traefik and Beszel connect to `socket-proxy` over the internal `podman-api` network. The broker permits discovery, inspection, stats and events, and denies mutation, exec, logs, archive access and native Libpod routes. It alone mounts the rootful Podman socket. The API is never published on a host port. See [security limits](security-audit.md).

Home Assistant, Matter and OTBR use host networking. Border-router sysctls (forwarding, RA handling) ship in `/usr/lib/sysctl.d/60-homelab-network.conf`. `wpan0` is an explicit member of the firewalld public zone so LAN clients (e.g. iPhone commissioning) can reach the whole Thread mesh; without it, forwarded LAN→Thread traffic is rejected.

Timers use the host's Europe/Berlin timezone:

| Time | Operation |
| --- | --- |
| Daily 02:00 | Consistent encrypted application backup |
| Sunday 04:00 | Back up, stage `bootc upgrade`, pre-pull the staged deployment's pinned app images, reboot |

A process lock serializes these operations. Timers do not catch up at boot. Missing or unreachable backup configuration blocks host updates; an S3 failure detected before backup never stops apps. Upload failure restarts the apps and blocks updates. A durable restart manifest, `ExecStopPost` and `homelab-recover.service` recover only previously running apps.

Application definitions pin registry digests. Renovate proposes digest/version changes for review; security scans gate publication. Pins reach the Pi through the host image. Recovery metadata records image digests and bootc status. Container and OS rollback do not undo database migrations; restore pre-update data when a migration cannot be reversed.

References: [bootc filesystem persistence](https://bootc.dev/bootc/bootc-filesystem.7.html), [Fedora base-image interfaces](https://gitlab.com/fedora/bootc/base-images).

## Configuration ownership

Choose the configuration method per application and setting: an existing UI where it supports the setting, otherwise the documented file or environment variable. Native formats are preserved, not translated into a new configuration system.

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
| Git / host image | Images and digests, networks, ports, proxy routes/TLS provider, hardware, deployment URLs, SSH/firewall policy, encrypted secrets | PR, CI, bootc update |
| Seed on first install | AdGuard YAML, HA YAML, Glance dashboard, Papra `app.env` | Copied only if absent |
| Device / application | Users, dashboards, documents, integrations, pairing keys, all databases | App UI/API, or local files when the app has no editor |
| Device / operator | age key, S3 endpoint/credentials, restic password, optional registry authentication | Root-only local provisioning; no image rebuild |

App environment preferences live in `/var/lib/homelab/apps/<app>/config/app.env` where supported; restart that service after editing.

The host uses persistent `/etc`. bootc's merge preserves device identities, storage/network configuration and credentials, so local `/etc` overrides need deliberate management: files in `/etc/containers/systemd` override image Quadlets.

## Storage

Application state lives under `/var/lib/homelab/apps/<app>` as bind mounts, which keep storage explicit and preserve ownership with idmapped mounts. Named volumes would add nothing: they live on the same SD card and need the same consistency procedure.

Use a USB SSD for this root when available, mounted by UUID with `RequiresMountsFor=/var/lib/homelab`, never falling back to an empty SD-card directory.

Backups stop all writers, run restic directly over the application tree, then restart; apps are down for the whole scan/upload. Retention runs after restart.

S3 is the backup target, not a mount for live state: SQLite and application files need local locking and POSIX semantics, so no s3fs/rclone adapters. Native S3 drivers (Papra documents, registry) are possible but would add live network dependencies, so state stays local. Hosting the only backup repository on one S3 server does not protect against that server's loss.
