# Production release acceptance

Status: **release candidate, not approved for real pupil data**. Draft PR #1: https://github.com/HarisRiazGondal/School-CMS/pull/1

| Gate | Current evidence | Required before release |
|---|---|---|
| Application regression |215 pass, 9 PG skips |Green target PostgreSQL full suite/concurrency |
| Authentication |DB throttles, encrypted TOTP, recovery/replay/session tests |Provision accounts and verify MFA/recovery on target |
| Dependencies/source |Pinned packages; clean audit/source scan |Repeat on final built artifact |
| Private files |16 scanner/content/scope/integrity tests |Real ClamAV fresh signatures; mounted-volume smoke and restore |
| Deployment |Strict settings, nonroot image, manifest/health/proxy code |Build and start stack; confirm secret/volume ownership, TLS/cookies |
| Backups |Authenticated encryption and empty-target guards |Actual DB+files restoration, measured recovery and off-host copy |
| SMTP |TLS-required settings; enumeration-safe reset tests |Controlled mailbox reset delivery using real host |
| Accessibility/privacy |Semantics and scoped HTTP tests; runbooks |Keyboard/screen-reader/viewport and school/operator signoff |
| Operations |Health and recovery scripts/runbook |Monitoring alerts, retention owner and incident rehearsal |

Prior CI run#7 failed with zero jobs and unavailable logs; the invalid job-level runner context is corrected, and the new exact-commit run still requires verification. Use the draftPR checks and current commit evidence before merging. The user selected an existing VPS. Its host/IP, SSH username and public domain, real SMTP setup, external PostgreSQL acceptance and human signoff are still required. Integration discovery did not find a suitable connected VPS/SSH capability. Supply those through the deployment secret manager and use deploy/production.env.example plus OPERATIONS; never paste secrets in chat or commit them. Local Docker/PG runtime and browser installation were unavailable. These are concrete release blockers, not a reason to claim100% completion.

The next validation tools are [runtime preflight](RELEASE_PREFLIGHT.md), [complete recovery](RECOVERY_REHEARSAL.md), [synthetic browser acceptance](BROWSER_ACCEPTANCE.md), [auth retention](AUTH_RETENTION.md), [review](RELEASE_REVIEW.md) and [evidence accounting](RELEASE_EVIDENCE.md). No target-host gate is closed by their implementation alone.

## Confirmed CI startup blocker

Runs #8/#9 at 6e3b0a6558267ca3cbed8a3696811e4f5cea73eb each created five jobs but no runners or steps. The public job annotation confirms: "The job was not started because your account is locked due to a billing issue." The account owner must resolve this outside the repository before rerunning CI. No PostgreSQL, recovery, container or browser CI pass occurred.

[Verified job annotation](https://github.com/HarisRiazGondal/School-CMS/actions/runs/38771801513/job/116549229916). Resolve the account issue and rerun the exact release commit before evaluating hosted acceptance.
