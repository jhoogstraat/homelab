# Patched application images

The ARM64 derivatives in `images/` keep the pinned upstream application versions, startup commands, ports, data mounts and runtime users. They replace vulnerable OS packages or runtime dependencies so they pass the same security gate as every other image (`scripts/scan-images`).

| Image | Changes |
| --- | --- |
| OTBR | Upstream 4.2.5 with Debian updates only; upstream tempio and OTBR binaries; `FLOW_CONTROL=0` in `configs/environment/otbr` |
| Papra | Debian updates; affected npm packages replaced with published fixes; esbuild 0.18.20 and 0.25.10 rebuilt with Go 1.27.2; `nonroot` user |
| API broker | HAProxy 3.2 Alpine with package upgrades (patched PCRE2); restricted API configuration unchanged |
| TREK | Upstream 4.3.4 with `proxy-addr` 2.0.8 and `dompurify` 3.4.17 (registry SHA-512 verified); KItinerary and libxml2 removed, so booking-file import is unavailable |

`Build patched application images` publishes ARM64 artifacts as `ghcr.io/jhoogstraat/homelab:<app>-sha-<commit>`. These tags are not deployed automatically: resolve and scan the exact digest, run the smoke checks in `images/verify.sh`, then update the Quadlet pin in a reviewed change. TREK's Quadlet and route follow once its image is published.

`images/patch-node.py` installs fixed npm versions in place, keeping pnpm/npm paths intact; `images/patch-esbuild.py` replaces every vulnerable native esbuild copy, including pnpm hardlinks, without changing API versions.

Image rollback does not undo database migrations; keep data backups and previous pins.

## Upstream images without a derivative

Home Assistant runs the official image pinned in `quadlets/homeassistant.container`.

Matter runs upstream `ghcr.io/matter-js/matterjs-server:1.5.0`. It uses BlueZ over a read-only `/run/dbus` mount (`NOBLE_BINDINGS=dbus`, `spc_t`). Direct BLE commissioning from the Pi has not worked (HCI `0x3e`); commission through the Home Assistant iPhone app over Thread.
