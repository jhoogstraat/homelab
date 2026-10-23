# AGENTS.md

Fedora bootc host image for a Raspberry Pi 4 (arm64) running Podman Quadlets. See README.

## Secrets

Application secrets live in Git as SOPS ciphertext: `secrets/<app>.enc.env` (dotenv, age recipient in `.sops.yaml`). Never put a secret in a Quadlet, in `configs/`, or in device-owned files.

Adding a secret:
1. Add the keys to `SECRET_KEYS` and the staged file names to `SECRET_OUTPUTS` in `scripts/homelab`, and map them in `stage_secrets()`. The encrypted file must hold exactly those keys, all non-empty. Otherwise `homelab prepare` fails and no app starts.
2. Create or edit the file with `sops edit secrets/<app>.enc.env`, or `sops set --input-type dotenv secrets/<app>.enc.env '["KEY"]' '"value"'`.
3. Mount `/run/homelab/secrets/current/<app>` at `/run/secrets` (read-only, idmapped to the image user) and point the app at the files (`*_FILE`). Never pass secrets with `EnvironmentFile`/`--env-file`; `tests/verify_image.py` enforces this. Node apps without `_FILE` support use `env.json` with `secret-loader.mjs`.

## Applications

- One Quadlet per app in `quadlets/`, image pinned as `tag@sha256:…`, static IP on `homelab.network`, state in `/var/lib/homelab/apps/<app>/`.
- Public hostnames go through Traefik's `tunnel` entrypoint (`configs/environment/traefik/public-routes.yml`) and a Cloudflare tunnel public hostname pointing at `http://traefik:8080`.
- Every pinned image must scan with 0 fixable critical findings (`scripts/scan-images`, CI `image-security`). No per-image exceptions: patch vulnerable upstream images in `images/<app>/`.

## Checks

`python3 -m unittest discover -s tests -v`. The image and route checks in README need Linux.
