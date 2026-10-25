# Patched application images

The ARM64 derivatives in `images/` keep the pinned upstream application versions, startup commands, ports, data mounts and runtime users. They replace vulnerable OS packages or runtime dependencies so they pass the same security gate as every other image (`scripts/scan-images`).

| Image | Changes |
| --- | --- |
| Home Assistant | Upstream 2026.10.2 with Alpine updates; certifi, Pillow 13.0.0 and uv from PyPI (hash-pinned), with HA's constraints and integration manifests bumped so it does not downgrade them; go2rtc 1.9.14 and tempio 2024.11.2 rebuilt with Go 1.27.2 |
| OTBR | Upstream 4.2.5 with Debian updates only; upstream tempio and OTBR binaries; `FLOW_CONTROL=0` in `configs/environment/otbr` |
| Papra | Debian updates; affected npm packages replaced with published fixes; esbuild 0.18.20 and 0.25.10 rebuilt with Go 1.27.2; `nonroot` user |
| API broker | HAProxy 3.4 Alpine with package upgrades (patched PCRE2); restricted API configuration unchanged |
| TREK | Upstream 5.0.0; KItinerary and libxml2 removed, so booking-file import is unavailable |

`Build patched application images` runs on every change under `images/` and nightly at 00:37 UTC. The nightly run only rebuilds apps whose deployed image has OS package updates pending (`apk`/`apt`), so quiet nights change nothing. Each run builds the selected apps, runs the smoke checks in `images/verify.sh`, publishes `ghcr.io/jhoogstraat/homelab:<app>-sha-<commit>`, then opens a PR pinning those apps' Quadlets to the new digests and merges it once the host build and image scan pass. A failed check leaves the PR open. Renovate's base image updates in `images/*/Containerfile` therefore reach the Pi without manual steps.

`images/patch-node.py` installs fixed npm versions in place, keeping pnpm/npm paths intact; `images/patch-esbuild.py` replaces every vulnerable native esbuild copy, including pnpm hardlinks, without changing API versions.

Image rollback does not undo database migrations; keep data backups and previous pins.

## Upstream images without a derivative

Matter runs upstream `ghcr.io/matter-js/matterjs-server:1.5.0`. It uses BlueZ over a read-only `/run/dbus` mount (`NOBLE_BINDINGS=dbus`, `spc_t`). Direct BLE commissioning from the Pi has not worked (HCI `0x3e`); commission through the Home Assistant iPhone app over Thread.
