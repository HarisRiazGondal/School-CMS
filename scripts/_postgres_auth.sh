#!/usr/bin/env bash
# Source this helper to give libpq tools a private pgpass file when operators
# provide PGPASSWORD. It never places credentials in command arguments.
set -euo pipefail

_postgres_auth_cleanup() { :; }

_require_private_file() {
  local file="$1" label="$2" mode
  [[ -r "$file" ]] || { echo "$label is not readable" >&2; return 1; }
  mode="$(stat -c '%a' -- "$file")"
  if (( (8#$mode & 077) != 0 )); then
    echo "$label must not be readable or writable by group/other users (use chmod 600)" >&2
    return 1
  fi
}

if [[ -n "${PGPASSFILE:-}" ]]; then
  _require_private_file "$PGPASSFILE" "PGPASSFILE" || return 1
  return 0
fi

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "Set PGPASSFILE or PGPASSWORD for PostgreSQL authentication" >&2
  return 1
fi

for required in PGHOST PGPORT PGDATABASE PGUSER; do
  [[ -n "${!required:-}" ]] || { echo "$required is required" >&2; return 1; }
done

_pgpass_escape() { local value="$1"; value=${value//\\/\\\\}; value=${value//:/\\:}; printf '%s' "$value"; }
_pgpass_tmp=$(mktemp)
_postgres_auth_cleanup() { rm -f -- "${_pgpass_tmp:-}"; }
# Cover callers that fail validation before installing their fuller cleanup trap.
trap _postgres_auth_cleanup EXIT
chmod 600 "$_pgpass_tmp"
printf '%s:%s:%s:%s:%s\n' \
  "$(_pgpass_escape "$PGHOST")" "$(_pgpass_escape "$PGPORT")" \
  "$(_pgpass_escape "${PGPASS_DATABASE:-$PGDATABASE}")" "$(_pgpass_escape "$PGUSER")" \
  "$(_pgpass_escape "$PGPASSWORD")" > "$_pgpass_tmp"
unset PGPASSWORD
export PGPASSFILE="$_pgpass_tmp"
