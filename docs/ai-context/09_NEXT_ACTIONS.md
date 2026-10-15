# Next Actions

Release branch `codex/production-hardening-20261015`, draft PR1. Local175 passed/8 PG skips; unchanged pilot score87.5%, production milestone8 In progress.

1. Inspect the draft PR PostgreSQL17/concurrency, encrypted restore, container build and security CI jobs; fix failures. The first CI run failed and its logs/step details were unavailable through the connector.
2. Provide a controlled target host/domain and operator-managed PostgreSQL/SMTP/secret files; validate nonroot volume/secret permissions and start the reviewed stack.
3. Verify TLS/cookie/proxy behavior, real password-reset delivery and ClamAV clean/infected/unavailable paths with current signatures.
4. Run encrypted database plus private-files backup restoration and record measured recovery time, data checks, retention and operator ownership.
5. Complete hosted five-role pilot, keyboard/screen-reader/viewport and privacy/security/monitoring acceptance before marking milestone8 Verified.

Update measured passed/skipped totals, CI outcomes, affected memory/JSON/HTML in every checkpoint. Keep operational evidence distinct from code/config tests.
