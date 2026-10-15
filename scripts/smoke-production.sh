#!/usr/bin/env bash
set -euo pipefail

: "${BASE_URL:?Set BASE_URL to the HTTPS origin, for example https://school.example.org}"
base_url="${BASE_URL%/}"
case "$base_url" in https://*) ;; *) echo "BASE_URL must use HTTPS" >&2; exit 1 ;; esac

for endpoint in /health/live/ /health/ready/; do
  status="$(curl --fail --silent --show-error --output /dev/null --write-out '%{http_code}' "$base_url$endpoint")"
  [[ "$status" == "200" ]] || { echo "Health check failed at $endpoint (HTTP $status)" >&2; exit 1; }
done
echo "HTTPS liveness and readiness checks passed for $base_url"
