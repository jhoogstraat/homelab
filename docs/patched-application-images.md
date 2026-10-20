# Patched application images

The ARM64 derivatives in `images/` retain the pinned upstream application versions, startup commands, ports, data mounts and runtime users. They update OS packages and vulnerable runtime dependencies so the existing application security gate can pass without exceptions or ignored findings.

| Image | Changes |
| --- | --- |
| Home Assistant | Alpine updates; rebuild the existing go2rtc 1.9.14 and tempio 2024.11.2 sources using Go 1.27.2; remove unused Nexity-only `warrant-lite` and its unpatched `python-jose` dependency |
| OTBR | Upstream 4.2.5 with Debian updates only; retain upstream tempio and OTBR binaries |
| Papra | Debian updates; replace affected npm packages with published fixes; rebuild esbuild 0.18.20 and 0.25.10 with Go 1.27.2; preserve `nonroot` |
| API broker | Alpine updates, including patched PCRE2; preserve HAProxy 3.2 and the restricted API configuration |

Nexity login support is unavailable in the Home Assistant derivative until its upstream dependency has a reviewed fix. The Pi does not have the Overkiz/Nexity integration enabled. The image still runs `uv pip check`; enabled Home Assistant integrations and core startup must also be validated before deployment.

`Build patched application images` publishes ARM64 artifacts under `ghcr.io/jhoogstraat/homelab:<app>-sha-<commit>`. These staging tags are not deployed automatically. Resolve and scan each exact digest, run compatibility checks, then update its Quadlet pin in a reviewed change. The normal host build and application scan must pass before merge. The scan still rejects unpinned images, scanner errors, critical findings, and any HIGH API-broker finding.

`images/patch-node.py` installs the fixed versions through npm and replaces the existing package directories while keeping pnpm/npm paths intact. New dependencies remain nested inside their package. Regression tests cover npm metadata, module links, and retained native esbuild copies. The esbuild patch replaces every vulnerable native copy, including pnpm hardlinks, while keeping the original API versions.

Retain application data backups and previous pinned images when deploying a derivative. An image rollback does not undo database migrations; these recipes do not change the application versions or migration commands.

Exact Quadlet artifacts were scanned on 2026-10-11 with the repository's pinned Trivy 0.75.0 scanner: all five have zero CRITICAL findings. Remaining HIGH counts are Home Assistant 30, OTBR 97, Papra 156, and the API broker 0. These derivatives meet the existing gate; other applications' HIGH findings remain visible in the full scan report. Matter runs the upstream `ghcr.io/matter-js/matterjs-server:1.5.0` image without a local derivative; on 2026-10-20 it scanned with zero CRITICAL and 59 HIGH findings. ARM64 smoke checks cover Home Assistant version preservation and core/integration imports, OTBR agent paths and template rendering, Papra's native esbuild binaries and migration command, and the broker configuration. Hardware, live integrations and stateful startup still require deployment validation.

Live Matter validation on pi1 on 2026-10-20 confirmed server version 1.5.0, HTTP 200, a successful WebSocket `get_nodes` response retaining all 16 nodes, and zero service restarts. The Pi uses a persistent `/etc/containers/systemd/matter.container.d/95-matter-v1.5.0.conf` image override; its booted bootc image still packages the previous pin. The next bootc build packages the 1.5.0 pin from `quadlets/matter.container`. Varmblixt commissioning remains to be tested.

OTBR 4.2.5 was built and deployed on pi1 on 2026-10-20 with Debian updates only, retaining upstream OTBR/tempio binaries. Its exact local image scans with zero CRITICAL and 94 HIGH findings. Explicit `FLOW_CONTROL=0` preserves the serial radio setting required by the old image. The main-branch application workflow published the 4.2.5 derivative, and `quadlets/otbr.container` pins its verified registry digest. The Pi still uses its tested local-image override and retained recovery archive until host-image cutover. See [the OTBR review](otbr-upstream-review.md) for checks, artifact identity, and rollback.
