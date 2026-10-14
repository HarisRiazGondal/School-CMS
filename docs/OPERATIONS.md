# Operations

## Local development

Install the pinned Django minor line and other dependencies with `python -m pip install -r requirements.txt`. Copy `.env.example` to `.env` for a local run, then migrate and start the server. `DEBUG=True`, SQLite, and the sample development secret are strictly local conveniences.

Use `python manage.py seed_demo --password <chosen-password>` to populate a synthetic browser demo. The command refuses to run with `DEBUG=False`. The password is supplied at invocation time and is not stored in source control. Demo accounts and records are intentionally predictable, so never seed a database that contains real data.

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
