# Backup redesign proposal

Status: the owner approved only shutdown/recovery/readiness hardening on 2026-10-10. Those changes are implemented and validated on the Pi. Local staging remains an unapproved proposal and is not implemented. See `operations.md` for the device overrides, validation evidence and rollback procedure.

## Recommendation and limits

Keep the existing SD card and ext4 filesystem, Python helper, systemd timers, encrypted restic repository and retention policy. Harden failure recovery first, then benchmark consistent local staging to separate capture from remote upload. Adding an SSD, reformatting storage and filesystem migration are outside this plan.

The proposed staging sequence is: preflight → pre-copy while applications run → record recovery intent → stop required writers cleanly → finalize a complete local copy → resume and check applications → upload → prune after success.

If staging passes the benchmark, applications run during upload and pruning. Final synchronization, Home Assistant startup and Thread/Matter reconnection still contribute to the interruption. This removes upload time from the outage; it does **not** promise uninterrupted light control or a shorter total outage until measured. Eliminating routine restarts would require verified application-native exports for the entire HA/Matter/Thread set.

## Evidence from this Pi

- `/var/lib/homelab` is on the SD card's ext4 filesystem; no USB SSD is currently attached.
- Application state occupies approximately 3.7 GiB. About 167 GiB was free during the incident.
- Today's backup stopped services at 02:00:19; HA, Matter and OTBR restarted at 02:01:18; the remote access tunnel reconnected at 02:01:54.
- Restic scanned about 3.669 GiB in 41 seconds and uploaded about 16.7 MiB. A new local-copy design could be slower than this workload, so it must be measured rather than assumed faster.
- HA's Podman `StopTimeout` is 10 seconds while systemd allows 100 seconds. The logs show a forced kill during backup.
- Recovery intent currently lives in `/run/homelab/paused-units.json`, which does not survive reboot. Existing tests exercise upload failure, unreachable repositories, repeatable recovery and real restic restore, but not the proposed staging lifecycle.

## Phase 1: harden the current lifecycle

1. Give HA an explicit container shutdown allowance, initially 60 seconds, with systemd retaining a larger allowance. Check the installed Quadlet generator and generated stop commands: changing systemd's timeout alone does not fix Podman's 10-second limit. A failed HA shutdown or an application writer remaining active must fail the capture gate; attempt recovery and block updates rather than label that run a clean backup. Other applications' shutdown policies remain unchanged.
2. Keep one maintenance lock shared by scheduled backup, app updates, host updates and recovery. Recovery must not race a still-running capture.
3. Store an atomically written, root-only restart list on durable local storage before stopping anything. Persist it through reboot; make startup recovery run after preparation without ordering application startup after recovery, which would create a dependency cycle. Recover only recorded units and retain the list until recovery succeeds. The smaller implementation uses the restart list and existing journal timestamps rather than adding a maintenance state machine.
4. Check application readiness after restart, not just systemd's `active` state: HA HTTP, Matter connection and OTBR attached state; check other resumed services are active. Verify external HA access during rollout. Existing systemd/restic logs supply shutdown, startup, upload and completion timings.
5. Keep failures visible through systemd and its journal. Outbound alerting, overdue-backup monitoring and additional reporting remain follow-up proposals requiring an owner-selected destination; no messaging integration is implemented in the smaller fix.

## Phase 2: capture locally, resume before upload

- Allocate root-only staging outside the live application tree, with separate incomplete and complete generations. Keep complete generations untouched during upload/retry. Bound staging to one complete generation plus one working generation, and reserve space for both plus application growth. At today's size, two staging copies require approximately 7.4 GiB extra; calculate the requirement from the current inventory on every run.
- Pre-copy the complete application state while services run, preserving numeric ownership, permissions, ACLs, hard links and relevant extended attributes. This copy is provisional and must never be uploaded or satisfy the update gate.
- Capture current images/digests and active-unit metadata before stopping containers. Include credentials and all existing host recovery sources (SSH identity, NetworkManager, Bluetooth, fstab and local overrides) in the private recovery tree. Avoid concurrent administrative configuration changes during capture.
- Stop actual persistent-state writers and external ingestion, then perform an authoritative final synchronization that catches in-place edits, same-size changes and deletions. Do not rely solely on size/mtime checks for the final consistency gate. Verify all intended sources were captured before publishing the generation as complete. Keep staging outside its own source traversal.
- HA, Matter and OTBR remain a coordinated group so pairing state is captured together. Cloudflared has no application-state volume and should remain running; do not stop entire pods/targets when that unnecessarily stops other services. Other services can remain online only after verifying a consistent supported capture method for their writable files.
- Bound the stopped-services phase with a timeout. On timeout, failed final synchronization or termination, resume the recorded services, retain recovery intent if resume fails, and reject the incomplete generation.
- Resume the recorded services immediately after local capture, verify readiness, then upload the frozen generation with restic while applications run. Use a stable backup source path with a documented restore mapping, so local generation names do not change restoration layout or retention behavior.
- Retain the newest complete capture after upload failure and retry it without another service interruption. Never mutate a retry source or discard the last known remote recovery point to make a failed run appear successful.

Staging adds SD reads/writes and space use. A full-content final comparison may take longer than today's 41-second scan/upload. Benchmark representative database and document changes, first-run copying, interrupted runs and normal incremental runs. Adopt staging only if the measured full outage improves and the SD I/O impact is acceptable. Otherwise retain the hardened existing backup and investigate supported native exports as a separately reviewed design. Do not introduce a loopback filesystem merely to obtain snapshots.

## Failure and update behavior

- Preflight failure: leave services running and do not start updates.
- Stop/capture failure: resume every previously running affected service; mark capture incomplete; keep updates blocked.
- Resume failure: retain recovery intent and raise an alert; do not hide it behind an upload-success status.
- Termination/reboot: repeatable recovery reads durable intent; stale/incomplete captures are never uploaded as successful captures.
- With staging enabled, upload failure or restic partial success leaves services online; preserve a bounded complete capture for retry. Under the hardened existing backend, failure recovery resumes services. Require exit status 0 and a recorded remote snapshot ID before allowing updates or pruning.
- Fresh pre-update backups remain mandatory. Do not reuse an old nightly backup merely because its upload succeeded. Backup checks/retention do not run while applications are stopped.
- Preserve the current seven daily, four weekly and twelve monthly remote snapshots, scoped to this host and backup tag. Local staging is a capture aid; remote encrypted backups remain the recovery protection against SD-card loss.

## Validation and rollout gates

Extend `tests/test_homelab.py` with ordering and failure injection at stop, copy, resume, upload and reboot recovery; test previously inactive/retired services, incomplete restic snapshots, insufficient space, copy timeouts, deletions, same-size edits, metadata preservation and safe retries. Test real rsync/staging and restic restore on Linux, not only mocks.

Restore a new-format remote snapshot to an isolated directory and verify SQLite integrity plus binary attachments, HA `.storage`, Matter fabric state, OTBR state, numeric ownership and recovery secrets. Never run a second restored controller against the same real devices during the drill.

On the Pi, measure from the user's perspective: HA access and actual light control before, during and after capture. Deliberately slow/fail upload in an approved verification window and confirm services recover before upload completes. Require clean shutdowns, bounded capture time, automatic recovery, acceptable SD I/O and a successful remote restore before enabling staging. Compare against the hardened existing backend, not its old forced-kill timing; publish measured downtime.

Keep the old helper/deployment available through verification. Roll back backup execution independently of application state: live paths remain unchanged on the SD card. Disable staging and return to the hardened direct-restic backend if it fails the benchmark or operational gates. Restoring application data remains a separate, deliberate operation.

## Implementation scope and decisions

Expected changes: `scripts/homelab`, relevant Quadlet shutdown settings, maintenance/recovery systemd units, `tests/test_homelab.py`, and operations documentation. Reuse installed rsync, Python, restic and the current timers/repository; add no backup daemon, filesystem migration, web UI or workflow platform.

The owner has selected the existing SD card. Before implementation: review the hardening and staging-benchmark plan, its remaining outage and SD-write tradeoff, and select an alert destination if outbound alerts are desired. Enable staging only after its measured benefit and restore tests are reviewed. No code, timer or storage change is approved by the hardware preference or this proposal itself.

## Primary references

- [Podman Quadlet shutdown timeouts](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html#stoptimeout): the container timeout must be lower than the systemd timeout.
- [Restic backup exit statuses](https://restic.readthedocs.io/en/stable/040_backup.html#exit-status-codes): exit 3 creates an incomplete snapshot and must not satisfy the update gate.
- [HA native backup preparation hooks](https://developers.home-assistant.io/docs/core/platform/backup/): supported application-aware export is the future path to less disruption; HA's export alone does not cover the separate Matter/OTBR containers.
