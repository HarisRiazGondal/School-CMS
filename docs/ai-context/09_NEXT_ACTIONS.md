# Next Actions — local acceptance

User instruction: defer CI/VPS work, test locally and identify remaining bugs. Release branch `codex/production-hardening-20261015`, draft PR#1. Final local regression: **224 tests run, 215 passed, 9 PostgreSQL-only skips, no failures**.

1. Test the release branch locally using docs/TESTING_MVP.md; review docs/LOCAL_TEST_REPORT.md for current findings and earlier review links.
2. Complete all five synthetic role journeys on the user computer: admissions/corrections, assessment marking/publication, payments/reversals and promotion/history.
3. Log reproducible issues with role, route, synthetic input, expected/actual behavior and traceback/screenshot; fix and rerun affected checks.
4. When local dependencies are available, run Chromium/axe and PostgreSQL-specific tests; real antivirus/mail/recovery checks require their configured services.
5. Resume CI/VPS/hosted production acceptance separately when requested; retain existing open release gates.

Two confirmed defects are fixed: excessive financial Decimal magnitude and teacher dashboard correction navigation. No failing local automated check remains in the exercised cases. Browser/axe execution is unverified because Chromium is absent. Nine PostgreSQL tests skip under SQLite. Use synthetic data and disposable DBs; keep real pupil data and credentials outside the repository.

Latest evidence/index: `docs/LOCAL_TEST_REPORT.md`; role checklist: `docs/TESTING_MVP.md`; historical reviews: PROJECT_REVIEW, PRODUCTION_REVIEW and RELEASE_REVIEW. Do not add old review totals together. Keep production acceptance open and update affected memory/JSON/HTML with future changes.
