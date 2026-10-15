import os
from pathlib import Path
import secrets
import subprocess
import sys
from unittest.mock import patch, MagicMock

from cryptography.fernet import Fernet
from django.db import OperationalError
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse


class ProductionConfigurationTests(SimpleTestCase):
    def environment(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith(("DJANGO_", "MFA_", "PRIVATE_FILE_", "DATABASE_URL"))}
        env.update({
            "DJANGO_DEBUG": "false", "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
            "DJANGO_ALLOWED_HOSTS": "cms.example.test", "DJANGO_CSRF_TRUSTED_ORIGINS": "https://cms.example.test",
            "DATABASE_URL": "postgresql://test:test@127.0.0.1:5432/disposable",
            "MFA_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "PRIVATE_FILE_ROOT": "/tmp/schoolcms-release-private", "PRIVATE_FILE_SCANNER_COMMAND": "clamscan --no-summary {path}",
            "DJANGO_EMAIL_HOST": "smtp.example.test", "DJANGO_EMAIL_USE_TLS": "true",
            "DJANGO_DEFAULT_FROM_EMAIL": "cms@example.test",
        })
        return env

    def load_settings(self, env, deploy_check=False):
        command = [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "ERROR"] if deploy_check else [sys.executable, "-c", "from schoolcms import settings; assert settings.MFA_REQUIRED_FOR_STAFF; assert settings.MFA_REQUIRED_FOR_PRIVILEGED_ROLES"]
        return subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)

    def test_complete_production_config_passes_deploy_checks(self):
        result = self.load_settings(self.environment(), deploy_check=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Subdomain HSTS/preload require a verified domain inventory. These two
        # warnings are retained explicitly instead of enabling either blindly.
        self.assertIn("security.W005", result.stderr)
        self.assertIn("security.W021", result.stderr)

    def test_missing_or_unsafe_production_settings_fail_closed(self):
        cases = [
            ("DATABASE_URL", None, "PostgreSQL"), ("DATABASE_URL", "sqlite:////tmp/unsafe.sqlite3", "PostgreSQL"),
            ("DJANGO_ALLOWED_HOSTS", "*", "wildcards"), ("DJANGO_CSRF_TRUSTED_ORIGINS", "http://cms.example.test", "HTTPS"),
            ("MFA_ENCRYPTION_KEY", "invalid", "MFA_ENCRYPTION_KEY"),
            ("PRIVATE_FILE_ROOT", str(Path(__file__).resolve().parent.parent / "media"), "PRIVATE_FILE_ROOT"),
            ("PRIVATE_FILE_SCANNER_COMMAND", "", "SCANNER"), ("DJANGO_HSTS_SECONDS", "0", "HSTS"),
            ("DJANGO_EMAIL_USE_TLS", "false", "SMTP TLS"), ("DJANGO_EMAIL_HOST", "localhost", "SMTP"),
        ]
        for key, value, message in cases:
            with self.subTest(key=key, value=value):
                env = self.environment()
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = value
                result = self.load_settings(env)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)


@override_settings(DEBUG=True)
class HealthAndResponseTests(TestCase):
    def test_health_routes_are_generic_and_readiness_checks_database_and_migrations(self):
        self.assertEqual(self.client.get(reverse("health_live")).json(), {"status": "ok"})
        self.assertEqual(self.client.get(reverse("health_ready")).status_code, 200)
        with patch("schoolcms.health.MigrationExecutor") as executor:
            executor.return_value.migration_plan.return_value = [object()]
            response = self.client.get(reverse("health_ready"))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"status": "unavailable"})
        with patch("schoolcms.health.connection.cursor", side_effect=OperationalError("sensitive database details")):
            response = self.client.get(reverse("health_ready"))
            self.assertEqual(response.status_code, 503)
            self.assertNotContains(response, "sensitive", status_code=503)

    def test_account_pages_have_private_cache_and_browser_security_headers(self):
        response = self.client.get(reverse("login"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])
        self.assertIn("camera=()", response["Permissions-Policy"])

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_trusted_tls_edge_does_not_redirect_loop_but_plain_http_redirects(self):
        self.assertEqual(self.client.get(reverse("login"), HTTP_X_FORWARDED_PROTO="https").status_code, 200)
        self.assertEqual(self.client.get(reverse("login")).status_code, 301)
        self.assertEqual(self.client.get(reverse("health_live")).status_code, 200)
