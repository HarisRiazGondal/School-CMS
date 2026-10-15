# Independent production and security review

Latest local acceptance (15 October2026): **224 run,215 passed,9 PostgreSQL-only skips,no failures**, after the financial-validation and teacher-navigation fixes. See [LOCAL_TEST_REPORT.md](LOCAL_TEST_REPORT.md) for the consolidated report and index. Earlier counts below are historical snapshots; CI/VPS work is currently deferred.


Reviewed 2026-10-15 against the current repository state. This is an engineering review, not a security certification or a claim that the service is ready for real pupil data.

## Findings verified in code

- **Closed locally: production can no longer silently fall back to SQLite.** With `DEBUG=False`, startup requires a PostgreSQL URL, explicit non-wildcard hosts and HTTPS CSRF origins, a non-placeholder Django key, a separate valid MFA encryption key, an absolute private file root outside the application directory, a scanner command, explicit TLS SMTP, and HSTS of at least one hour. `tests.test_production_review` checks both valid settings and fail-closed cases. The independent release configuration tests also exercise Django's deployment checks.
- **Closed locally: forwarded HTTPS state is opt-in.** `SECURE_PROXY_SSL_HEADER` is set only when `DJANGO_TRUST_PROXY=true`; the deployment stack keeps the app port private behind Caddy and enables that setting there. Trusting forwarded headers on an Internet-facing application port would be unsafe. Django documents the trust boundary in its [proxy SSL setting](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header).
- **Closed locally: privileged accounts cannot use the password-only portal or Django Admin login path.** The custom login, enrollment and challenge routes are wired, MFA middleware intercepts privileged sessions including Admin's stock login, successful TOTP steps cannot be replayed, recovery codes are one-time, pending enrollment is time/password-hash bound, and MFA attempts are throttled. Regression coverage is in `tests/test_auth_security.py`; independent source review also checked the middleware and routes.
- **Closed locally: private uploads are not served as public media.** Files use opaque random keys, a private volume, strict upload limits and type checks, structural PDF validation, fail-closed scanning, scoped download authorization, attachment disposition and no-store/nosniff headers. Quarantined files are not downloadable. `_root()` now rejects symlinks and fails if it cannot enforce owner-only directory permissions; `tests.test_production_review` includes the permission-failure regression.
- **Closed locally: production release and restore scripts have explicit safety gates.** The container runs as a non-root user with a read-only root filesystem, Compose keeps PostgreSQL off published ports, migrations are a separate release action, and the restore script requires a disposable target and empty schema. Backups are encrypted and authenticated before restore. The PostgreSQL CI job is configured to run a dump/restore rehearsal, but CI configuration is not evidence that a hosted restore succeeded.
- **Dependency review:** the installed Django is 5.2.18 and `requirements.txt` pins that patch. Django's [6 October 2026 security release](https://www.djangoproject.com/weblog/2026/oct/06/security-releases/) identifies 5.2.18 as the patched 5.2 release for the listed issues. The installed packages match the requirements pins; `python -m pip_audit -r requirements.txt` reported **No known vulnerabilities found** on 2026-10-15. Repeat this scan when dependencies change.

## Remaining production blockers

These are deployment acceptance gates, not defects that a local code test can close:

1. **PostgreSQL has not been exercised in this environment.** No `DATABASE_URL` was supplied, so PostgreSQL migrations, locking/concurrency behavior, and the test suite against the target database remain unverified here. The repository has PostgreSQL-specific concurrency tests and a CI job, but no hosted result was available during this review.
2. **The deployment stack was not started.** Docker is not installed in this workspace, so `docker compose config`, image build, container health, Caddy TLS, mount permissions, ClamAV connectivity/signature freshness, and real private-volume behavior were not verified.
3. **No external delivery or operational recovery was exercised.** SMTP/password-reset delivery, production account provisioning, encrypted backup creation and restoration against a live disposable PostgreSQL server, and monitoring/alert handling need recorded operational evidence.
4. **Human acceptance is outstanding.** Confirm HTTPS/cookie behavior at the target host, accessibility, privacy/retention ownership, incident response, and the five-role pilot before onboarding real users.

`manage.py check --deploy --fail-level ERROR` passed with a representative, synthetic production environment. Django reported only `security.W005` and `security.W021`, because HSTS subdomains and preload remain disabled until every relevant hostname has been verified. That is an intentional staged configuration; enable them only after the hostname inventory and HTTPS coverage are confirmed.

## Local review regressions

`DJANGO_DEBUG=true python manage.py test tests.test_production_review -v 1` — **4 tests passed**. These cover strict production startup configuration, explicit proxy trust, and fail-closed private storage permission handling. This focused run is not a substitute for the full test suite or target-host acceptance.

## Parent integrated evidence update

Final local suite:183 run,175 passed, 8 real-PG concurrency tests skipped. Source scan0 findings with narrow documented false-positive exceptions; dependency audit clean after pypdf 6.20.1 upgrade. First draftPR CI reported failure; log retrieval returned404/BlobNotFound and step metadata was empty, so the cause and PostgreSQL/restore/container results remain unverified. The workflow is consolidated and being retried. These results do not close target-host operational gates.

Latest parent verification supersedes the earlier183 total: **184 run, 176 passed, 8 PostgreSQL-only skips**. Backup early-failure cleanup passes; temporary pgpass credentials are removed even if later validation fails. Artifact names are unique and sanitized. CI retry also failed without retrievable logs; no remote success claim is made. The user chose an existing VPS, with actual connection/domain still required.
