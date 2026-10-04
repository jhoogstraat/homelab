# Application state and S3 backups

Research checked against upstream documentation and source on 2026-10-04. Scope: the three remaining stateful applications below. The intended ownership rule is **Git controls deployment settings; the device owns application preferences and UI state**. The implementation target is `/var/lib/homelab/apps/<app>/{data,config}`; paths below are the container mount targets. Migrate existing data explicitly rather than starting with empty volumes. Where a preference has no UI, use the application's documented file format or environment variable. Restart only when that application requires it; file/env configuration does not imply live reconciliation. Git env files are copied into `/var/lib/homelab/environment` for bind mounts and SELinux labeling; seed files initialize missing state only.

The recommended baseline is local application state plus encrypted, retained backups in S3. Native object storage can be added where the application supports it, but does not replace database backups. A generic S3 mount is unsuitable for these databases: AWS Mountpoint does not provide file locking, modification of existing files, or full POSIX semantics. [AWS Mountpoint limitations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mountpoint.html)

## Storage and ownership matrix

“Cold backup” below means stop every writer before capturing the listed directories, then restart services. These are implementation recommendations based on the documented storage layouts; they are not claims that each application supplies a complete built-in backup command.

| Application | Durable container paths and ownership | Consistent backup | Native S3 primary storage |
| --- | --- | --- | --- |
| [AdGuard Home](../quadlets/adguard.container) | Persist **both** `/opt/adguardhome/conf` and `/opt/adguardhome/work`. The device owns `AdGuardHome.yaml`; initialize it only when missing. AdGuard generates and rewrites this file, and upstream requires stopping the process before editing it. Git owns startup arguments and networking. [Configuration](https://adguard-dns.io/kb/adguard-home/configuration/), [Docker volumes](https://adguard-dns.io/kb/adguard-home/docker/) | Stop AdGuard and capture both directories, including DNS settings, users, certificates, and work data. A read-only image config mount cannot serve as its writable configuration directory. | No native S3 state backend documented in the cited configuration; use S3 for backups. |
| [Vaultwarden](../quadlets/vaultwarden.container) | Persist `/data`: database, attachments, sends, signing keys, and optional `config.json`. UI `/admin` changes in `config.json` override environment values. Upstream recommends env configuration, but honoring device-owned UI config means retaining this file and accepting that editable env defaults may be superseded. [Config precedence](https://github.com/dani-garcia/vaultwarden/wiki/Configuration-overview) | Cold-capture all `/data`, including any SQLite WAL files. Its SQLite online backup command captures the database, **not** attachments, sends, or signing keys. External SQL requires a separate database dump. [Backup inventory](https://github.com/dani-garcia/vaultwarden/wiki/Backing-up-your-vault) | An optional compiled `s3` feature exists under AGPL. A maintainer says standard images do not enable it; it requires a custom build. SQL, temporary files, and templates still need their documented storage. Keep the current image local. [Feature configuration](https://raw.githubusercontent.com/dani-garcia/vaultwarden/main/.env.template), [Maintainer explanation](https://github.com/dani-garcia/vaultwarden/discussions/7327) |
| [Papra](../quadlets/papra.container) | Persist `/app/app-data` (SQLite DB and filesystem documents) and `/app/ingestion` (incoming/failed documents). Git sets storage/auth/env settings; UI document metadata belongs to the DB. Preserve authentication and any database/document encryption secrets. [Docker layout](https://docs.papra.app/self-hosting/using-docker/), [Configuration](https://docs.papra.app/self-hosting/configuration/), [Ingestion](https://docs.papra.app/guides/setup-ingestion-folder/) | Stop Papra and ingestion producers; capture both directories. Backing up only SQLite loses original documents. With S3 documents, recovery needs the corresponding objects and DB metadata as well. | Native document S3 storage is documented without a paid gate in the AGPL project; SQLite remains separate. Use the migration tool, not just an env change: it copies objects and updates DB storage keys. Run a dry run, keep source files, and inspect failures before deleting originals. [Migration procedure](https://docs.papra.app/guides/migrate-document-storage/), [Project license](https://github.com/papra-hq/papra) |

## Implementation and recovery gates

1. **Verify writable config mounts on the device.** AdGuard configuration must remain writable and durable. Verify changes survive a service restart before relying on backups.
2. **Capture a consistent set.** Serialize backup against container auto-update and restart activity. Stop all included stateful writers, capture their entire directories, and guarantee restart even if capture fails. Direct Restic-to-S3 cold backup works on the existing filesystem, but pauses applications for the **entire scan/upload**, potentially a long initial backup. A staged copy or future filesystem snapshot can shorten downtime. Plain live copies are unsuitable for SQLite; its Online Backup API provides a consistent DB snapshot but cannot atomically include sibling attachments. [SQLite backup API](https://www.sqlite.org/backup.html)
3. **Keep backups independent and encrypted.** Restic supports encrypted repositories on S3. Store its password and recovery credentials independently of the backed-up apps; losing the repository password prevents recovery. Retention and restore checks are required even if documents later move to a primary S3 bucket. [Restic repository and S3 setup](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html)
4. **Prove restoration before trusting automation.** Restore into isolated paths with compatible application versions; check database integrity, logins, downloaded documents/attachments, DNS settings, and document state. Record the container versions alongside each backup. A bootc OS rollback does not reverse application database migrations, so preserve the pre-update application state as well.

Native Papra S3 is the clearest optional next step. For the initial migration, keeping every application on its current local storage avoids a simultaneous data migration and makes a single cold-backup procedure reviewable.

## Retired services

OneDev and n8n are removed at the owner's request. Migration stops their legacy writers and archives their complete data/config trees under `/var/lib/homelab/apps/_retired/{onedev,n8n}`. This includes OneDev repositories and database state, and n8n workflows, credentials and its encryption key. Originals remain intact, and the archives are included in the encrypted host backup. They are not started by the new deployment.

Grafana and wg-easy were also retired at the owner's request. Their complete
data/config trees remain under `apps/_retired/{grafana,wg-easy}`, included in
restic backups. Grafana's archived secrets and wg-easy's peer keys are private
recovery state. Their Quadlets, seeded dashboard links and Grafana encrypted
secret are no longer packaged in new host images.

CouchDB was retired after the owner confirmed Obsidian uses iCloud now. Its
complete data and writable configuration remain under `apps/_retired/couchdb`;
its deployment definition, environment configuration and local credentials are
held in root-only recovery storage. These archives remain included in restic
backups. New images omit CouchDB and its encrypted secret.
