#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_postgres_auth.sh
source "$script_dir/_postgres_auth.sh"

: "${BACKUP_ENCRYPTION_KEY_FILE:?Set BACKUP_ENCRYPTION_KEY_FILE to a protected file containing a strong random key/passphrase}"
_require_private_file "$BACKUP_ENCRYPTION_KEY_FILE" "Backup encryption key file"
[[ -n "${PGDATABASE:-}" ]] || { echo "PGDATABASE is required" >&2; exit 1; }

output_dir="${BACKUP_OUTPUT_DIR:-./backups}"
mkdir -p -- "$output_dir"
chmod 700 "$output_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
safe_database_name="${PGDATABASE//[^a-zA-Z0-9_-]/_}"
safe_database_name="${safe_database_name:0:80}"
destination="$(mktemp --suffix=.dump.enc "$output_dir/${safe_database_name}-${timestamp}-XXXXXXXX")"
plain_dump="$(mktemp "${TMPDIR:-/tmp}/schoolcms-pg-dump.XXXXXXXX")"
chmod 600 "$plain_dump"
trap 'rm -f -- "$plain_dump"; _postgres_auth_cleanup' EXIT

pg_dump --no-password --format=custom --file="$plain_dump"
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 600000 \
  -in "$plain_dump" -out "$destination" \
  -pass "file:$BACKUP_ENCRYPTION_KEY_FILE"
chmod 600 "$destination"
sha256sum "$destination" > "$destination.sha256"
chmod 600 "$destination.sha256"
python3 - "$destination" "$BACKUP_ENCRYPTION_KEY_FILE" <<'PY'
import hashlib
import hmac
import pathlib
import sys

artifact, key_file = map(pathlib.Path, sys.argv[1:])
passphrase = key_file.read_bytes().rstrip(b"\r\n")
mac_key = hashlib.sha256(b"School-CMS encrypted backup HMAC v1\0" + passphrase).digest()
digest = hmac.new(mac_key, digestmod=hashlib.sha256)
with artifact.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
mac = digest.hexdigest()
artifact.with_name(artifact.name + ".hmac").write_text(mac + "\n")
PY
chmod 600 "$destination.hmac"
printf 'Encrypted backup created: %s\n' "$destination"
