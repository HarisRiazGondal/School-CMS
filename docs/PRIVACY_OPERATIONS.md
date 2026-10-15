# Private learning attachments: operations boundary

The `privatefiles` app stores opaque file keys under `PRIVATE_FILE_ROOT`, separate from `STATIC_ROOT` and Django's media configuration. There is no public media URL or direct file-serving route. Downloads pass through the authenticated authorization view, are always sent as attachments, and set `nosniff` and `private, no-store` headers. The only accepted file formats are PDF and UTF-8 plain text (`.pdf`, `.txt`, `.text`); the app validates PDF structure with bounded parsing, rejects active/embedded PDF features, and validates UTF-8 text encoding, and applies a configurable byte limit before scanning.

## Required production configuration

Set `PRIVATE_FILE_ROOT` to an absolute path on a dedicated persistent mount outside the repository, web root and `STATIC_ROOT`, with restrictive ownership and permissions. The production settings reject a missing or unsafe path. Keep it off any static/media CDN or web-server alias. Set `PRIVATE_FILE_MAX_BYTES` to the approved upload limit. Configure `PRIVATE_FILE_SCANNER_COMMAND` to a locally installed, maintained ClamAV scanner command, for example `clamscan --no-summary {path}`. The scanner command is invoked without a shell; `{path}` is replaced by the private staged file path. A scanner return code of 0 means clean, 1 means infected and quarantined, while any other return code, timeout, missing command or execution error rejects the upload. There is no bypass mode. Keep signatures updated and monitor scanner health through deployment operations without logging file contents or user-provided names.

Configure and test these settings in every deployment before enabling upload. This repository's automated scanner tests use a controlled fake scanner; they do not establish that a production scanner is installed, reachable, current, or operational. The production gate remains open until operations verifies those facts.

## Access and audit

Teacher access uses the existing active school membership and exact section/subject assignment checks; matching school administrators use their existing school-scoped access. Student uploads require the active enrollment for the assignment and must target that student's own submission. A student's own submission attachments remain readable after promotion when the historical enrollment is no longer active. Other users' files, quarantined files, and attachments with missing storage objects are denied. Audit events contain owner identifiers, size and scan status, but never file bytes or original filenames.

The download endpoint streams the file from private storage and does not expose a filesystem path. Original names are sanitized basenames for `Content-Disposition` only. Random storage keys do not incorporate student, assignment, submission or user identifiers. Files and metadata are retained; no automatic orphan purge or destructive cleanup is provided.

## Backups, restore and retention

Back up the database and the entire configured private attachment root as one coordinated delivery set. Encrypt backups in transit and at rest, restrict backup access to named operators, and keep retention aligned with the school-approved records schedule. Record the database backup timestamp and private-volume snapshot/version together. Test restoration into an isolated environment, verify the restored metadata-to-file set and permissions, and validate authorized downloads before accepting the restore. A database-only restore or file-volume-only restore can leave broken references or untracked files.

Before retention or deletion work is introduced, obtain an approved schedule and implement a report-only dry run that identifies candidate metadata and files. Review its output and obtain operational authorization before any purge. Do not delete files merely because a filesystem scan finds no apparent database reference.

## Production acceptance still required

Local tests prove application-level scope, response headers, format/size checks and fail-closed scanner behavior only. They do not establish legal/privacy acceptance, school retention policy, malware scanner operations, production filesystem isolation, encrypted backup restoration, hosted authorization behavior, or PostgreSQL behavior. Complete and record those checks before real pupil files are enabled.
