# Depanator on pi1

Depanator runs as `depanator.service`, a rootful Podman Quadlet in
`homelab.target`. The image includes Bun and Codex; setup and review happen in
Telegram. The previous browser/VNC setup helper is obsolete for this image.

The multi-architecture image is published as `ghcr.io/jhoogstraat/depanator:latest`,
from merged main commit `a4ddf1afc7d618be504ec4f934512be6257ff62a`, and pinned to
`sha256:634c406254bb4657053edb59ad90f98affaaa26fba4aa01006151ed54572d06e`.
CI published both ARM64 and AMD64 after the application checks passed. This release
preserves the Telegram setup and scheduled searches, and deletes a listing message
when Dismiss is tapped (including tracked split messages).
`Pull=missing` uses the local image once available. The `latest` tag is pinned to the
verified digest; Renovate can propose digest updates, which require review. Merely
publishing a new `latest` does not change the running Pi image. Registry auto-update
is disabled.

On 2026-10-20 the Pi pulled this digest and restarted successfully. The running
image revision, application heartbeat, public connect page (HTTP 200), and first
completed search were verified. The previous unit and a stopped-state app backup
are retained at `/var/lib/homelab/recovery/depanator-before-a4ddf1a`.

Searches run on the configured interval, with a 22:00–07:00 Europe/Berlin night
pause by default. Manual searching has been removed. The first successful
search after startup, resume or changing the search only records a baseline;
only later arrivals become review candidates. Pending typed criteria prompts
survive restarts. Explicit swap-only offers are dismissed when excluded by the
criteria; ordinary rentals do not need a no-swap declaration.

## State and access

- `/var/lib/homelab/apps/depanator/data` mounts at `/data`: SQLite history and
  settings, IS24 renewable login, Telegram offset and Codex login.
- `config/bot-token` mounts read-only at `/run/secrets/bot-token` and is consumed
  through `TELEGRAM_BOT_TOKEN_FILE`. Keep it root-owned with mode 0600.
- Idmapped mounts map host UID/GID 0 to the image UID/GID 1000. Preserve private
  ownership and permissions; do not apply blanket ownership changes to apps.
- Public Mini App: `https://trek.hoogstraat.net/depanator/connect`. A dedicated
  Traefik router matches only `/depanator/` on the existing tunnel entrypoint.
  Other TREK paths keep their existing router. No new host port is published.
- Private LAN endpoint: `https://depanator.hoogstraat.de/connect`.

The static connect page is public; connection actions require fresh
Telegram-signed data from the paired owner. Credentials are forwarded once to
IS24 and are not stored. Other changes and reconnects use the Telegram bot.

## Operations and recovery

Use `systemctl status depanator` and `journalctl -u depanator` for diagnostics.
The native health command checks the poll heartbeat. Health failures kill the
container so systemd restarts it. Stop timeout is 40 seconds; application
shutdown drains work for up to 30 seconds. Startup is automatic through
`homelab.target`.

The hardened homelab maintenance helper includes local Quadlets, stops the
agent during backup and checks its heartbeat after resuming. Its current
readiness probe must use `/usr/local/bin/depanator-entrypoint health`, rather
than the retired VNC endpoint.

The latest stopped Mac state was migrated on 2026-10-19; it contains 101 known
listings (26 dismissed, 75 existing). The retired Mac data has a `reconciliation-required` marker to prevent
accidentally running both copies. Keep the Mac agent stopped after cutover.
The previous Pi unit and maintenance helper are archived under
`/var/lib/homelab/recovery/depanator-before-20261019`.

Back up the complete stopped app directory. Before starting after a historical
restore, create `data/reconciliation-required`, reconcile IS24 contact history
and stale approvals, and remove the marker only after that reconciliation.
The marker blocks startup and submission. Normal image rollback does not roll
back database state. Do not run the previous setup/VNC helper against this
version's data.

## Secrets and state provenance

The current Pi state was copied from the latest stopped Mac agent at
`.depanator/live`, using a consistent SQLite backup. The Pi is now the live
source of state; it does not synchronize with Git or the retired Mac copy.

- BotFather issued the Telegram bot token, previously held at
  `~/.config/depanator/bot-token` on the Mac. The Pi stores it at
  `/var/lib/homelab/apps/depanator/config/bot-token` and mounts it read-only.
- ChatGPT device login created `data/codex/auth.json`, holding OAuth login and
  renewal tokens. Codex renews these on the Pi; no API billing key is used.
- Connecting IS24 created `data/is24-session.json`, holding a renewable login.
  The IS24 password and security code are not retained.
- `data/agent.db` contains personal settings, Telegram pairing, listing history
  and application outcomes. `data/telegram-offset.json` tracks consumed updates.

Those paths are relative to `/var/lib/homelab/apps/depanator` unless absolute.
Credential files and the database are root-owned, mode 0600, inside private
app directories. The host copies are ordinary files, not SOPS ciphertext.
The existing homelab encrypted restic backup is configured to include this app tree; its
repository credentials are provisioned independently under
`/var/lib/homelab/credentials`. No credential values or runtime state are
committed to either repository.
