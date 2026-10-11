# Homelab secret delivery implementation proposal

2026-10-11. This supersedes the candidate integration in [the initial assessment](systemd-creds-research.md). The repository implementation follows this design; it has not been deployed. Live checks below used metadata and disposable dummy-secret probes, without reading production secret contents or mounting application data.

## Decision

Keep SOPS/age as the portable source of truth. Use native systemd credentials for host processes, and private per-application runtime directories for containers. Remove all six applications' secret `EnvironmentFile=` injections. Use application-native file readers where available and one small JSON loader for Papra and homepage. Keep the existing maintenance lock, generation switch, pause/resume recovery and backups.

Do not introduce a secret server, a Podman secret store, host-only encryption of the age identity, or PCR policies in this implementation. The Pi currently cannot use TPM-backed credentials. The remaining root-only persistent recovery inputs and application-owned state still require storage protection against whole-device theft.

## Gaps resolved by evidence

- The live Pi runs systemd **262-3.fc45**, Podman **6.1.3**, and SELinux **Enforcing**. `systemd-analyze has-tpm2` reports partial support, with firmware and driver absent. Libraries being installed is not a usable TPM. `systemd-creds has-tpm2` redirects to the new command.
- Restic is **0.19.1**. The credential parent is root-owned 0700 and the current age key, backup environment and restic password files are root-owned 0600, confirmed without reading their values.
- `/run` is tmpfs; `swapon --show` reported no active swap. Runtime files therefore avoid the current persistent plaintext generations. Preparation must reject disk-backed swap if introduced later, or the memory-confidentiality claim must be revisited; this proposal does not change the machine's swap configuration.
- A transient unit loaded a harmless credential and attempted the previously suggested `:ro,Z,idmap` bind mount. Podman failed with `lsetxattr(...) /run/credentials/.../probe: read-only file system`. Use relabelable per-app runtime directories rather than weakening SELinux or assuming the systemd credential mount is container-compatible.
- Separate root-owned 0700 directories and 0600 files in `/run`, with `:ro,Z,idmap` and explicit UID mappings, were readable in installed Glance and Vaultwarden images and by Papra UID 999. cloudflared UID 65532 reached token parsing and rejected the intentionally invalid dummy token, rather than failing to read it.
- The installed homepage image defaults to root when instantiated without the deployed user override. A second probe explicitly selected UID/GID 1000 and succeeded. The implementation must retain that user explicitly; image defaults are not sufficient.
- A JSON preload probe succeeded as Papra UID 999 and homepage UID 1000, including dollar signs, hash marks, both quote types, newline and backslash. The dummy value was absent from `podman inspect`'s `Config.Env` in both cases. The installed Papra startup is `pnpm start:with-migrations`, and homepage is `bun dist/server/entry.mjs` with Bun 1.4.3.
- Inspection and loading tests are not authentication or restore tests. Full app startup, Beszel hub reconnection, Vaultwarden's persisted configuration precedence and Glance's device-owned YAML migration remain deployment acceptance checks, not unverified design alternatives.

Probe scripts were run from the operator's temporary directory. Temporary container names used `homelab-secret-probe-*` and `homelab-json-probe-*`; the transient unit used `homelab-credential-probe-*`. Probes cleaned their runtime files and containers; the final check found no remaining probe containers or units.

## Runtime layout and preparation

Use one immutable generation for all applications:

```text
/run/homelab/secrets/
  generations/<ciphertext-and-delivery-version-digest>/
    cloudflared/tunnel-token
    vaultwarden/admin-token
    beszel-agent/token
    beszel-agent/key
    glance/adguard-username
    glance/adguard-password
    papra/env.json
    papra/load-env.mjs
    homepage/env.json
    homepage/load-env.mjs
  current -> generations/<digest>
```

The generation root and each app directory are root-owned 0700; secret files are 0600. Keep distinct app copies when two services consume the same source secret. Sharing the same inode between separately labeled `:Z` mounts would undermine their SELinux isolation.

In `scripts/homelab`, extract a narrow generation-staging helper from `prepare()` and reuse `atomic_file()`. Decrypt each SOPS file to JSON through captured stdout, never a shell parser or a persistent plaintext staging file. Require known keys with string values and reject unexpected keys, empty required values and oversize outputs. Write only these app-specific exports:

- cloudflared: `TUNNEL_TOKEN`, exported as raw file content.
- Vaultwarden: `ADMIN_TOKEN`, preserving its existing value/hash bytes.
- Beszel agent: `TOKEN` and `KEY`; `KEY` is the hub's public SSH key, not a private identity.
- Glance: `ADGUARD_USERNAME` and `ADGUARD_PASSWORD`, without the unused password hash.
- Papra JSON: `AUTH_SECRET`, `DATABASE_AUTH_TOKEN`, `DATABASE_ENCRYPTION_KEY`.
- Homepage JSON: the five existing Spotify/Beszel variables.

AdGuard's username/bcrypt hash are used separately for first-install seeding. Validate that seed before publishing a generation, and never overwrite an existing AdGuard configuration. Include an explicit delivery-format version and loader content in the generation digest, so a changed delivery format cannot reuse stale output even when ciphertext is unchanged. Stage everything before atomic publication; a decrypt/validation/write failure leaves the old selection intact. Existing generations should be checked for completeness and permissions before reuse.

`homelab-prepare.service` keeps `RemainAfterExit=yes` and its existing ordering. Add `LoadCredential=age.key:/var/lib/homelab/credentials/age.key`; make the helper use `$CREDENTIALS_DIRECTORY/age.key` in service context. Keep an explicit validated root-only source path for supported direct CLI preparation. A present but broken service credential must fail, not silently fall back to disk. Validate persistent input ownership, regular-file type, symlinks and restrictive permissions before consumers use them. The source age identity remains root-only on disk, and the prepare unit's credential persists while that oneshot unit is active; no short-lived-key claim is made.

## Container changes

Remove the secret `EnvironmentFile=` line from cloudflared, vaultwarden, beszel-agent, glance, papra and homepage. Preserve their ordinary environment files and device-owned settings.

The cloudflared Quadlet becomes, in its existing `[Container]` section:

```ini
Volume=/run/homelab/secrets/current/cloudflared:/run/secrets:ro,Z,idmap=uids=@0-65532-1;gids=@0-65532-1
Exec=tunnel --no-autoupdate run --token-file /run/secrets/tunnel-token
```

Use the same mount pattern for each app, with its own directory. Default container-root apps use `:ro,Z,idmap`; Papra uses UID/GID 999 and homepage 1000. Add `User=1000:1000` to homepage so its tested user does not depend on a persistent drop-in. Preserve the working data-volume ownership/mapping. Do not add `UserNS=auto` to Beszel's existing pod without a separate compatibility change; give its runtime export a private `:ro,Z` mount within the existing pod mapping and test it there.

Set these public configuration values:

```ini
# vaultwarden
Environment=ADMIN_TOKEN_FILE=/run/secrets/admin-token
# beszel-agent
Environment=TOKEN_FILE=/run/secrets/token
Environment=KEY_FILE=/run/secrets/key
# papra: retains the image's pnpm command and migrations
Environment=NODE_OPTIONS=--import=/run/secrets/load-env.mjs
# homepage: retains the image entrypoint
Exec=bun --preload /run/secrets/load-env.mjs dist/server/entry.mjs
```

Ship one `configs/secret-loader.mjs`, copied to each JS app's runtime export directory by preparation:

```js
import { readFileSync } from "node:fs";
const values = JSON.parse(readFileSync(new URL("./env.json", import.meta.url), "utf8"));
for (const [name, value] of Object.entries(values)) {
  if (!/^[A-Z][A-Z0-9_]*$/.test(name) || typeof value !== "string")
    throw new Error("Invalid secret entry");
  if (process.env[name] !== undefined && process.env[name] !== value)
    throw new Error(`Conflicting secret: ${name}`);
  process.env[name] = value;
}
```

Only the preparation allowlist determines `env.json` keys; never include runtime-control variables such as `NODE_OPTIONS` or `BUN_OPTIONS`. Identical inherited values are accepted because Papra's package manager starts child processes with the loader option inherited. Conflicting values fail rather than silently allowing a legacy env file to override a secret. Loader errors identify names, never values. The loader removes Podman metadata exposure, but the app and its children still hold secrets in their environment/memory; it is not protection against application compromise or host root. Preserve any existing nonconflicting `NODE_OPTIONS` after reviewing actual drop-ins.

Change Glance's seed to `${secret:adguard-username}` and `${secret:adguard-password}`. Since deployed YAML is device-owned, migrate only the two exact legacy placeholders in the actual deployed configuration, including relevant includes after inspection; preserve all other bytes/settings. If locally customized references cannot be identified safely, fail the Glance cutover and require a reviewed native-config edit, rather than overwriting it or putting credentials back into container metadata.

Native support sources: [cloudflared token file](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/#token-file), [Vaultwarden file reader](https://raw.githubusercontent.com/dani-garcia/vaultwarden/main/src/util.rs), [Beszel token reader](https://raw.githubusercontent.com/henrygd/beszel/main/agent/client.go), [Beszel key reader](https://raw.githubusercontent.com/henrygd/beszel/main/internal/cmd/agent/agent.go), [Glance secret syntax](https://github.com/glanceapp/glance/blob/main/docs/configuration.md#other-ways-of-providing-tokenspasswordssecrets). These sources establish the contracts; acceptance must use the exact installed/pinned images.

## Maintenance credentials and recovery

Split the device's `backup.env` into nonsecret repository/region/cache settings and `/var/lib/homelab/credentials/s3-credentials`, an AWS shared credentials INI file. Retain the existing restic password file. All persistent input files must be root-owned 0600 with a 0700 parent, validated during provisioning and preparation; generation validation does not replace this check.

Apply identically to `homelab-backup.service` and both update-service drop-ins:

```ini
LoadCredential=restic-password:/var/lib/homelab/credentials/restic-password
LoadCredential=s3-credentials:/var/lib/homelab/credentials/s3-credentials
Environment=RESTIC_PASSWORD_FILE=%d/restic-password
Environment=AWS_SHARED_CREDENTIALS_FILE=%d/s3-credentials
```

Remove the old password path from `backup.env` so it cannot override the unit value, and remove AWS/MinIO key variables from every effective environment source. Use `UnsetEnvironment=AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN MINIO_ACCESS_KEY MINIO_SECRET_KEY` as a final guard against stale injected credentials. Keep all existing timeouts and `ExecStopPost` recovery. Update `configs/backup.env.example` and add a shared-credentials example without actual values. Direct operator restic commands explicitly reference the protected files; the supported unattended path remains systemd.

Make backup/update actions revalidate their required persistent source paths and service credential copies before the first restic call, using the shared credential-path validator. Do not rely on preparation having run previously or `After=homelab.target` implicitly starting it. Source checks use ownership/mode/type metadata; systemd may already have loaded the source, but restic must never run after a validation failure. Direct CLI calls validate the explicitly selected protected files as well.

The current backup already captures the complete `credentials` directory. These portable inputs remain there, so no `/var/lib/systemd/credential.secret` backup dependency is introduced. Runtime generations are reconstructible from SOPS ciphertext and excluded from backups. Retain independent operator recovery copies outside Vaultwarden and the restic repository. Replacement-host recovery restores/provisions these portable inputs before preparation; it never needs the original Pi/TPM.

If TPM hardware is added later, provision `LoadCredentialEncrypted=` inputs with explicit `host+tpm2` on that host, preserve portable recovery separately, and test replacement-host reprovisioning. That is a separate implementation; no automatic downgrade to host-only or null-key protection is allowed. [systemd credential encryption](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd-creds.xml), [restic password-file support](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html), [restic S3 provider ordering](https://raw.githubusercontent.com/restic/restic/master/internal/backend/s3/s3.go)

## Rotation, interruption and retention

Add `rotate-secrets` to the existing helper and a manually activated `homelab-secrets-rotate.service`. It requires the prepared homelab and loads the same age credential. Under the existing maintenance lock, stage and validate the candidate before interrupting apps, then use the existing `pause()`/`resume()` path to briefly restart the previously active managed services. This deliberately reuses the existing cold-maintenance mechanism; optional inactive services remain inactive. Call the staging helper directly; invoking `systemctl restart homelab-prepare` while holding its lock would deadlock.

Save the previous selection, pause, atomically select the candidate, and resume. On an ordinary restart/readiness failure, restore the old selection and recreate the original active services. Keep the existing durable paused-unit intent until recovery succeeds. Set `ExecStopPost=/usr/libexec/homelab resume` for process interruption: it resumes whichever complete generation is selected, not a partial directory. On reboot, `/run` is rebuilt from the booted image before recovery resumes applications; runtime generations cannot provide cross-reboot rollback. Use the pinned prior boot deployment and its ciphertext for that recovery. Decryption/validation failures must block dependent startup rather than start apps without secrets.

The existing `wait_ready()` only checks active state for most secret consumers. It cannot prove credential validity. Full app endpoint/reconnection and token authentication checks remain explicit operator deployment gates before provider revocation; this implementation retains the existing readiness checks and does not claim automated credential-validity rollback. Keep old provider tokens valid during a planned cutover. Revoked tokens cannot be restored by switching a symlink.

Keep the current and one previous runtime generation; prune older generations only after successful recreation and verification that no managed container mounts reference them. On rotation failure, retain both required generations until recovery completes. Root-only runtime files can be removed at reboot. Delete persistent old plaintext generations only after migration and rollback paths have been verified; never delete credential-bearing recovery archives wholesale. Deletion on flash does not guarantee erasure; revoke obsolete provider tokens.

Do not casually rotate Papra's database encryption key or archived applications' encryption material. Those need application-specific migration and matching historical recovery keys. SOPS recipient/age-identity rotation is a separate portable-source operation, with old recovery identities retained for historical ciphertext/backups.

## Concrete change set and rollout

Implement in one focused branch:

1. `scripts/homelab`: credential input validation, runtime generation staging, per-app exports and rotation using existing lifecycle helpers.
2. `configs/secret-loader.mjs` and `Containerfile`: package the shared loader as a preparation input; no image rebuilds or dependency additions for Papra/homepage.
3. The six secret-consuming Quadlets and Glance seed: per-app mounts/file readers; explicit homepage user.
4. Prepare, backup and update units, plus the manual rotation unit: credential sources and consistent recovery behavior.
5. Backup templates and `docs/operations.md`: provisioning, exact Glance migration, manual restic usage, rollback and independent recovery.
6. Existing lifecycle/image tests: runtime permissions, failed generation publication, no unexpected JSON keys, exact loader values, optional-service preservation, failed rotation recovery, and assertions that no secret `--env-file` remains in generated units.

Before rollout, take the existing verified backup and inventory effective local Quadlet/service drop-ins, especially the patched homepage user/image and maintenance helper. Bootc preserves those overrides; editing packaged units alone cannot establish the new delivery path. Keep reviewed old definitions and portable recovery inputs root-only. Stage all required files and the Glance config edit before switching effective definitions, then stop maintenance timers, select the new image/definitions, reload systemd, and restart using captured active-service intent. Restore timers only after the acceptance gates pass.

Deployment acceptance: exact-image file support; generated mount mappings; successful complete reboot; token absence from direct and broker inspection; denied access from an unrelated container/unprivileged host user; missing files/malformed JSON causing failure; Papra migrations and encrypted data still readable; homepage OAuth behavior unchanged; Vaultwarden's existing configuration override precedence reviewed; Beszel authenticated reconnection; Glance authenticated DNS stats; rotation success/failure/interruption; backup and both guarded update paths; isolated restoration using only documented independent recovery material. Probe successes above cover the delivery mechanism only.

Until those gates pass, retain the old deployment and provider tokens. For rollback, stop affected services, restore reviewed old definitions and native app config, reconstruct the old layout with its matching helper/ciphertext, reload systemd and restore the captured active-service set. Prefer reconstructing plaintext from retained SOPS sources over keeping old plaintext indefinitely. Existing image vulnerability/publication blockers remain independent release gates.

## Implementation verification

The implementation passed 39 Linux tests, including real rsync migration, restic backup/restore, JSON loader literal values, malformed inputs, incomplete-generation rejection, rotation rollback, optional-service preservation and mounted-generation retention. Generated Quadlets and complete image validation are additional merge checks. Live authenticated cutover, reboot and recovery gates above remain outstanding; merging is not a claim that the Pi has been migrated.
