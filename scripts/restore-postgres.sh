#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() { echo "Usage: $0 BACKUP.dump.enc" >&2; }
if [[ $# -ne 1 ]]; then usage; exit 2; fi
backup_file="$1"
[[ -r "$backup_file" ]] || { echo "Backup file is not readable" >&2; exit 1; }

[[ "${RESTORE_TARGET_DISPOSABLE:-}" == "YES" ]] || {
  echo "Refusing restore: set RESTORE_TARGET_DISPOSABLE=YES only for a disposable target" >&2; exit 1;
}
[[ "${RESTORE_TARGET_ENVIRONMENT:-}" == "disposable" ]] || {
  echo "Refusing restore: RESTORE_TARGET_ENVIRONMENT must be exactly 'disposable'" >&2; exit 1;
}
[[ "${DJANGO_ENVIRONMENT:-}" == "disposable" ]] || {
  echo "Refusing restore: DJANGO_ENVIRONMENT must be explicitly set to 'disposable'" >&2; exit 1;
}
[[ -n "${PGDATABASE:-}" ]] || { echo "PGDATABASE is required" >&2; exit 1; }
[[ "$PGDATABASE" =~ (^|[_-])(restore|rehearsal|disposable|test)([_-]|$) ]] || {
  echo "Refusing restore: target database name must contain restore, rehearsal, disposable, or test" >&2; exit 1;
}
if [[ -n "${RESTORE_PRODUCTION_DATABASE_NAME:-}" && "$PGDATABASE" == "$RESTORE_PRODUCTION_DATABASE_NAME" ]]; then
  echo "Refusing restore: target matches RESTORE_PRODUCTION_DATABASE_NAME" >&2; exit 1
fi
[[ "${DJANGO_ENVIRONMENT:-}" != "production" ]] || {
  echo "Refusing restore from an environment marked production" >&2; exit 1;
}
: "${BACKUP_ENCRYPTION_KEY_FILE:?Set BACKUP_ENCRYPTION_KEY_FILE to the protected backup key file}"
[[ -r "$backup_file.hmac" ]] || { echo "Authenticated backup HMAC sidecar is missing or unreadable" >&2; exit 1; }

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_postgres_auth.sh
source "$script_dir/_postgres_auth.sh"
_require_private_file "$BACKUP_ENCRYPTION_KEY_FILE" "Backup encryption key file"

python3 - "$backup_file" "$backup_file.hmac" "$BACKUP_ENCRYPTION_KEY_FILE" <<'PY'
import hashlib
import hmac
import pathlib
import sys

artifact, mac_file, key_file = map(pathlib.Path, sys.argv[1:])
passphrase = key_file.read_bytes().rstrip(b"\r\n")
mac_key = hashlib.sha256(b"School-CMS encrypted backup HMAC v1\0" + passphrase).digest()
expected = mac_file.read_text().strip()
digest = hmac.new(mac_key, digestmod=hashlib.sha256)
with artifact.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
actual = digest.hexdigest()
if not hmac.compare_digest(expected, actual):
    raise SystemExit("Encrypted backup authentication failed")
PY

table_count="$(psql --no-password --tuples-only --no-align --command \
  "SELECT (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')) + (SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema')) + (SELECT count(*) FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')) + (SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast','public'))")"
if [[ "$table_count" != "0" ]]; then
  echo "Refusing restore: target database must be empty (found $table_count tables)" >&2
  exit 1
fi

plain_dump="$(mktemp "${TMPDIR:-/tmp}/schoolcms-pg-restore.XXXXXXXX")"
chmod 600 "$plain_dump"
trap 'rm -f -- "$plain_dump"; _postgres_auth_cleanup' EXIT
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
  -in "$backup_file" -out "$plain_dump" \
  -pass "file:$BACKUP_ENCRYPTION_KEY_FILE"
pg_restore --list "$plain_dump" >/dev/null
pg_restore --no-password --exit-on-error --single-transaction \
  --no-owner --no-privileges --dbname="$PGDATABASE" "$plain_dump"
printf 'Restore completed to disposable database: %s\n' "$PGDATABASE"
