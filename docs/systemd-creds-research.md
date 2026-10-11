# systemd credentials research — 2026-10-11

Follow-up: [the concrete implementation proposal](secrets-implementation-plan.md) resolves the candidate container-mount approach with live dummy-secret tests and records deployed versions, TPM capability, application delivery contracts and recovery decisions. In particular, direct `:Z` mounts of systemd credentials fail because their source is read-only; use private per-app runtime exports instead.

The requested [rendered manual](https://www.freedesktop.org/software/systemd/man/latest/systemd-creds.html) returned HTTP 403. Findings use its official upstream source and complementary first-party documentation. This is analysis; no live configuration or secret values were accessed.

## Runtime delivery

`LoadCredential=` copies a source file/socket into a read-only credential for the service; the original need only be readable by the manager. Service code uses `$CREDENTIALS_DIRECTORY/name` or `%d/name`. Access includes the service user and root; this does not defend against a compromised host administrator. The per-unit total limit is 1 MB. `LoadCredentialEncrypted=` decrypts/authenticates before launch and fails activation on invalid ciphertext. Prefer explicit absolute sources for required credentials: name-only lookup tolerates absence, and `ImportCredential=` skips decryption failures. Avoid plaintext `SetCredential=` and unit `Environment=` secrets. [systemd.exec upstream manual](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.exec.xml)

Credentials are immutable during a service activation and released at shutdown. Rotation consequently needs service restarts. Memory backing is unswappable when supported; mount namespaces isolate credential directories, with `PrivateMounts=` suggested for native services. Moving a secret back into application environment variables sacrifices the file-delivery advantage. [System and Service Credentials](https://systemd.io/CREDENTIALS/)

## Encryption and recovery

AES256-GCM credentials support `host`, `tpm2`, and `host+tpm2`. The host key is `/var/lib/systemd/credential.secret`; the combined mode requires that key and the original TPM. `auto` chooses available protection and excludes TPM in containers; explicitly select `host+tpm2` when both must be required. **TPM encryption defaults to no PCR binding.** Hardware binding alone does not enforce a trusted boot state. Fixed PCR policies depend on current measurements; signed PCR policies permit approved updates. Purpose-specific `--name=` prevents unnoticed credential repurposing. Null-key encryption offers no confidentiality/authenticity. Expiry checks use the system clock. v262 TPM ciphertext gains SRK pinning and is incompatible with older systemd releases. [systemd-creds upstream manual](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd-creds.xml)

Inference: host-only encryption adds little against theft of the complete filesystem containing its key. Preserve independent SOPS recovery before hardware binding; restoring combined-mode ciphertext alone onto a replacement Pi cannot recover it. Evaluate boot measurements and firmware/bootc update/rollback behavior before PCR binding. Inspect installed systemd and TPM capabilities before choosing a policy.

## Quadlet boundary

Quadlet passes `[Service]` options through to generated units. `[Container] Volume=` maps bind mounts; `Secret=` uses Podman secrets, a separate mechanism. Thus a systemd credential given to the Podman unit does not inherently appear in the application's container. Rootless Quadlets require their own user search paths; systemd `User=`/`DynamicUser=` does not turn a rootful Quadlet into a rootless one. [Podman Quadlet manual](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html)

Candidate integration, requiring a harmless dummy-secret test on the deployed versions:

```ini
[Service]
LoadCredential=example:/run/homelab/current/example

[Container]
Volume=%d/example:/run/secrets/example:ro
```

Verify generated unit expansion, container UID readability, SELinux labels, fresh credential mounts on restart, absence from container environment/inspection, and continued startup ordering. Do not blanket-disable SELinux to make a credential mount work. Begin with native maintenance services before container adoption.

## Version floor

Basic service credentials arrived in v247; encrypted credentials, `systemd-creds`, `LoadCredentialEncrypted=`, and `SetCredentialEncrypted=` arrived in v250. [systemd v250 release notes](https://raw.githubusercontent.com/systemd/systemd/v250/NEWS)

Latest upstream documentation may describe capabilities unavailable in the deployed image. The deployed systemd/Podman versions and successful reboot/restore/rotation exercises are acceptance evidence; the current documentation alone is not.

## Homelab assessment

Keep SOPS as the portable, Git-managed source of truth. Add systemd credentials at the device delivery boundary where they remove persistent plaintext or environment exposure. Do not replace all SOPS ciphertext with host-bound blobs in Git: each replacement device would otherwise need its own provisioning, and image builds cannot use a device's TPM.

### Existing strengths and concrete gaps

- Only SOPS ciphertext enters the host image ([Containerfile](../Containerfile)). The age identity is checked for owner and restrictive permissions; preparation decrypts a complete generation before atomically selecting it, preserving the previous selection on failure ([prepare](../scripts/homelab#L94)). Preserve those properties.
- Decrypted generations are written under `/var/lib/homelab/secret-sets`, selected through `/var/lib/homelab/secrets`, and never pruned by preparation. Old token values remain readable to root and to someone who obtains the unencrypted filesystem, even after a newer generation is selected. Deleting old files is not reliable forensic erasure on flash; revoke retired provider tokens as well.
- cloudflared, Vaultwarden, Beszel, homepage, Papra and Glance receive secret dotenv files through Quadlet `[Container] EnvironmentFile=`. This becomes Podman `--env-file`, placing values in container environment metadata. The broker permits `/containers/<id>/json`, so allowed monitoring clients are inside this secret trust boundary ([broker policy](../configs/environment/socket-proxy/haproxy.cfg#L19), [existing audit](security-audit.md)). Merely sourcing an env file from `%d` does not remove this exposure. [Quadlet environment documentation](https://docs.podman.io/en/latest/markdown/podman-container.unit.5.html#environmentfile-file)
- Backup and update services load S3 access keys from the same plaintext `backup.env`; the restic password already uses a file. Preparation validates the age key, but it does not similarly validate backup-file ownership/mode before systemd consumes them. Provisioning currently relies on the documented permissions ([backup template](../configs/backup.env.example), [operations](operations.md#configure-the-s3-backup-server)).
- AdGuard's initial bcrypt hash belongs in its persistent application configuration. Home Assistant, Matter/Thread, Spotify state and archived applications also contain credentials in app-owned data. Systemd credentials cannot eliminate this application state; backups and host storage protection remain necessary.

### Recommended sequence

1. **Move decrypted generations to `/run/homelab/secret-sets`**, keeping a private parent, 0600 files and the all-or-nothing generation switch. Update every Quadlet secret path and recreate secrets before dependent containers start on every boot. Native `LoadCredential=` can then copy only the needed file into each consuming unit. Preserve a bounded previous generation for rotation failures during the current boot. Inventory persistent old generations and recovery archives before cleanup; older bootc deployments still expect the old paths. `/run` removes normal disk persistence, but check swap policy before claiming the same protection as unswappable credential storage.
2. **Use files in applications that already support them.** Start with cloudflared's `--token-file /run/secrets/tunnel-token` (requires cloudflared >= 2025.4.0). Extract only `TUNNEL_TOKEN` as the file content, not the whole dotenv record, and remove the original token environment injection. Vaultwarden supports `ADMIN_TOKEN_FILE`; check the pinned image and persistent `config.json` overrides before migration. Both should receive a narrowly scoped read-only credential mount, with user namespace ownership and SELinux verified. [Cloudflare run parameters](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/#token-file), [Vaultwarden file loading](https://raw.githubusercontent.com/dani-garcia/vaultwarden/main/src/util.rs), [Vaultwarden configuration](https://raw.githubusercontent.com/dani-garcia/vaultwarden/main/src/config.rs)
3. **Adopt native credentials for maintenance.** Apply the same configuration to `homelab-backup.service`, `podman-auto-update.service`, and `bootc-fetch-apply-updates.service`: load the restic password and an AWS-format shared credentials file; keep repository/region/cache settings as ordinary environment values. Set `RESTIC_PASSWORD_FILE=%d/restic-password` and `AWS_SHARED_CREDENTIALS_FILE=%d/s3-credentials`. Remove the original AWS key environment variables, which take precedence over the file. Initially `LoadCredential=` improves delivery; `LoadCredentialEncrypted=` additionally avoids plaintext source files when independently provisioned ciphertext replaces them. Preserve manual maintenance and `ExecStopPost` recovery behavior. [Restic password files](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html), [Restic S3 credentials chain](https://raw.githubusercontent.com/restic/restic/master/internal/backend/s3/s3.go)
4. **Wrap the age identity only after deciding the storage threat model.** Provision its encrypted credential on the Pi and point `SOPS_AGE_KEY_FILE` at the prepare unit's credential file. Remove the persistent plaintext identity only after reboot and recovery succeed. The current `RemainAfterExit=yes` means the prepare unit stays active; review credential lifetime rather than assuming its key disappears when the preparation process exits. Use `systemd-creds has-tpm2` on the host to establish actual support; the repository does not establish a TPM-equipped Pi. Require `host+tpm2` explicitly if theft resistance is the goal and both components are available. Host-only encryption leaves the decrypting key on the same disk. Full disk encryption addresses broader application-state theft, but unattended Pi boot/recovery needs its own design.
5. **Keep environment-only applications compatible for now.** Verify native file/config support in the pinned Beszel, Papra, homepage and Glance versions before changing their contracts. Loading systemd credentials into environment variables is a transitional integration improvement, not a fix for container inspection exposure. Podman `Secret=...,type=mount` is an alternative delivery mechanism; its storage backend and rotation semantics need verification and add a second secret store. `type=env` does not achieve the file-delivery objective. [Podman secret options](https://docs.podman.io/en/latest/markdown/podman-container.unit.5.html#secret-secret-opt-opt)

### Recovery and acceptance

The backup helper includes `apps`, `credentials`, `recovery` and selected host configuration, but **does not include `/var/lib/systemd/credential.secret`** ([backup sources](../scripts/homelab#L313)). If native encrypted sources move outside those trees, include their ciphertext explicitly. Decide whether host-key recovery should preserve the host secret or require reprovisioning; a backup of ciphertext alone does not imply decryptability. A copied host key still cannot replace the original TPM for combined encryption.

Keep the existing independent age identity, restic password and S3 recovery credentials. A TPM-bound age key and a password contained inside its own restic snapshot cannot bootstrap replacement-device recovery. Prefer restoring portable recovery material and re-encrypting credentials on the replacement device, rather than assuming the old host-bound blobs will work. [Existing independent recovery procedure](operations.md#configure-the-s3-backup-server)

Before implementation is accepted, verify generation rollback after failed decryption; missing/corrupted credential startup failure; complete boot and container restart; no token values in inspection through the broker; access denied to unrelated containers/users; rotation with deliberate restarts; backup/update/resume behavior; and restoration on a replacement host using only documented independent recovery material. Also exercise bootc update/rollback before adding PCR policies. No code or device changes were made for this assessment, and no live version, TPM, mount or restore checks were performed.
