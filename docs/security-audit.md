# Security posture and limits

This is not a penetration test, and the deployment is not security-clear. Current controls and known residual risks:

## Controls

- **Podman API:** Traefik and Beszel reach the rootful socket only through the HAProxy broker on the internal `podman-api` network: GET discovery/inspection/stats/events and GET/HEAD ping only; mutation, exec, logs, archive, image and Libpod paths are denied. No host port. The broker has a read-only root filesystem, no capabilities and no new privileges.
- **Proxy:** normal backend TLS verification, INFO logging to the journal. Management routers require TLS and admit only the local IPv4 subnet, loopback and link-local; forwarded-header aliases are stripped. LAN global IPv6 prefixes must be added explicitly if needed.
- **Public exposure:** Cloudflare publishes `hoogstraat.net`, `vault.hoogstraat.net`, `trek.hoogstraat.net` (TREK plus Depanator's `/depanator/` path) and `brain.hoogstraat.net` (second-brain MCP, GitHub OAuth or bearer token); everything else hits a 404 catch-all. Vaultwarden and Depanator use Traefik's unpublished `tunnel` entrypoint. Public Vaultwarden `/admin` (including encoded variants) returns 403; registration is closed.
- **Secrets:** only SOPS ciphertext enters the image. Runtime secrets are private per-app files in memory-backed `/run`; preparation refuses disk-backed swap. Host maintenance uses systemd credentials. Application, credential and secret parents are root-only 0700.
- **Defaults:** Vaultwarden and Papra disable open registration; AdGuard seeds a 20 queries/s rate limit; Papra seeds a 25 MiB upload limit. Existing device config can override seeds.
- **CI:** actions pinned to commit IDs; every Quadlet image gets the same scan (`scripts/scan-images`), no per-image exceptions; publication blocks on scanner errors, unpinned images and CRITICAL findings a change introduces relative to the last published host image. Findings in already-deployed images are reported but never hold back an update; the weekly `Image security` run fails when any of them has a fix, as a reminder to repin.

## Remaining risks

1. **Image findings:** images retain HIGH and unfixed CRITICAL findings; they are reported, not blocking. Findings are package advisories, not proven exploits. Trivy does not cover Fedora RPMs, so the host has no advisory scan.
2. **Trusted broker and metadata:** compromise of the broker grants rootful API access. Container inspection exposes environment metadata to its clients; Beszel's hub shares its agent's pod. The allowlist disables Beszel container logs, image-update inspection and control actions.
3. **Hardware privilege:** Home Assistant, Matter and OTBR use host networking and device access; Home Assistant and Matter run as `spc_t` (Matter for BlueZ over D-Bus). `wpan0` in the public zone forwards the whole LAN into the Thread mesh, not just Matter ports.
4. **Accounts and remote state:** Cloudflare routes/Access, router forwarding, DNS, Cockpit accounts, MFA and credential strength live outside Git. Public Vaultwarden relies on password authentication; enable MFA for every account. `jh` is a trusted SSH-key administrator with passwordless sudo; root and password SSH login are disabled.
5. **Persistent `/etc`:** local Quadlets/drop-ins override image defaults and survive updates; inspect them before relying on Git. Removing ciphertext from Git does not revoke provider tokens.
6. **Secrets at rest:** root and each consuming app can read its secrets. Recovery inputs (age key, restic password, S3 credentials) are persistent root-only files and need protection against device theft.
7. **Recovery:** the cold backup stops applications for the full upload. Independent copies of backup credentials, remote storage protection and periodic restore drills remain required.
8. **Host release:** the Fedora 45 base was adopted as a prerelease; check its release status before treating it as supported.
