import os
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[1]


class ProductionDeliveryContractTests(SimpleTestCase):
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
