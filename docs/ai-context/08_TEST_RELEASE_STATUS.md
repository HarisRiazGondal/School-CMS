# Test and Release Status

**Production release candidate; acceptance pending. Pilot score remains87.5%.**

2026-10-15 local integrated run: **183 tests run,175 passed,8 PostgreSQL-only concurrency tests skipped** in95.384 seconds. This is not183 PostgreSQL passes.

| Check | Actual evidence |
|---|---|
| SQLite full suite |175 passed,8 PG-only skips |
| Django check / migration drift |Clean / no changes |
| Fresh SQLite migrate |Passed |
| Dependency audit |No known vulnerabilities after pypdf6.20.1 upgrade |
| Bandit app source |0 findings; narrow reviewed inline exceptions documented in OPERATIONS |
| Static collection |127 assets and compressed manifest generated |
| Synthetic production deploy check |No errors; intentional W005/W021 retained for staged HSTS |
| Shell syntax / YAML / restore refusal |Passed |
| First draft PR CI |Failure reported; logs404 and step details empty; cause not established |
| Real PostgreSQL concurrency/restore and image build |CI configured; success unverified |
| Real SMTP/TLS/ClamAV/private-volume restore |Not exercised |
| Hosted human/privacy/accessibility pilot |Not performed |

Targeted coverage includes DB login/reset/MFA throttling (including Admin, rotating IPs and replay/recovery), required and optional MFA, strict production startup, private attachment content/scanner/scope/history/permission/integrity guards, grading/upload row rechecks, health/headers/proxy, deployment/restore refusal and accessibility semantics. Baseline129 pilot tests remain included. Eight new PostgreSQL tests intentionally skip on SQLite.

A deadline HTTP test advances the shared clock beyond a one-hour session lifetime. Its fixture now uses a longer session to test late-body exclusion independently of session expiry; the affected33-test suite and final integrated suite pass. Production session protection was not weakened.

See PRODUCTION_REVIEW, PRIVACY_OPERATIONS, ACCESSIBILITY_ACCEPTANCE and OPERATIONS for reviewed changes and open operational gates. CI configuration and code presence do not certify production readiness.
