# Operations runbook

This runbook deploys one Django web service behind Caddy with PostgreSQL and ClamAV. Caddy terminates public HTTPS and renews certificates; PostgreSQL and the virus scanner are reachable only on the private Compose network. ClamAV also has an egress-only bridge for FreshClam signature updates; it is not exposed through a published port. PostgreSQL, private uploads, ClamAV signatures, and Caddy's ACME state use named volumes. App containers run as UID 10001, have a read-only root filesystem, and do not apply migrations on startup. Static assets are collected into the image and served through WhiteNoise.

The Compose file intentionally has no production credential defaults. Put the deployment variables in the host's protected environment or a root-readable Compose env file outside source control. Keep `.env`, credentials, encryption keys, and student records out of Git. Django's key, PostgreSQL URL, PostgreSQL password, SMTP password, and MFA encryption key use separate file-backed Compose secrets; the backup key remains outside the stack. `DATABASE_URL_FILE` must point at a protected file whose only content is the connection URL for the Compose database using the same database name and role configured for PostgreSQL.

## Local development

Install dependencies with `python -m pip install -r requirements.txt`, copy `.env.example` to `.env`, then apply migrations and start the local server. `DJANGO_DEBUG=true`, SQLite, and the development-only secret are local conveniences; never reuse them in a production environment.

Use `python manage.py seed_demo --password <chosen-password>` to populate a synthetic browser demo. It requires debug mode and an operator-supplied password of at least eight characters. The accounts and records are predictable fixtures and must never be seeded into a database containing real school data. Reseeding preserves changed school settings, reviewed notices and corrections, assessment attempts, finance history, and enrollment/promotion history. See `docs/TESTING_MVP.md` for the role-based pilot acceptance flows.

## First deployment

1. Install Docker Engine, the Compose plugin, and `curl` on a supported Linux host. Point the public DNS A/AAAA records for `CADDY_DOMAIN` at that host and allow inbound TCP 80/443 (UDP 443 is optional HTTP/3). Store the PostgreSQL password, a distinct MFA encryption key, Django secret key, SMTP password, and database URL in separate files owned by the deployment operator with mode `0600`. Generate MFA key material with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`; do not reuse the Django secret key or backup key.
2. Create a protected env file (for example `/etc/school-cms/production.env`, mode `0600`) with these required values:

   ```dotenv
   CADDY_DOMAIN=school.example.org
   POSTGRES_DB=schoolcms
   POSTGRES_USER=schoolcms_app
   POSTGRES_PASSWORD_FILE=/etc/school-cms/postgres-password
   MFA_ENCRYPTION_KEY_FILE=/etc/school-cms/mfa-encryption-key
   DATABASE_URL_FILE=/etc/school-cms/database-url
   DJANGO_SECRET_KEY_FILE=/etc/school-cms/django-secret-key
   DJANGO_ALLOWED_HOSTS=school.example.org
   DJANGO_CSRF_TRUSTED_ORIGINS=https://school.example.org
   DJANGO_EMAIL_HOST=smtp.example.org
   DJANGO_EMAIL_HOST_USER=school-cms@example.org
   DJANGO_EMAIL_HOST_PASSWORD_FILE=/etc/school-cms/smtp-password
   DJANGO_DEFAULT_FROM_EMAIL=School CMS <school-cms@example.org>
   ```

   Create `/etc/school-cms/django-secret-key` with a unique value from `python -c 'import secrets; print(secrets.token_urlsafe(64))'`; create `/etc/school-cms/database-url` containing `postgresql://schoolcms_app:URL_ENCODED_PASSWORD@db:5432/schoolcms`; and create `/etc/school-cms/smtp-password` containing only the SMTP password. Local Compose file secrets retain host ownership and permissions. The four web secret files must be readable by container UID10001: deliberately set ownership to10001:10001 and mode0400 (for example using sudo chown/chmod on a secured host directory), or use an equivalent secret manager mount. Keep the PostgreSQL password readable by its database entrypoint. Verify readability with a one-off web check before starting service; Compose file-backed secrets do not reliably remap UID/GID. Never solve this by making secrets world-readable. URL-encode reserved characters in the password portion of the database URL. `DJANGO_HSTS_SECONDS` defaults to 3600; raise it and enable include-subdomains/preload only after verifying all relevant names support HTTPS. Do not place the backup encryption key in this Compose environment; keep it in a separate protected file and make it available only to the backup operator.

3. Check the required interpolation, build the reviewed web image, then start PostgreSQL and ClamAV:

   ```sh
   docker compose --env-file /etc/school-cms/production.env config --quiet
   docker compose --env-file /etc/school-cms/production.env build web
   docker compose --env-file /etc/school-cms/production.env up -d db clamav
   ```

4. Apply migrations as a single explicit release action. Run this before starting the web service so readiness can verify the schema:

   ```sh
   docker compose --env-file /etc/school-cms/production.env run --rm web python manage.py migrate --noinput
   ```

   Inspect the command output and retain the release log. Do not run migration commands independently in multiple web containers. Take a backup before every later migration that may alter or transform production data.

5. Start the application and TLS proxy, then verify health and Django's deployment checks:

   ```sh
   docker compose --env-file /etc/school-cms/production.env up -d web caddy
   BASE_URL=https://school.example.org scripts/smoke-production.sh
   docker compose --env-file /etc/school-cms/production.env exec -T web python manage.py check --deploy
   ```

   `GET /health/live/` checks that the process can serve requests. `GET /health/ready/` checks database connectivity and migration state and returns no diagnostic details. Both are unauthenticated operational endpoints; do not add private data to their response bodies.

6. Confirm ClamAV is healthy and its signature volume has completed its initial update before accepting uploads. The app scans uploads through the private Compose network and stores private files in the `private_files` volume at `/var/lib/schoolcms/private`; the service must fail closed if the scanner cannot give a clean result. Back up private files under the same access/retention controls as the database and test recovery for both. Create individual staff accounts through the approved administrative workflow. Do not use demo seed accounts in production. Configure SMTP and send a password-reset test to a controlled mailbox before onboarding users.

## Routine releases and operations

For each release, fetch/build the reviewed image, take a verified recent backup, run `manage.py check --deploy`, apply the migration step once, roll out the web containers, then check both health endpoints over HTTPS. Do not rely on a container restart to migrate the database. Keep the previous image available for application rollback; database rollback may require restoration when a migration is not backwards compatible.

Useful read-only operational commands:

```sh
docker compose --env-file /etc/school-cms/production.env ps
docker compose --env-file /etc/school-cms/production.env logs --since=30m web caddy db
docker compose --env-file /etc/school-cms/production.env exec -T web python manage.py check --deploy
```

The health check reports only service availability; monitor host disk, Compose health, PostgreSQL capacity, HTTPS certificate renewal, ClamAV signature freshness, SMTP delivery, and application exceptions separately. Process/error logs go to container stdout/stderr; HTTP access logging is disabled so password-reset paths and query strings are not emitted by default. Do not log passwords, reset links, or student records. Restrict log access and retention. Database history protections are application-level; privileged SQL access can bypass them, so restrict and audit database operator access.

## Encrypted backups

Install PostgreSQL client utilities and OpenSSL on a trusted backup host. Use a distinct key file containing a strong random passphrase, owned by the backup operator and mode `0600`; store a protected recovery copy outside the database host. Use a protected `.pgpass` file with mode `0600` or provide `PGPASSWORD` in a noninteractive secret-injection environment. The script turns `PGPASSWORD` into a short-lived mode-`0600` pgpass file and never puts credentials in process arguments. Avoid shell tracing (`set -x`) and do not pass passwords as command-line options.

Example, after loading the protected deployment variables into the operator's shell and selecting the database credentials via `PG*` variables:

```sh
export PGHOST=db.example.internal PGPORT=5432 PGDATABASE=schoolcms PGUSER=schoolcms_backup
export PGPASSFILE=/etc/school-cms/backup.pgpass
export BACKUP_ENCRYPTION_KEY_FILE=/etc/school-cms/backup-encryption.key
export BACKUP_OUTPUT_DIR=/srv/secure-backups/school-cms
scripts/backup-postgres.sh
```

The resulting custom-format dump is encrypted with OpenSSL AES-256-CBC, PBKDF2, and a 600,000-iteration derivation. Each artifact has a SHA-256 sidecar for transfer-corruption checks and an HMAC-SHA256 sidecar keyed from the protected passphrase; restore verifies the HMAC before decryption. Restrict the backup directory, replicate encrypted artifacts to a separate failure domain, set retention according to school policy, and document who can restore and access student data. Keep the key separate from the backup artifact and never upload an unencrypted temporary dump.

## Restore to an empty disposable database

Restores are deliberately fail-closed. The script requires both `RESTORE_TARGET_ENVIRONMENT=disposable` and `DJANGO_ENVIRONMENT=disposable`, explicit `RESTORE_TARGET_DISPOSABLE=YES`, a target database name containing `restore`, `rehearsal`, `disposable`, or `test`, and a database with no user tables, functions, types, or non-default schemas. It refuses unmarked/default environments, `DJANGO_ENVIRONMENT=production`, and a target equal to `RESTORE_PRODUCTION_DATABASE_NAME`. It never runs `pg_restore --clean` and never drops tables. Do not point it at a production database.

Create a new empty database on an isolated PostgreSQL instance, then set credentials and the separate encryption key file:

```sh
export PGHOST=restore-db.example.internal PGPORT=5432 PGDATABASE=postgres PGUSER=schoolcms_restore
export PGPASSFILE=/etc/school-cms/restore.pgpass
export BACKUP_ENCRYPTION_KEY_FILE=/etc/school-cms/backup-encryption.key
export RESTORE_TARGET_ENVIRONMENT=disposable RESTORE_TARGET_DISPOSABLE=YES
export DJANGO_ENVIRONMENT=disposable
export RESTORE_PRODUCTION_DATABASE_NAME=schoolcms
createdb schoolcms_restore_20261015
export PGDATABASE=schoolcms_restore_20261015
scripts/restore-postgres.sh /srv/secure-backups/school-cms/schoolcms-20261015T120000Z.dump.enc
```

The restore `.pgpass` file must match both the maintenance database (`postgres`, for database creation) and the `_restore` target database, or use a narrowly scoped wildcard for the isolated restore server and role.

After restoration, run `python manage.py migrate --check` using the isolated restored database settings, verify expected record counts/business invariants with authorized staff, and retain rehearsal evidence. Treat a restored database as real student data even when isolated. Dispose of it according to the retention policy.

Run the end-to-end encrypted dump/restore rehearsal periodically and after changing backup tooling, PostgreSQL major versions, or encryption-key handling. It creates two uniquely named temporary databases on the selected server, validates a marker through an encrypted backup and disposable restore, then drops those two databases:

```sh
export PGHOST=restore-db.example.internal PGPORT=5432 PGUSER=schoolcms_restore
export PGPASSFILE=/etc/school-cms/restore.pgpass
export BACKUP_ENCRYPTION_KEY_FILE=/etc/school-cms/backup-encryption.key
scripts/restore-rehearsal.sh
```

Use this only on a disposable PostgreSQL server where the configured role can create and drop databases. If using `PGPASSFILE`, include a mode-`0600` entry whose database field is `*` for the selected host/user so the rehearsal can authenticate to both temporary databases. The CI PostgreSQL job runs the same rehearsal against its ephemeral service. CI is not evidence of a successful production restore.

## Production acceptance gates

Before launch, record hosted HTTPS/proxy/cookie behavior, SMTP and reset-email delivery, least-privilege account provisioning, private-file handling, PostgreSQL concurrency tests, an isolated restore rehearsal, operational monitoring, incident response, accessibility, privacy review, and a five-role human pilot. Passing container, CI, or Django deployment checks alone does not mark the production milestone complete.

## Reviewed scanner exceptions

Bandit exceptions are narrow inline IDs: the explicitly DEBUG-only fallback secret (production rejects it), public grading percentages misclassified as passwords, and the operator-configured scanner subprocess using an argv list with no shell, opaque app-created paths and a timeout. Preflight additionally resolves Git from PATH and invokes only fixed argv; configured scanner calls use no shell and explicit timeouts. These calls have reviewed narrow inline exceptions. The dependency scan includes all pinned runtime dependencies; a clean scan is point-in-time evidence rather than a security guarantee.

## Separate MFA key and final backup checks

Generate the MFA key directly into its protected host file using `umask077` (written as `umask 077` in the shell) and `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' > /etc/school-cms/mfa-encryption-key`. Set deliberate owner/mode for UID10001 readability as described above, and retain a protected recovery copy. Do not reuse the Django signing key. Losing this key prevents decrypting stored TOTP devices; rehearsed recovery is required.

The PostgreSQL helper installs credential-file cleanup before later validation can fail. Encrypted artifact names are sanitized and unique, and no script silently overwrites a previous artifact. Rehearse the DB and private-file restoration together on the selected VPS before onboarding. CI's initial job and retry failed with no retrievable logs/steps; resolve the runner/check failure or run the recorded checks in a controlled staging server.

## Release validation tools

See [runtime preflight](RELEASE_PREFLIGHT.md), [combined recovery rehearsal](RECOVERY_REHEARSAL.md), [synthetic browser acceptance](BROWSER_ACCEPTANCE.md), [authentication throttle retention](AUTH_RETENTION.md), [release review](RELEASE_REVIEW.md) and [evidence accounting](RELEASE_EVIDENCE.md). The combined bundle covers the database and private-file tree, including quarantine; database-only restoration is not full recovery acceptance. Keep the application and all file writers stopped for a consistent bundle.

The CI Bandit scan covers the listed Django application directories; it does not scan the `scripts/` directory. Operational scripts receive manual review and targeted tamper, traversal, cleanup and disposable-target regression tests. Do not present the application scan as a clean scan of every repository file.
