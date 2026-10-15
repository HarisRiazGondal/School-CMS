# Database and private-file recovery

Production release recovery requires one authenticated encrypted bundle containing the encrypted PostgreSQL custom dump, its existing SHA-256 and HMAC sidecars, all private storage files (including quarantine), and a versioned manifest with per-file SHA-256 digests. The private-file tree is part of the release backup acceptance gate. A successful Django/SQLite test or a PostgreSQL-only dump rehearsal does not establish that the release bundle can restore both halves.

## Consistency contract

The bundle scripts require an explicit maintenance marker with the exact bytes `SCHOOL-CMS-QUIESCED-V1` followed by a newline. The marker records an operator assertion; it cannot stop or detect application processes. Before creating the marker, stop every web/worker process and any other database or private-storage writer, confirm uploads and writes have drained, and keep the system unavailable until the backup or restore is complete. This deliberate downtime gives the PostgreSQL dump and private-file tree one consistent point. The scripts do not claim an online or transactionally coordinated snapshot. A changed private-file inventory during backup causes the bundle to fail closed.

Create the marker only after quiescing the service. Keep the backup key in a separate operator-controlled file with mode `0600`, outside the application stack and backup directory. Set `PG*` credentials as for `backup-postgres.sh` in `docs/OPERATIONS.md`; do not enable shell tracing or place secrets in command arguments.

```sh
umask 077
printf 'SCHOOL-CMS-QUIESCED-V1\n' > /secure/maintenance/school-cms.quiesced
export BACKUP_ENCRYPTION_KEY_FILE=/etc/school-cms/backup-encryption.key
python3 scripts/backup-bundle.py \
  --private-root /var/lib/schoolcms/private \
  --output-dir /srv/secure-backups/school-cms \
  --quiesced-marker /secure/maintenance/school-cms.quiesced
```

The output is a unique `.scb.enc` bundle plus `.sha256` transfer checksum and `.hmac` authentication sidecar. AES-256-CBC/PBKDF2 encryption matches the existing PostgreSQL backup format; the bundle HMAC authenticates the encrypted archive and the authenticated manifest pins the dump and every private file by digest and size. The existing dump HMAC is carried into the bundle and checked again by the existing PostgreSQL restore script. The scripts reject symlinks and special files, unsafe archive paths, duplicate names, oversized content, missing/malformed manifests, and mismatching hashes. Quarantined files are preserved as private files; they are not rescanned or promoted during recovery.

## Restore

Restore only to a newly created, isolated PostgreSQL database and a separately selected, existing, empty private-file directory. The PostgreSQL target must also satisfy the existing `restore-postgres.sh` disposable environment and empty-database safeguards. Use the same protected key file. Stop application and background services and keep them stopped until the restore and verification finish. The bundle restore validates authentication, format, paths, sizes, and file hashes, then stages private files before the database restore. It invokes the existing guarded PostgreSQL restore; only after that succeeds does it atomically publish the staged private-file directory.

```sh
printf 'SCHOOL-CMS-QUIESCED-V1\n' > /secure/maintenance/school-cms.quiesced
export BACKUP_ENCRYPTION_KEY_FILE=/etc/school-cms/backup-encryption.key
export RESTORE_TARGET_DISPOSABLE=YES
export RESTORE_TARGET_ENVIRONMENT=disposable
export DJANGO_ENVIRONMENT=disposable
export RESTORE_PRODUCTION_DATABASE_NAME=schoolcms
export PGDATABASE=schoolcms_restore_20261015
python3 scripts/restore-bundle.py \
  /srv/secure-backups/school-cms/schoolcms-recovery-v1-20261015T120000Z-a1b2c3d4e5.scb.enc \
  --private-root /srv/restore/schoolcms-private \
  --private-root-disposable \
  --quiesced-marker /secure/maintenance/school-cms.quiesced
```

Create the target directory empty before running restore. If database restore fails, the private-file directory remains empty and temporary staged files are removed. If PostgreSQL succeeds but publishing the files fails, the tool reports that state explicitly: keep the application stopped, discard that disposable database, resolve the filesystem issue, and repeat against a newly created empty database and root. Never serve the database or files from an incomplete restore. A successful command still requires operational validation before traffic resumes: run `python manage.py migrate --check` with the disposable restored settings, verify expected business invariants and private-file reads with authorized staff, and record elapsed recovery time. Treat restored pupil records under the same access and retention controls as production.

## Real PostgreSQL acceptance rehearsal

Run this harness only against an isolated disposable PostgreSQL server and a CI-only key. It creates two uniquely named databases, writes a database marker and clean plus quarantined private-file fixtures, performs the real `pg_dump`/encryption/restore path, verifies the restored database marker and byte-for-byte file contents, then drops only those databases. `RECOVERY_REHEARSAL_DISPOSABLE=YES` is an explicit operator guard, not server detection. The harness's result is real PostgreSQL and file roundtrip evidence for that run; tests that mock the PostgreSQL subprocess are only local bundle/filesystem checks and must never be reported as database acceptance.

```sh
export RECOVERY_REHEARSAL_DISPOSABLE=YES
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=schoolcms
export PGPASSFILE=/secure/maintenance/recovery.pgpass # mode 0600; use secret injection in CI
export BACKUP_ENCRYPTION_KEY_FILE=/tmp/schoolcms-test-backup-key
openssl rand -base64 48 > "$BACKUP_ENCRYPTION_KEY_FILE"
chmod 600 "$BACKUP_ENCRYPTION_KEY_FILE"
python3 scripts/recovery-rehearsal.py
```

CI should run this harness with PostgreSQL 17 and an ephemeral service. A passing CI rehearsal does not prove the production host's key access, storage capacity, downtime, retention, operator procedure, or measured recovery time. Record production rehearsal evidence separately before marking the release gate complete.
