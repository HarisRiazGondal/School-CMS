# Production release preflight

`python manage.py verify_release --json` gathers local production-configuration, live database, migration, private-file directory, scanner, SMTP, source revision, and runtime evidence. It is read-only by default. The report contains a UTC timestamp, exact Git HEAD when available, a clean-worktree check, Python/Django/platform metadata, and individual checks with `passed`, `failed`, or `blocked` status. A dirty worktree blocks source evidence because HEAD does not identify uncommitted code. It never emits configured secret values or exception/server details. A non-passing report exits with status 1 while keeping JSON on stdout.

The preflight requires a production settings process. Development settings deliberately fail the production checks. Database evidence comes from the active connection and requires PostgreSQL; the command runs a version query and Django's unapplied migration plan. It will report SQLite as blocked even when the SQLite query succeeds. Run it using the same release image, environment, and service identity used by the target deployment.

## Optional operator probes

SMTP is never contacted unless `--network-checks` is supplied. That option attempts only the configured SMTP transport/TLS negotiation and sends no mail. To send a controlled test message, explicitly supply `--send-test-email operator-controlled-address@example.org` as well. Use only a mailbox whose operator has agreed to receive the message. Delivery is attempted only in that invocation; no message is sent by this document or by default command behavior.

An external health check requires both `--network-checks` and an explicit `--health-url https://host/health/ready/` (or `/health/live/`). The command requires an exact `ALLOWED_HOSTS` entry, HTTPS, no URL credentials/query/fragment, and DNS answers that are all globally routable. It pins the request to one validated DNS address while retaining TLS certificate verification and hostname SNI, and it does not follow redirects. The target must return the generic `{"status":"ok"}` body and expected browser/security headers. Invalid/private targets are rejected before an HTTP request. Only provide a public target you are authorized to probe.

Scanner executable availability is checked without scanning data. Signature readiness is reported as passed only for supported ClamAV `clamscan --version` output that includes its loaded signature count; unsupported scanner implementations are blocked rather than inferred healthy. `--probe-scanner` opts into writing two small temporary files (plain clean text and the standard EICAR antivirus test string) beneath the private root, invoking the configured scanner, and removing the temporary directory. The expected scanner exit codes are 0 for clean and 1 for detected EICAR. Probe only in an environment where this benign antivirus test is permitted. Scanner stdout/stderr and exception details are suppressed.

The private root check verifies that the configured path exists as a real directory, is owned by the service UID, and has no group/world permissions. It does not create or repair directories. Container/filesystem metadata cannot establish that storage survives container replacement, so persistence remains blocked until deployment-volume and restore evidence is recorded externally. A mounted path that passes the local permission checks is not, by itself, proof of backup or recoverability.

## Interpreting results

`failed` means a check ran and observed an unsafe setting or an operational error. `blocked` means a runtime, external target, or independent evidence was unavailable or deliberately skipped; it is never counted as a pass. `passed` applies only to the stated check. The report is not a release approval and does not complete target-host TLS, private-file restore, SMTP delivery, scanner signature update, human acceptance, backup recovery, or monitoring gates. Do not convert a local preflight report or an operator statement into a production acceptance percentage.

Example defaults (no network probes, mail, or scanner test):

```sh
python manage.py verify_release --json
```

Explicit, operator-authorized probes:

```sh
python manage.py verify_release --json --network-checks \
  --health-url https://cms.example.org/health/ready/ --probe-scanner
```

Add `--send-test-email` only when a controlled recipient is ready for one message.
