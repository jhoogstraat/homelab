# Depanator

The system Quadlet belongs to `homelab.target`, with a digest-pinned ARM64 image and container UID/GID 1000. Startup is skipped until personal setup creates configuration and staged secrets. Host configuration/data live under `/var/lib/homelab/apps/depanator`; idmapped mounts preserve root-owned private files across setup, login and runtime namespaces. Container paths remain `/config` and `/data` because paths participate in approval bindings.

## Setup

Create a dedicated Telegram bot with BotFather (`/newbot`). Have its token, your filtered IS24 search URL, preferences and actual contact details ready. On the Pi:

```sh
sudo /usr/libexec/depanator setup
sudo /usr/libexec/depanator llm-login
sudo systemctl start depanator.service
```

With persistent deployment overrides, use `/var/lib/homelab/maintenance/depanator` instead; it must sit beside the reviewed `homelab` helper. The pinned image must already be pulled. Choose `codex`, leave viewer URL blank for the default LAN URL, enter the token privately, send `/start` to your bot, and confirm the discovered private chat. Save the displayed viewer password privately.

Wizard plaintext lives temporarily under memory-backed `/run/homelab` and is removed. Bot/viewer values are encrypted using the homelab age recipient into `/var/lib/homelab/device-secrets/depanator.enc.env` with a root-owned 0700 parent. Chat ID stays in configuration. Optional device ciphertext takes precedence over packaged Depanator ciphertext; absence does not affect existing apps. Secrets stage into `/run/homelab/secrets/current/depanator` as raw-value files. Native `_FILE` inputs keep values out of Podman metadata. No API key is needed.

`llm-login` prints the ChatGPT device link/code; authorize on your phone. Enable device-code login in ChatGPT security settings if required. Login persists under `/data/codex`. Never commit or share credential files/browser profiles.

Open `https://depanator.hoogstraat.de/vnc.html` on home Wi-Fi, enter the viewer password, sign into the configured IS24 account and close Chromium. Identity verification then resumes the agent. Traefik routes directly over `homelab.network`, with existing LAN restrictions and TLS. No host viewer port or public tunnel route is exposed. Remote access requires separately configured authenticated HTTPS covering page and WebSockets.

## Backup and restore

The maintenance inventory includes `/etc` and `/usr` Quadlets. The service gets a 40-second Podman stop timeout and 60-second systemd teardown timeout, exceeding the app's 30-second deadline. Failed/forced stops refuse backup. Readiness checks the internal viewer after restarting. Backups include the entire stopped data directory (SQLite/WAL, browser profile/HOME, Telegram offset, Codex auth) and encrypted device secrets. Memory is capped at 2 GiB with 256 MiB shared memory; measure consumption after live login.

Stop the service before setup/login/status maintenance. After restoring historical data, with writers and maintenance timers stopped, run **before any start/resume**:

```sh
sudo /usr/libexec/depanator restore-gate
sudo /usr/libexec/depanator status
```

The marker `/data/reconciliation-required` blocks startup and sending. Compare restored reviews/approvals with IS24 contact history and repair already-sent/stale entries. Remove the marker deliberately only after reconciliation, then start explicitly. Restore success alone is not reconciliation. The helper never removes the marker; interrupted submissions stay `unknown_outcome` without automatic retry.

Take a successful backup before changing the pinned image digest. Keep container paths and mappings stable. All maintenance commands hold the homelab maintenance lock.
