# Production release acceptance

Status: **release candidate, not approved for real pupil data**. Draft PR #1: https://github.com/HarisRiazGondal/School-CMS/pull/1

| Gate | Current evidence | Required before release |
|---|---|---|
| Application regression |176 pass, 8 PG skips |Green target PostgreSQL full suite/concurrency |
| Authentication |DB throttles, encrypted TOTP, recovery/replay/session tests |Provision accounts and verify MFA/recovery on target |
| Dependencies/source |Pinned packages; clean audit/source scan |Repeat on final built artifact |
| Private files |16 scanner/content/scope/integrity tests |Real ClamAV fresh signatures; mounted-volume smoke and restore |
| Deployment |Strict settings, nonroot image, manifest/health/proxy code |Build and start stack; confirm secret/volume ownership, TLS/cookies |
| Backups |Authenticated encryption and empty-target guards |Actual DB+files restoration, measured recovery and off-host copy |
| SMTP |TLS-required settings; enumeration-safe reset tests |Controlled mailbox reset delivery using real host |
| Accessibility/privacy |Semantics and scoped HTTP tests; runbooks |Keyboard/screen-reader/viewport and school/operator signoff |
| Operations |Health and recovery scripts/runbook |Monitoring alerts, retention owner and incident rehearsal |

The first CI run failed without retrievable logs. Use the draftPR checks and current commit evidence before merging. The user selected an existing VPS. Its host/IP, SSH username and public domain, real SMTP setup, external PostgreSQL acceptance and human signoff are still required. Integration discovery did not find a suitable connected VPS/SSH capability. Supply those through the deployment secret manager and use deploy/production.env.example plus OPERATIONS; never paste secrets in chat or commit them. Local Docker/PG runtime and browser installation were unavailable. These are concrete release blockers, not a reason to claim100% completion.
