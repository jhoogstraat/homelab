# OTBR upstream image review — 2026-10-20

Candidate: `ghcr.io/wittdennis/homeassistant-otbr:4.2.5`, ARM64 manifest
`sha256:db85eb8a1f76aba121ab509ec53a7cb169139748295119d1a6604e1a6640d7a8`.
Image config: `sha256:93ce3a1bc66a55275b147e76299c3916cb6681b51d75836c5ede9c075ffe29bb`.

Before this upgrade, the derivative used the older major-3 image, applied Debian
package updates, and rebuilt tempio 2024.11.2 with Go 1.27.2. At the start of
review, the Pi's only OTBR Quadlet drop-in was `20-device-enable.conf`, which
enables the service and must remain.

## Compatibility checks

- Upstream 4.2.5 uses Home Assistant OTBR 3.2.0 and promotes Thread 1.4 to
  stable through its major-4 release.
- The serial device, baud rate, backbone interface, `/data/thread` storage,
  REST port 8081, and configured web port 7070 are supported.
- Stable and beta agent binaries exist under `/opt/otbr-{stable,beta}/sbin`;
  startup selects the active binaries under `/usr/sbin`.
- An offline ARM64 smoke check executed the stable agent
  (`0.3.0-337711e7`) and rendered a template with tempio 2026.07.0.
- Live verification of the Debian-patched candidate is recorded below.

## Security gate

Trivy 0.75.0, pinned to the repository scanner digest, scanned both the tag and
the exact ARM64 manifest with identical results: **3 CRITICAL, 159 HIGH**.
The reports identify the same image config as the pulled image.

All three critical findings affect Debian `perl-base` 5.40.1-6 and have the
published fix 5.40.1-6+deb13u1:

- CVE-2026-13221
- CVE-2026-42496
- CVE-2026-8376

The high findings comprise 134 Debian, 2 Python aiohttp, and 23 tempio Go
dependency/runtime findings. Upstream tempio uses Go 1.26.5 and
`golang.org/x/crypto` v0.31.0. Using upstream tempio without a rebuild would retain these findings, although
HIGH findings alone do not block this repo's OTBR publication gate.

The unmodified upstream image fails the existing zero-critical publication
gate. A derivative applying Debian updates remains necessary to pass that
gate unless a newer upstream artifact fixes these packages.

Full tag and pinned-digest reports are stored root-only on pi1 under
`/var/lib/homelab/recovery/otbr-upstream-review-20261020/`.

Sources: [release notes](https://github.com/wittdennis/homeassistant-otbr/blob/4.2.5/CHANGELOG.md),
[build recipe](https://github.com/wittdennis/homeassistant-otbr/blob/4.2.5/Dockerfile),
[agent startup](https://github.com/wittdennis/homeassistant-otbr/blob/4.2.5/rootfs/etc/s6-overlay/s6-rc.d/otbr-agent/run),
[web startup](https://github.com/wittdennis/homeassistant-otbr/blob/4.2.5/rootfs/etc/s6-overlay/s6-rc.d/otbr-web/run).

## Debian-only derivative and live deployment

The operator selected the minimal Debian patch. `images/otbr/Containerfile`
now uses the pinned upstream 4.2.5 ARM64 image and only runs Debian package
updates. The Go build stage and replacement tempio binary were removed.

The ARM64 build on pi1 is tagged
`localhost/homelab-otbr:4.2.5-debian-20261020`, with immutable local image ID
`f85f232dc632711263adc9888357ea0ac5845389155a85304b3aaf98d0224b08`.
Its scan reports **0 CRITICAL, 94 HIGH**. `perl-base` is
5.40.1-6+deb13u1. Both agent binaries and tempio have the same SHA-256 hashes
as upstream, and the template smoke check passes. Remaining HIGH findings
are accepted for this Debian-only upgrade; the existing publication gate
still applies to future builds.

The first live attempt failed radio initialization because upstream now
uses `${FLOW_CONTROL:-1}`, whereas the old image used disabled flow control
when the variable was absent. The guarded deployment restored the old image
and stopped-data backup, and verified the old router reattached. The retry
sets `FLOW_CONTROL=0` explicitly, preserving the previous working behavior.
This setting is also recorded in `configs/environment/otbr/otbr.env`.

The retry joined the Thread network, progressed to the router role, and passed
REST port 8081 and web port 7070 probes. The active dataset before and after is byte-for-byte identical.
The unit was active with zero restarts. Home Assistant HTTP returned 200; the
Matter WebSocket API retained 16 nodes, with 15 available. The unavailable
Hallway Switch (node 93) already had a peer timeout at 15:44, before this OTBR
upgrade. Pre-upgrade data and definitions are
stored in `/var/lib/homelab/recovery/otbr-4.2.5-20261020T161216/`.

The Pi uses `/etc/containers/systemd/otbr.container.d/95-otbr-4.2.5-debian.conf`
to select the exact local image ID with `Pull=never` and set `FLOW_CONTROL=0`.
Keep the device enablement drop-in. Registry publishing credentials were not
available, so the image has not been published and `quadlets/otbr.container`
retains the previous pullable registry pin. The booted bootc image is unchanged.
The updated recipe will build through the existing application-image workflow;
resolve and scan the published artifact, then replace the repository pin and
remove the local image override after a host image packages the new pin/settings.
Do not remove the override before that cutover.

The image archive `otbr-4.2.5-debian.tar`, build recipe/log, and
`scan-debian-patched.json` are retained in the root-only review directory above.
To restore on another host, load the image archive before restoring this
`Pull=never` override. For rollback on pi1, stop OTBR, remove only
`95-otbr-4.2.5-debian.conf`, preserve the new data separately, restore the
saved `data.tar`, reload systemd, and start OTBR. Verify Thread attachment and
network identity before resuming use. The old registry image remains available
locally.
