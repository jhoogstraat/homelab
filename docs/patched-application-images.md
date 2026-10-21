# Patched application images

Home Assistant uses the official upstream ARM64 image, without a local derivative.

The other ARM64 derivatives in `images/` retain the pinned upstream application versions, startup commands, ports, data mounts and runtime users. They update OS packages and vulnerable runtime dependencies so the existing application security gate can pass without exceptions or ignored findings.

| Image | Changes |
| --- | --- |
| Home Assistant | Official upstream 2026.10.2 image; no custom build or dependency changes |
| OTBR | Upstream 4.2.5 with Debian updates only; retain upstream tempio and OTBR binaries |
| Papra | Debian updates; replace affected npm packages with published fixes; rebuild esbuild 0.18.20 and 0.25.10 with Go 1.27.2; preserve `nonroot` |
| API broker | Alpine updates, including patched PCRE2; preserve HAProxy 3.2 and the restricted API configuration |

`Build patched application images` publishes ARM64 artifacts under `ghcr.io/jhoogstraat/homelab:<app>-sha-<commit>`. These staging tags are not deployed automatically. Resolve and scan each exact digest, run compatibility checks, then update its Quadlet pin in a reviewed change. The normal host build and application scan must pass before merge. The scan rejects unpinned images, scanner errors, critical findings outside the explicitly accepted official Home Assistant digest below, and any HIGH API-broker finding. All findings remain visible in the report.

`images/patch-node.py` installs the fixed versions through npm and replaces the existing package directories while keeping pnpm/npm paths intact. New dependencies remain nested inside their package. Regression tests cover npm metadata, module links, and retained native esbuild copies. The esbuild patch replaces every vulnerable native copy, including pnpm hardlinks, while keeping the original API versions.

Retain application data backups and previous pinned images when deploying a derivative. An image rollback does not undo database migrations; these recipes do not change the application versions or migration commands.

The previous derivative Quadlet artifacts were scanned on 2026-10-11 with the repository's pinned Trivy 0.75.0 scanner: all five have zero CRITICAL findings. Remaining HIGH counts are Home Assistant 30, OTBR 97, Papra 156, and the API broker 0. At that time these derivatives met the existing gate; other applications' HIGH findings remain visible in the full scan report. Matter runs the upstream `ghcr.io/matter-js/matterjs-server:1.5.0` image without a local derivative; on 2026-10-20 it scanned with zero CRITICAL and 59 HIGH findings. ARM64 smoke checks cover OTBR agent paths and template rendering, Papra's native esbuild binaries and migration command, and the broker configuration. Hardware, live integrations and stateful startup still require deployment validation.

## Matter commissioning on pi1

The live server runs Matter.js 1.5.0, matching the repository's exact image pin. On 2026-10-21, the Home Assistant iPhone app successfully commissioned the IKEA VARMBLIXT on the existing `ha-thread-265c` network after repairing LAN-to-Thread forwarding. All 17 saved nodes were retained, with 16 online including the lamp; the ESP32-C6 light switch was already offline. See [the forwarding diagnosis, validation and rollback](thread-forwarding.md).

The onboard BCM4345C0 controller was also missing firmware: it reported build 0000 and a placeholder address. Loading the verified Raspberry Pi firmware restored build 0382 and the real controller address. The next bootc image packages that same artifact and license, with a digest check in `tests/verify_image.py`. See [firmware provenance and boot verification](../configs/firmware/README.md). The live firmware load was temporary; the Pi has not yet booted the rebuilt host image.

The approved live D-Bus backend configuration is now also in `quadlets/matter.container`: `NOBLE_BINDINGS=dbus`, a read-only `/run/dbus` mount, Bluetooth service ordering, and `SecurityLabelType=spc_t`. The normal container label blocked BlueZ access with `EACCES`; `spc_t` allowed it. This broadens Matter's SELinux access, and a read-only socket mount does not restrict D-Bus method calls. These settings preserve the tested live configuration; they are not evidence that direct Pi Bluetooth commissioning works.

After the firmware repair, direct BLE attempts still failed during remote-feature discovery with HCI `0x3e` (`Connection Failed to be Established`). A direct BlueZ `Device1.Connect` reproduced the failure without Matter. Successful commissioning used the Home Assistant iPhone app; a successful direct server BLE retry has not been demonstrated. Runtime logging is back at info and diagnostic captures are stopped.

The Pi retains `/etc/containers/systemd/matter.container.d/95-matter-v1.5.0.conf` and `96-bluetooth-dbus.conf` from the live investigation. The repository now includes their effective settings. To undo only the live D-Bus experiment, remove `96-bluetooth-dbus.conf`, run `systemctl daemon-reload`, and restart `matter.service`; preserve the image override and application data. Revert the corresponding Quadlet settings too if rolling back a rebuilt bootc image.

OTBR 4.2.5 was built and deployed on pi1 on 2026-10-20 with Debian updates only, retaining upstream OTBR/tempio binaries. Its exact local image scans with zero CRITICAL and 94 HIGH findings. Explicit `FLOW_CONTROL=0` preserves the serial radio setting required by the old image. The main-branch application workflow published the 4.2.5 derivative, and `quadlets/otbr.container` pins its verified registry digest. The Pi still uses its tested local-image override and retained recovery archive until host-image cutover. See [the OTBR review](otbr-upstream-review.md) for checks, artifact identity, and rollback.

## Official Home Assistant image and accepted findings

The user explicitly chose the official Home Assistant image on 2026-10-21 and accepted its security findings instead of maintaining a custom build. The custom-build PR #18 was closed and its build cancelled. The recipe and workflow matrix entry have been removed so future application-image builds cannot rebuild Home Assistant.

`quadlets/homeassistant.container` pins upstream release 2026.10.2, published on 2026-10-16, to its exact Linux/ARM64 manifest:

```text
ghcr.io/home-assistant/home-assistant:2026.10.2@sha256:1edf9ce6c140826cdfcd6358802cf3466e38045cd7ed62ccf42c78980ff937ae
```

`scripts/scan-images` continues scanning and reporting that image, but accepts its CRITICAL findings for this exact pin only. Changing the pin requires a new review of that acceptance. Scanner errors, unpinned images, other applications' CRITICAL findings, and any HIGH API-broker finding still block publication. No package metadata or dependencies are patched. Official integrations, including Nexity, are retained.

The exact official digest scanned on 2026-10-21 with the repository's pinned Trivy 0.75.0: **6 CRITICAL and 172 HIGH findings**, accepted as directed. The critical entries are CVE-2026-60002 in three OpenSSH packages, CVE-2026-85394 in python-jose, and CVE-2025-68121 in each of the go2rtc/tempio Go runtimes. The full scan remains available in CI output. This acceptance does not mean those vulnerabilities were fixed.

The preceding bootc build from main commit `49c539d` passed its ARM64 host and Quadlet checks, but publication was blocked by newly reported Home Assistant findings. The previous firmware-only host image remained published; that failed run did not publish the forwarding repair. The final reconciled build must pass the updated explicit policy before being published.
