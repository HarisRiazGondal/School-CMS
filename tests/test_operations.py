import os
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[1]


class ProductionDeliveryContractTests(SimpleTestCase):
    def test_backup_early_validation_failure_removes_temporary_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {key: value for key, value in os.environ.items() if key not in {"PGPASSFILE", "BACKUP_ENCRYPTION_KEY_FILE"}}
            env.update(TMPDIR=directory, PGHOST="localhost", PGPORT="5432", PGDATABASE="disposable", PGUSER="synthetic", PGPASSWORD="synthetic-test-value")
            result = subprocess.run([str(ROOT / "scripts" / "backup-postgres.sh")], env=env, capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("synthetic-test-value", result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_container_and_compose_have_production_boundaries(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        compose = (ROOT / "compose.yaml").read_text()
        caddy = (ROOT / "deploy" / "Caddyfile").read_text()

        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn('"gunicorn", "schoolcms.wsgi:application"', dockerfile)
        self.assertIn("postgres_data:/var/lib/postgresql/data", compose)
        self.assertIn("${DJANGO_SECRET_KEY_FILE:?", compose)
        self.assertIn("${DATABASE_URL_FILE:?", compose)
        self.assertIn("${DJANGO_EMAIL_HOST_PASSWORD_FILE:?", compose)
        self.assertIn("/health/ready/", compose)
        self.assertIn("/var/lib/schoolcms/private", compose)
        self.assertIn("clamav/clamav:1.5.4", compose)
        self.assertIn("scanner_egress", compose)
        self.assertIn("mfa_encryption_key", compose)
        self.assertNotIn('"5432:5432"', compose)
        self.assertIn("reverse_proxy web:8000", caddy)
        self.assertIn("{$CADDY_DOMAIN}", caddy)
        self.assertIn("header_up X-Forwarded-For {remote_host}", caddy)
        self.assertNotIn("--access-logfile", dockerfile)

    def test_github_actions_job_environment_avoids_step_only_runner_context(self):
        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text()
        # runner.temp is unavailable in jobs.<job_id>.env. Keep the disposable
        # CI paths on the Linux runner's temporary filesystem without using it
        # in an expression that GitHub evaluates before dispatching the job.
        postgres_job = workflow.split("  postgres:\n", 1)[1].split("\n  security:\n", 1)[0]
        job_environment = postgres_job.split("    env:\n", 1)[1].split("    steps:\n", 1)[0]
        self.assertNotIn("${{ runner.temp }}", job_environment)
        self.assertIn("PRIVATE_FILE_ROOT: /tmp/schoolcms-private-files", job_environment)
        self.assertIn("BACKUP_ENCRYPTION_KEY_FILE: /tmp/schoolcms-backup-key", job_environment)

    def test_ci_runs_real_recovery_and_isolated_browser_harnesses(self):
        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text()
        browser_requirements = (ROOT / "requirements-e2e.txt").read_text()
        browser_script = (ROOT / "scripts" / "browser_acceptance.py").read_text()
        recovery_script = (ROOT / "scripts" / "recovery-rehearsal.py").read_text()

        self.assertIn("RECOVERY_REHEARSAL_DISPOSABLE=YES python3 scripts/recovery-rehearsal.py", workflow)
        self.assertIn("postgres:17-bookworm", workflow)
        self.assertIn('scripts / "backup-bundle.py"', recovery_script)
        self.assertIn('scripts / "restore-bundle.py"', recovery_script)
        self.assertIn("python -m pip install -r requirements.txt -r requirements-e2e.txt", workflow)
        self.assertIn("playwright install --with-deps chromium", workflow)
        self.assertIn("npm ci --prefix tests/e2e", workflow)
        self.assertIn("python scripts/browser_acceptance.py", workflow)
        self.assertIn("playwright==", browser_requirements)
        self.assertIn("if: failure()", workflow)
        self.assertIn("schoolcms-e2e-", browser_script)
        # External production checks are intentionally not a required CI gate.
        self.assertNotIn("verify_release --json", workflow)

    def test_migrations_are_not_part_of_web_startup(self):
        compose = (ROOT / "compose.yaml").read_text()
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertNotIn("migrate --noinput", compose)
        self.assertNotIn("migrate --noinput", dockerfile)

    def test_restore_refuses_without_disposable_confirmation(self):
        with tempfile.NamedTemporaryFile() as backup:
            environment = {**os.environ}
            environment.pop("DJANGO_ENVIRONMENT", None)
            environment.update({
                "RESTORE_TARGET_DISPOSABLE": "YES",
                "RESTORE_TARGET_ENVIRONMENT": "disposable",
            })
            result = subprocess.run(
                [str(ROOT / "scripts" / "restore-postgres.sh"), backup.name],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ENVIRONMENT must be explicitly set", result.stderr)
        self.assertNotIn("PGPASSWORD", result.stderr)

    def test_backup_and_restore_use_encrypted_artifacts_and_no_clean_restore(self):
        backup = (ROOT / "scripts" / "backup-postgres.sh").read_text()
        restore = (ROOT / "scripts" / "restore-postgres.sh").read_text()
        self.assertIn("openssl enc -aes-256-cbc", backup)
        self.assertIn("-pass \"file:$BACKUP_ENCRYPTION_KEY_FILE\"", backup)
        self.assertIn("School-CMS encrypted backup HMAC v1", backup)
        self.assertIn("pg_restore --no-password --exit-on-error", restore)
        self.assertIn("hmac.compare_digest", restore)
        self.assertNotIn("--clean", restore)
