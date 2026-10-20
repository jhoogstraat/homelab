# Security remediation — 2026-10-10

## Applied to the Pi

A successful cold backup preceded these changes. The full bootc image has **not** been published or switched; these are inventoried persistent device overrides.

Cold snapshot `488287fc` completed successfully. An isolated restore of its maintenance tree recovered 45.623 MiB; the helper, patched SOPS, broker configuration and both Traefik files match deployed SHA-256 hashes, and the temporary recovery instruction is absent. Final snapshot `a86153fe` also completed successfully and includes the subsequent startup fixes; a separate isolated restore verified all three ordering drop-ins, the corrected weekly timer and time-sync enablement. An earlier retry correctly refused backup when HA exited on SIGTERM during initialization; the successful retry recorded HA exit code 0. Older interim snapshots can contain the temporary manifest: exclude it when restoring, as described in the operations guide.

Two controlled reboots were performed. The second boot (`27f30f12-797a-436b-83c5-861c10646b0c`) held calendar timers behind chrony while its clock advanced by 1,007,776 seconds, then scheduled the next 02:00/03:00/04:00 runs without firing maintenance at startup. HA's cold start exceeded the 120-second probe budget. Reboot also changed Podman's inferred host gateway to the isolated API bridge; explicit aliases to `10.90.0.1` now keep HA/Matter/OTBR routing stable independently of network creation order. All three LAN routes return 200 after Traefik restart. This final 94-byte override is preserved in configuration-only snapshot `e092486e` (tag `homelab-security-config`); restore it alongside full snapshot `a86153fe` when needed. Subsequent full backups include it automatically.

- Application storage and secret-generation parents are root-only. Retired UDP 51820 is removed from runtime and persistent firewall configuration.
- Traefik and Beszel use the restricted HAProxy broker on the internal `podman-api` network. Neither client mounts the rootful socket. The broker has no published port and uses a local HAProxy 3.2 derivative with PCRE2 10.49-r0: zero HIGH/CRITICAL scan findings.
- The homepage runs a tested ARM64 build with Astro 7.3.8, node adapter 11.1.7, esbuild 0.28.2, Bun 1.4.3, refreshed OS packages and UID 1000. Its scan fell from 7 CRITICAL / 150 HIGH to **0 CRITICAL / 55 HIGH**. Static pages/API fallbacks and the live homelab API pass. Spotify returns `invalid_grant` with both old and new runtimes and needs OAuth reauthorization.
- SOPS 3.13.3 was rebuilt from verified commit `26e2f4784ca61353082c32dbd987c25eda086dc9` with patched Go/dependencies. It scans with zero HIGH/CRITICAL findings and decrypts existing device ciphertext without printing plaintext. `homelab-prepare` uses it through a root-owned PATH override. The installed maintenance helper includes the repository permission fixes and backs up the complete persistent maintenance tree, including the broker configuration and patched SOPS. A real restic restore test covers this recovery requirement.
- Vaultwarden's persistent open-registration override is closed. A dedicated unpublished Traefik entrypoint accepts only `vault.hoogstraat.net`; `/admin` returns 403 from the tunnel network. Tests cover ordinary API paths, encoded admin paths and forged forwarded headers. Management routers default to TLS and admit only the local IPv4 subnet, loopback and link-local sources; container bridge traffic and forged forwarded headers are denied. Local HA/vault HTTPS and the public homepage return 200. LAN global IPv6 prefixes must be added explicitly if needed; blanket ULA allowances would also admit the container bridge. Header aliases are stripped.
- Cloudflare exposes `hoogstraat.net` and `vault.hoogstraat.net`, followed by the 404 catch-all. The public vault uses `http://traefik:8080` and a proxied tunnel CNAME; its canonical domain is `https://vault.hoogstraat.net`. Public AdGuard, home, paperless and Grafana routes and matching tunnel CNAMEs are removed. Existing private-CIDR routing is preserved.
- All three maintenance timers remain enabled and active. Maintenance services wait for `homelab.target`; the native bounded `chrony-wait.service` is enabled so calendar timers wait for clock synchronization. The first reboot exposed an 11-day NTP clock correction that triggered all timers during startup. Those jobs were canceled and recovered before validation. The host timer now clears inherited boot/eight-hour triggers and retains only Sunday 04:00; application updates remain daily 03:00, backups daily 02:00. The operator explicitly chose to keep updates enabled and finish maintenance; existing unattended update policy is preserved. Git application definitions pin scanned digests without auto-update labels. Weekly/PR scans fail on CRITICAL findings, scanner errors or any HIGH broker finding; publication uses the same gate. Renovate configuration requests reviewed digest updates when its app is enabled; automerge is disabled.

## Input and access still needed

**Public vault/MFA:** the operator deferred MFA enrollment and explicitly instructed immediate public exposure after being told that the live database had two users and zero MFA records. The public route and canonical domain are now configured. Registration remains closed and public `/admin` remains blocked; native password authentication is available without a login gateway. Verified public HTTPS `/` and `/api/config` return 200, `/admin` and `/%61dmin` return 403, and public DNS is proxied. AdGuard had a private wildcard rewrite for `*.hoogstraat.net`; an exact self-CNAME exception now sends vault queries upstream, so normal LAN DNS also gives valid public HTTPS (200) and admin denial (403). This uses the [documented AdGuard exception](https://github.com/AdguardTeam/AdGuardHome/blob/master/AGHTechDoc.md#example-wildcard-cnamea-record-with-cname-exception). Vault settings and their rollback copy are saved in configuration snapshot `908cf5f1`; AdGuard settings and their rollback copy are saved in `e6bf7ccd` (both tagged `homelab-security-config`). Final verification found all four routing/application services and all three maintenance timers active, no failed systemd units, public vault/API HTTP 200 and public admin HTTP 403. MFA is still outstanding: enable it for both accounts and retain recovery codes privately. Check iPhone login/sync over cellular without a VPN; authenticated sync and notification behavior requires an account-holder test.

**Upstream images:** HA, Matter, Papra and OTBR retain reported CRITICAL findings. Other images and the rebuilt homepage retain HIGH findings. Package findings do not establish reachable exploits. Repository publication is deliberately blocked. Review reachability/publisher fixes before replacing digests or recording narrowly justified exceptions. Fedora RPMs need Fedora-supported advisory coverage; Trivy excludes them. The Fedora 45 prerelease choice is preserved.

**Source retention:** homepage changes are saved in the Pi's root-only `recovery/security-20261010/homepage-source.patch`, with image archives. Apply the patch to homepage commit `1455090529c1987d9dbcb1b363bf8eb1ba924b28`, validate and publish a reviewed image. GitHub's connector returned 403 for branch creation; the local CLI login is invalid. No homepage PR was created. Enable Renovate and require the image-security check in branch protection when repository access permits it.

## Persistent override and recovery inventory

- `maintenance/security-20261010/` under `/var/lib/homelab`: broker/Traefik settings and patched SOPS.
- `/etc/containers/systemd/{socket-proxy.container,podman-api.network}`: local broker definitions.
- `95-security.conf` in `traefik.container.d`, `beszel-agent.container.d`, `beszel.pod.d`, `homepage.container.d` and `vaultwarden.container.d`.
- `/etc/containers/systemd/traefik.container.d/96-host-gateway.conf`: deterministic host-network service routing.
- `/etc/containers/systemd/otbr.container.d/95-otbr-4.2.5-debian.conf`: scanned local OTBR 4.2.5 image ID, `Pull=never`, and explicit `FLOW_CONTROL=0`. Its image archive and scan are retained in `recovery/otbr-upstream-review-20261020/`; stopped data and prior definitions are in `recovery/otbr-4.2.5-20261020T161216/`. Registry publication and the repository image pin update are pending; see [the OTBR review](otbr-upstream-review.md).
- `/etc/systemd/system/homelab-prepare.service.d/95-security.conf`: patched SOPS PATH.
- `95-startup-ordering.conf` in the three maintenance service drop-in directories; `bootc-fetch-apply-updates.timer.d/95-calendar-only.conf`; enabled native `chrony-wait.service`. Timer drop-ins and the time-sync enablement link are included in subsequent backups.
- `recovery/security-20261010/` under `/var/lib/homelab`: prior Quadlets, vault settings/helper, tested image archives and homepage source patch. These root-only files are included in backups.

Local images use `Pull=never`; restore archives with `podman load` **before** starting applications on a replacement host. Once equivalent reviewed registry images are published, replace local references with verified digests and remove only inventoried overrides whose behavior is packaged. Preserve device enablement and settings.

For rollback, stop affected services, restore prior definitions/settings from the archive, reload systemd and restart them. Reverting the broker restores unrestricted socket access; reverting the homepage restores known vulnerabilities. Its Spotify directory now uses UID/GID 1000; restore prior ownership from restic when reverting that runtime. Check compatibility and recovery before resuming automatic updates.

The patched broker was built from this minimal derivative and scanned as a Docker archive before deployment:

```dockerfile
FROM docker.io/library/haproxy:3.2-alpine@sha256:5d97434a423c2533cfeb42874d45cf6d69a840b60334582dfbfd5008e94c80be
USER root
RUN apk upgrade --no-cache pcre2
USER haproxy
```

Package repositories change: verify the installed PCRE2 version, scan the resulting artifact and rerun the API policy tests for every rebuild.
