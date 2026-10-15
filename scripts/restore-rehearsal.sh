#!/usr/bin/env bash
# End-to-end PostgreSQL dump/encryption/restore check. Use only on a disposable
# PostgreSQL server; two temporary databases are created and dropped.
set -euo pipefail
umask 077

: "${BACKUP_ENCRYPTION_KEY_FILE:?Set BACKUP_ENCRYPTION_KEY_FILE to a protected file containing a strong random key/passphrase}"
[[ -r "$BACKUP_ENCRYPTION_KEY_FILE" ]] || { echo "Encryption key file is not readable" >&2; exit 1; }
key_mode="$(stat -c '%a' -- "$BACKUP_ENCRYPTION_KEY_FILE")"
if (( (8#$key_mode & 077) != 0 )); then
  echo "Backup encryption key file must not be accessible to group/other users (use chmod 600)" >&2; exit 1
fi
for required in PGHOST PGPORT PGUSER; do
  [[ -n "${!required:-}" ]] || { echo "$required is required" >&2; exit 1; }
done
export PGDATABASE="${PGDATABASE:-postgres}" PGPASS_DATABASE='*'

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_postgres_auth.sh
source "$script_dir/_postgres_auth.sh"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/schoolcms-restore-rehearsal.XXXXXXXX")"
chmod 700 "$work_dir"
suffix="$(date -u +%s)-$$"
source_db="schoolcms_rehearsal_${suffix}"
target_db="schoolcms_restore_${suffix}"
source_created=0
target_created=0
cleanup() {
  export PGDATABASE=postgres
  if [[ "$source_created" == "1" ]]; then
    dropdb --if-exists --no-password "$source_db" >/dev/null 2>&1 || true
  fi
  if [[ "$target_created" == "1" ]]; then
    dropdb --if-exists --no-password "$target_db" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$work_dir"
  _postgres_auth_cleanup
}
trap cleanup EXIT

createdb --no-password "$source_db"
source_created=1
export PGDATABASE="$source_db"
psql --no-password --set ON_ERROR_STOP=1 --command \
  "CREATE TABLE restore_probe (marker text PRIMARY KEY); INSERT INTO restore_probe VALUES ('backup-restore-ok');"
export BACKUP_OUTPUT_DIR="$work_dir"
"$script_dir/backup-postgres.sh"
backup_file="$(find "$work_dir" -maxdepth 1 -type f -name '*.dump.enc' -print -quit)"
[[ -n "$backup_file" ]] || { echo "Encrypted backup artifact was not produced" >&2; exit 1; }

createdb --no-password "$target_db"
target_created=1
export PGDATABASE="$target_db"
export RESTORE_TARGET_DISPOSABLE=YES RESTORE_TARGET_ENVIRONMENT=disposable DJANGO_ENVIRONMENT=disposable
"$script_dir/restore-postgres.sh" "$backup_file"
restored="$(psql --no-password --tuples-only --no-align --command "SELECT marker FROM restore_probe")"
[[ "$restored" == "backup-restore-ok" ]] || { echo "Restored data did not match rehearsal marker" >&2; exit 1; }
if "$script_dir/restore-postgres.sh" "$backup_file" >"$work_dir/nonempty-target.log" 2>&1; then
  echo "Restore unexpectedly accepted a non-empty target database" >&2
  exit 1
fi
if ! grep -q "target database must be empty" "$work_dir/nonempty-target.log"; then
  echo "Restore failed for an unexpected reason during the non-empty target check" >&2
  exit 1
fi
restored="$(psql --no-password --tuples-only --no-align --command "SELECT marker FROM restore_probe")"
[[ "$restored" == "backup-restore-ok" ]] || { echo "Refused restore changed the target data" >&2; exit 1; }
echo "Encrypted PostgreSQL restore rehearsal passed"
