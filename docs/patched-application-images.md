# Patched application images

The ARM64 derivatives in `images/` keep the pinned upstream application versions, startup commands, ports, data mounts and runtime users. They replace vulnerable OS packages or runtime dependencies so they pass the same security gate as every other image (`scripts/scan-images`).

| Image | Changes (pinned versions live in `images/*/Containerfile`) |
| --- | --- |
| Home Assistant | Alpine package upgrades and hash-pinned Authlib wheel from PyPI (`images/homeassistant/requirements.txt`) |
| OTBR | Debian package upgrades only; upstream tempio and OTBR binaries; `FLOW_CONTROL=0` in `configs/environment/otbr` |
| Papra | Debian package upgrades; affected npm packages replaced with published fixes (`images/patch-node.py`); native esbuild copies rebuilt with current Go (`images/patch-esbuild.py`); `python3` purged after patching; `nonroot` user |
| TREK | KItinerary and `libxml2` removed, so booking-file import is unavailable |

`Build patched application images` runs on every change under `images/` and nightly at 20:47 UTC. The nightly run only rebuilds apps whose deployed image has OS package updates pending (`apk`/`apt`), so quiet nights change nothing. Pull requests changing `images/` build and verify the affected apps without publishing them, which is the check Renovate waits for. Each other run builds the selected apps, runs the smoke checks in `images/verify.sh`, publishes `ghcr.io/jhoogstraat/homelab:<app>-sha-<commit>`, then opens a PR pinning those apps' Quadlets to the new digests and merges it once the host build and image scan pass. A failed check leaves the PR open. Renovate's base image updates in `images/*/Containerfile` therefore reach the Pi without manual steps.

`images/patch-node.py` installs fixed npm versions in place, keeping pnpm/npm paths intact; `images/patch-esbuild.py` replaces every vulnerable native esbuild copy, including pnpm hardlinks, without changing API versions.

Image rollback does not undo database migrations; keep data backups and previous pins.

## Upstream images without a derivative

Matter runs upstream `ghcr.io/matter-js/matterjs-server` (pinned in `quadlets/matter.container`). It uses BlueZ over a read-only `/run/dbus` mount (`NOBLE_BINDINGS=dbus`, `spc_t`). Direct BLE commissioning from the Pi has not worked (HCI `0x3e`); commission through the Home Assistant iPhone app over Thread.
