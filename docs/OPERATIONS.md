# Operations

## Local development

Install the pinned Django minor line and other dependencies with `python -m pip install -r requirements.txt`. Copy `.env.example` to `.env` for a local run, then migrate and start the server. `DEBUG=True`, SQLite, and the sample development secret are strictly local conveniences.

Use `python manage.py seed_demo --password <chosen-password>` to populate a synthetic browser demo. The command requires `DEBUG=True` and an operator-supplied password of at least eight characters; it does not embed or persist that password in source control. Each run applies that password to the known demo accounts (`demo-admin`, `demo-registrar`, `demo-teacher`, `demo-accountant`, and `demo-student`). Demo accounts and records are intentionally predictable, so never seed a database that contains real data.

The seed retains its baseline next-year Grade 8 / B placement fixture, creates an open Fractions mastery assessment with MCQ, true/false and manual short-answer questions, and issues Casey one annual-fee invoice. It creates no assessment attempts and posts no payments automatically. Rerunning the command does not recreate or overwrite existing assessment attempts, answers, posted invoices, payments, receipts or ledger entries; normal enrollment and promotion history is also preserved. Use the browser acceptance flows in `docs/TESTING_MVP.md` to test student submission, teacher marking, admin finalization/publication, statements, receipt issuance and payment reversal.

## Production baseline

- Set `DJANGO_DEBUG=false`, a unique random `DJANGO_SECRET_KEY` of at least 50 characters, `DJANGO_ALLOWED_HOSTS`, and a PostgreSQL `DATABASE_URL` through the deployment secret manager. Do not commit `.env` or copy development values into deployment.
- Terminate HTTPS at a trusted proxy/load balancer and configure proxy headers only for the actual trusted network. Secure session and CSRF cookies, redirect HTTP to HTTPS, and use the Django deployment check before release:

  ```sh
  python manage.py check --deploy
  ```

- Apply migrations as a controlled release step with a database backup and a rollback/restore plan. Keep media private by default and configure authorized delivery for any student records or documents.
- Restrict access to administrative accounts, use individual accounts, promptly deactivate leavers, and monitor authentication and sensitive record changes. Keep credentials and personal student data out of logs.
- Schedule encrypted database backups and periodically verify restoration in an isolated environment. Define retention and access policies for backups and uploaded files.
- Use a managed process supervisor and health monitoring for the web process. Collect errors and security events centrally with access controls and retention.

The project is an MVP and does not claim production readiness merely because `check --deploy` passes. Verify hosting, proxy, storage, backups, monitoring, incident response, and privacy obligations in the target environment before launch.
