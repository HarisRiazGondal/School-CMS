# Release review and evidence boundary

Latest local acceptance (15 October2026): **224 run,215 passed,9 PostgreSQL-only skips,no failures**, after the financial-validation and teacher-navigation fixes. See [LOCAL_TEST_REPORT.md](LOCAL_TEST_REPORT.md) for the consolidated report and index. Earlier counts below are historical snapshots; CI/VPS work is currently deferred.


Reviewed for the 2026-10-15 production hardening checkpoint. This is an engineering review of repository code and retrievable checks, not a security certification or permission to process real school records. The branch remains a release candidate; production milestone 8 is still in progress and the verified pilot score remains 7/8 (87.5%).

## Findings and local controls

- **Authentication and MFA:** privileged staff and school administrator/accountant roles are required to use MFA in production settings. Login throttling is shared through the database, MFA secrets are Fernet-encrypted, recovery codes are keyed hashes consumed under a row lock, and successful TOTP steps are checked against the last accepted step. Review the related behavior in `accounts/auth_security.py`, `accounts/views.py` and `accounts/middleware.py`; focused regression coverage is in `tests/test_auth_security.py`. This code review and local tests do not verify the production key lifecycle, real SMTP reset delivery, or hosted browser behavior.
- **Private files:** attachments are stored outside public media under opaque names, checked for size/type/content, scanned fail-closed, scoped on upload/download, and rechecked for file permissions and content hash when opened. Database and filesystem recovery must be validated as one set; the database-only PostgreSQL rehearsal does not prove private-file restoration.
- **Backup and recovery:** the database backup script encrypts the dump and authenticates it before restore. The database-plus-private-files bundle requires a quiesced marker, matches its manifest to staged file contents, authenticates the encrypted outer artifact, validates the disposable target and publishes the staged private tree only after database restoration. New bundle/rehearsal code is subject to its own tests and needs a successful real-PostgreSQL rehearsal before operational acceptance.
- **Deployment and preflight:** the application container is configured non-root with a read-only root filesystem; PostgreSQL and ClamAV have no published ports. Preflight network probes are explicit opt-ins. A preflight `passed` result cannot establish mounted-volume persistence, actual retention ownership, complete private-file recovery, real end-user acceptance, or availability of the target host.
- **Status accounting:** the dashboard keeps the 7/8 implementation score separate from production release gates. `scripts/release_state.py` checks test arithmetic, milestone names and production criteria, gate coverage, required evidence fields and readiness-label consistency; the renderer escapes displayed values. The validator does not authenticate an evidence artifact or reviewer identity. Its synthetic-evidence unit test exercises the required-field schema only, so gate closure still depends on a human reviewing genuine evidence.

## CI execution evidence

The GitHub Actions workflow run for commit `2fd821a715eb85e83e6834e62cad9cf7ebc776df` (run **38700616784**, workflow run #7) was marked failed. The read-only Jobs API response was `total_count: 0`; the run logs endpoint returned 404. The prior retrievable run #6 (38694740383) also had no jobs. Earlier failed attempts returned a nominal `sqlite-tests` job with an empty runner name and no steps. These records contain no evidence that SQLite tests, PostgreSQL tests, restore, scans, or image checks actually ran.

Code inspection found `${{ runner.temp }}` referenced from the PostgreSQL job-level `env` block. GitHub's [Actions context-availability table](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability) does not permit the `runner` context at that workflow key. The CI owner changed those values to explicit `/tmp` paths and added a regression check. That is a plausible explanation for validation failing before a runner/job was created; a new hosted run must succeed before attributing the cause as confirmed or treating the CI gates as passed.

## Open release gates

1. Obtain a successful workflow run for the current release commit, including the PostgreSQL/concurrency/recovery, security-scan and container jobs. Keep each job's actual outcome distinct from workflow configuration or a local simulation.
2. Verify against the selected VPS once its host, SSH operator and public domain are available. Record target HTTPS, trusted proxy and cookie behavior, service health, volume permissions/persistence, SMTP delivery and ClamAV clean/infected/unavailable behavior.
3. Rehearse an authenticated encrypted database-plus-private-files backup and restore on an isolated PostgreSQL target. Record integrity checks, restored authorization/download behavior, measured recovery time, retention, and named operator ownership.
4. Complete privacy, accessibility, monitoring/incident-response and five-role human acceptance before onboarding real users.

The required production evidence is not available from this local review: the VPS identity/access/domain were not supplied, local PostgreSQL and Docker acceptance were unavailable, and no hosted human pilot or full recovery rehearsal has been recorded. Do not mark production ready or report 100% production completion based on code presence, SQLite results, or configured jobs.

## Authentication throttle retention

Review initially found that stale `AuthThrottle` buckets had no cleanup path. A bounded `prune_auth_throttles` management command now supports a dry run and explicit deletion, uses database time, and preserves active blocks; see `docs/AUTH_RETENTION.md`. No timer or scheduled task is installed by this repository. An operator still needs to review the first dry run and schedule/monitor bounded cleanup in the deployment environment. This closes the missing cleanup mechanism locally, not the operational ownership gate.

## Review-local verification

The last integrated local run recorded at commit `2fd821a715eb85e83e6834e62cad9cf7ebc776df` reported 184 tests run, 176 passed, and 8 PostgreSQL-only tests skipped on SQLite. These are baseline results before the release-review, preflight, browser, and combined-recovery additions; they do not assert that those additions or the PostgreSQL workflow passed. The parent integrates runtime regression coverage and records the final full-suite result in `ai-context/08_TEST_RELEASE_STATUS.md`. Documentation wording is reviewed directly rather than tested through exact string assertions.

## Published run follow-up

Runs #8/#9 at 6e3b0a6558267ca3cbed8a3696811e4f5cea73eb each created five jobs but no runners or steps. The public job annotation confirms: "The job was not started because your account is locked due to a billing issue." The account owner must resolve this outside the repository before rerunning CI. No PostgreSQL, recovery, container or browser CI pass occurred.

[Verified public job annotation](https://github.com/HarisRiazGondal/School-CMS/actions/runs/38771801513/job/116549229916). The corrected workflow now creates jobs, unlike the prior invalid-context run. A later repository correction sets the settings module for standalone Python and pins Ubuntu24.04; its focused operations tests pass7/7. The account billing lock prevents runtime verification of those paths.
