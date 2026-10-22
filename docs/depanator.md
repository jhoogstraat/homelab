# Depanator on pi1

Depanator runs as `depanator.service`, a rootful Podman Quadlet in
`homelab.target`. The image includes Bun and Codex; setup and review happen in
Telegram. The image is pinned in [the Quadlet](../quadlets/depanator.container);
updates change that digest.

Searches run on the configured interval, with a 22:00–07:00 Europe/Berlin night
pause by default. The first successful search after startup, resume or a search
change only records a baseline; later arrivals become review candidates.

## State and access

- `/var/lib/homelab/apps/depanator/data` mounts at `/data`:
  - `agent.db`: settings, Telegram pairing, listing history and outcomes.
  - `telegram-offset.json`: consumed Telegram updates.
  - `is24-session.json`: renewable IS24 login (password and code are not kept).
  - `codex/auth.json`: ChatGPT OAuth tokens, renewed by Codex; no API key.
- The Telegram bot token is SOPS-encrypted in `secrets/depanator.enc.env` and
  delivered like other app secrets at
  `/run/homelab/secrets/current/depanator/telegram-bot-token`, read through
  `TELEGRAM_BOT_TOKEN_FILE`.
- Idmapped mounts map host UID/GID 0 to the image UID/GID 1000. Keep the app
  tree root-owned and private.
- Public Mini App: `https://trek.hoogstraat.net/depanator/connect`, a dedicated
  Traefik router for `/depanator/` on the tunnel entrypoint. Private LAN
  endpoint: `https://depanator.hoogstraat.de/connect`. No host port.

The connect page is static; connection actions require fresh Telegram-signed
data from the paired owner. IS24 credentials are forwarded once and not stored.

## Operations

Use `systemctl status depanator` and `journalctl -u depanator`. The health
command checks the poll heartbeat; failures kill the container and systemd
restarts it. Stop timeout is 40 seconds; shutdown drains work for up to 30.
`sudo /usr/libexec/depanator status` runs the image's status command against
the stopped service's data.

## Backup and restore

Backups stop the agent and capture the whole app directory. After any restore, run
`sudo /usr/libexec/depanator restore-gate` before starting the service. It
writes `data/reconciliation-required`, which blocks startup and submission.
Reconcile IS24 contact history and stale approvals, then remove the marker.
Image rollback does not roll back database state.
