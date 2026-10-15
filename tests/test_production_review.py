"""Independent release-configuration regressions for production settings."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from privatefiles.services import _root


ROOT = Path(__file__).resolve().parents[1]
VALID_PRODUCTION_ENV = {
    "DJANGO_SETTINGS_MODULE": "schoolcms.settings",
    "DJANGO_DEBUG": "false",
    "DJANGO_SECRET_KEY": "A1b2C3d4E5f6G7h8J9k0LmN1o2P3q4R5s6T7u8V9w0X1y2Z3a4B5c6D7e8F9g0H1",
    "DJANGO_ALLOWED_HOSTS": "school.example.test",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://school.example.test",
    "DATABASE_URL": "postgresql://schoolcms:secret@localhost:5432/schoolcms",
    "PRIVATE_FILE_ROOT": "/tmp/school-cms-review-private",
    "PRIVATE_FILE_SCANNER_COMMAND": "clamdscan --no-summary {path}",
    "MFA_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    "DJANGO_EMAIL_HOST": "smtp.example.test",
    "DJANGO_EMAIL_PORT": "587",
    "DJANGO_EMAIL_HOST_USER": "schoolcms",
    "DJANGO_EMAIL_HOST_PASSWORD": "dummy-password",
    "DJANGO_EMAIL_USE_TLS": "true",
    "DJANGO_DEFAULT_FROM_EMAIL": "School <noreply@example.test>",
    "DJANGO_TRUST_PROXY": "true",
}


class ProductionSettingsReviewTests(SimpleTestCase):
    def _run_python(self, script, changes=None):
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT)}
        env.update(VALID_PRODUCTION_ENV)
        for key, value in (changes or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, env=env,
            capture_output=True, text=True, check=False,
        )

    def test_production_requires_explicit_database_mfa_storage_and_hsts_config(self):
        cases = [
            ({"DJANGO_SECRET_KEY": None}, "DJANGO_SECRET_KEY must be set"),
            ({"DJANGO_SECRET_KEY": "replace-in-development"}, "strong, non-placeholder key"),
            ({"DJANGO_SECRET_KEY": "too-short"}, "strong, non-placeholder key"),
            ({"DATABASE_URL": None}, "Production requires a PostgreSQL DATABASE_URL"),
            ({"DATABASE_URL": "sqlite:////tmp/schoolcms.sqlite3"}, "Production requires PostgreSQL"),
            ({"MFA_ENCRYPTION_KEY": None}, "separate valid MFA_ENCRYPTION_KEY"),
            ({"PRIVATE_FILE_ROOT": None}, "persistent PRIVATE_FILE_ROOT"),
            ({"PRIVATE_FILE_ROOT": str(ROOT / "private" )}, "persistent PRIVATE_FILE_ROOT"),
            ({"DJANGO_HSTS_SECONDS": "0"}, "Production HSTS must be at least 3600 seconds"),
        ]
        for changes, expected_error in cases:
            with self.subTest(changes=changes):
                result = self._run_python("from django.conf import settings; print(settings.DEBUG)", changes)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stderr)

    def test_valid_production_settings_keep_proxy_and_private_data_controls_explicit(self):
        result = self._run_python(
            """from django.conf import settings
assert settings.DEBUG is False
assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql'
assert settings.SECURE_PROXY_SSL_HEADER == ('HTTP_X_FORWARDED_PROTO', 'https')
assert settings.SECURE_SSL_REDIRECT is True
assert settings.SECURE_HSTS_SECONDS >= 3600
assert settings.SESSION_COOKIE_SECURE and settings.SESSION_COOKIE_HTTPONLY
assert settings.CSRF_COOKIE_SECURE and settings.CSRF_COOKIE_HTTPONLY
assert settings.MFA_REQUIRED_FOR_STAFF and settings.MFA_REQUIRED_FOR_PRIVILEGED_ROLES
assert settings.PRIVATE_FILE_ROOT.is_absolute()
assert settings.PRIVATE_FILE_SCANNER_COMMAND
assert 'accounts.middleware.MFARequiredMiddleware' in settings.MIDDLEWARE
"""
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_forwarded_https_header_is_not_trusted_without_explicit_proxy_opt_in(self):
        result = self._run_python(
            "from django.conf import settings; assert settings.SECURE_PROXY_SSL_HEADER is None",
            {"DJANGO_TRUST_PROXY": None},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_private_storage_permission_hardening_failure_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(PRIVATE_FILE_ROOT=Path(temp_dir) / "private"):
                with patch.object(Path, "chmod", side_effect=PermissionError("read-only mount")):
                    with self.assertRaises((OSError, ValidationError)):
                        _root()

