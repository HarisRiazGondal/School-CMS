# Next Actions

Release branch `codex/production-hardening-20261015`, draft [PR #1](https://github.com/HarisRiazGondal/School-CMS/pull/1). Final local suite: **223 run, 214 passed, 9 PostgreSQL-only skips, no failures**. Pilot score 87.5%; production milestone8 In progress.

1. Inspect the new exact-commit Actions run and individual SQLite, PostgreSQL/concurrency/recovery, application security, container and browser jobs; resolve any retrievable failures.
2. Existing VPS selected: supply host/IP, SSH operator username and public domain with an approved connection; configure secret files, PostgreSQL and SMTP without posting credentials in chat.
3. Run verify_release --json on the real target, then authorized HTTPS/SMTP/scanner probes; review persistence, signature freshness, secret/key and volume ownership separately.
4. Rehearse a quiesced database-plus-private-files bundle on an isolated PostgreSQL target; record restored data/downloads, recovery time, off-host retention and named ownership.
5. Install and monitor bounded auth-throttle retention; complete hosted five-role, assistive-technology, privacy/security and operational acceptance before verifying milestone8.

Runbooks: RELEASE_PREFLIGHT.md, RECOVERY_REHEARSAL.md, BROWSER_ACCEPTANCE.md, AUTH_RETENTION.md, RELEASE_EVIDENCE.md and RELEASE_REVIEW.md under docs. Preflight defaults to no network/mail/scanner probes and cannot prove volume persistence. Recovery requires quiescence and explicit disposable empty DB/file targets. Browser runner owns loopback-only synthetic SQLite. No external timer, live deployment, email or user pilot was performed.

Update exact test totals, source/target evidence, blockers, all affected AI-context Markdown/JSON and generated HTML in every checkpoint. Keep PR draft/main unchanged until release gates are independently reviewed.
