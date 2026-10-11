# Runtime secrets deployment — 2026-10-11

The Pi boots the published PR #11 host image, digest
`sha256:4bc4b03cb23df0b02e234170631efed2301d198de49c1dac64a01649a9be9767`.
The previous deployment remains pinned for rollback. The pre-cutover cold snapshot
is `f908c866`; an isolated restore verified recovery inputs, Vaultwarden SQLite
and Papra's encrypted database with its native client.

## Live paths and compatibility fixes

- Helper: `/var/lib/homelab/maintenance/homelab`, invoked with Python by local service overrides.
- Ciphertext and loader source: `/usr/share/homelab`.
- Selected runtime files: `/run/homelab/secrets/current/<app>`.
- Portable recovery inputs: `/var/lib/homelab/credentials`, including the separate S3 INI file.

The live helper retains the device's union of `/etc` and `/usr` Quadlet inventory
so maintenance includes TREK. It uses a five-minute readiness budget for cold
application recovery and backs up local rotation-service overrides. Preserve
these changes when installing another additive helper patch.

Beszel's pod uses `UserNS=auto`; its agent secret mount needs `idmap` so pod root
can read host-root-owned files. The targeted device override is
`/etc/containers/systemd/beszel-agent.container.d/97-secrets-mapping.conf`.
PR #12 packages that mapping, the readiness budget and recovery inventory fix.
Remove the override only after booting an image containing the equivalent fix.

## Verification and limits

All six consumers use private read-only secret mounts. Their secret values match
the previous delivery, no secret values are injected into container metadata,
and an unprivileged host user cannot read the exports. AdGuard authenticated
successfully with Glance's exported credentials; Beszel reconnected and reports
the Pi up. Glance, homepage, Papra and Vaultwarden returned HTTP 200 locally;
operator-side public homepage and Vaultwarden checks returned 200, while the
public Vaultwarden admin route remained blocked with 403. Vaultwarden's persisted
admin-token precedence was checked.

Both a controlled loader-only generation change and rotation back to the packaged
source completed successfully, preserving provider credentials and database keys.
All previously active containers resumed and durable recovery intent cleared.
The temporary source override and first-boot startup extensions were removed.

These checks establish secret delivery, readiness and database integrity. They
cannot establish account-holder login or document decryption in a user session.
Homepage's existing Spotify OAuth refresh failure still requires account-owner
reauthorization. No database encryption-key migration or provider revocation was
performed. Root and consuming applications can read their secrets; portable
recovery inputs remain persistent and require separate protection against disk theft.

The post-cutover native backup is `9fd5b83a`. Its isolated restore verified all
four credential inputs (including S3 INI), the live helper and rotation override,
Vaultwarden SQLite, and Papra's encrypted database; `restic check` reported no
errors. Obsolete persistent plaintext generations and their selector were removed,
and raw environment values were removed from the local legacy container metadata.
Historical encrypted backups and private portable recovery inputs remain available.
All three maintenance timers are enabled and active again, after time synchronization.
Final service checks found no failed units or pending recovery intent.

The Depanator thread may now pull the pinned public image, apply its additive
helper patch while retaining the fixes above, install its own Quadlet and run the
private setup wizard. Its optional device ciphertext belongs at
`/var/lib/homelab/device-secrets/depanator.enc.env`; the root-owned parent must be
0700 and the ciphertext 0600. Personal setup and account authentication remain
owned by that thread. No Depanator secrets or configuration were provisioned by
this deployment.
