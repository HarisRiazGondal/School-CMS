import json
import os
import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings

from schools.management.commands.verify_release import Command


class ReleasePreflightUnitTests(SimpleTestCase):
    def test_strict_settings_fail_closed_without_echoing_configured_secrets(self):
        checks = []
        with override_settings(DEBUG=True, SECRET_KEY="private-secret-value", ALLOWED_HOSTS=["*"],
                               CSRF_TRUSTED_ORIGINS=[], MFA_REQUIRED_FOR_STAFF=False,
                               MFA_REQUIRED_FOR_PRIVILEGED_ROLES=False):
            Command._settings_checks(checks)
        self.assertTrue(any(row["status"] == "failed" for row in checks))
        self.assertNotIn("private-secret-value", json.dumps(checks))

    def test_non_postgresql_runtime_is_blocked_instead_of_reported_as_pass(self):
        checks = []
        with patch("schools.management.commands.verify_release.connection.vendor", "sqlite"):
            Command._database_checks(checks)
        self.assertEqual({row["status"] for row in checks}, {"blocked"})
        self.assertEqual({row["id"] for row in checks}, {"database_connection", "database_version", "migration_state"})

    def test_private_root_checks_permissions_but_does_not_claim_persistence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "private"
            root.mkdir(mode=0o700)
            root.chmod(0o700)
            checks = []
            with override_settings(PRIVATE_FILE_ROOT=root, BASE_DIR=Path(temporary) / "app"), patch.dict(os.environ, {"PRIVATE_FILE_ROOT": str(root)}):
                root_ok = Command()._private_root_checks(checks)
            statuses = {row["id"]: row["status"] for row in checks}
            self.assertTrue(root_ok)
            self.assertEqual(statuses["private_root_permissions"], "passed")
            self.assertEqual(statuses["private_root_configuration"], "passed")
            self.assertEqual(statuses["private_root_persistence"], "blocked")

    def test_insecure_private_root_is_a_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "private"
            root.mkdir(mode=0o755)
            root.chmod(0o755)
            checks = []
            with override_settings(PRIVATE_FILE_ROOT=root, BASE_DIR=Path(temporary) / "app"), patch.dict(os.environ, {"PRIVATE_FILE_ROOT": str(root)}):
                root_ok = Command()._private_root_checks(checks)
            self.assertFalse(root_ok)
            self.assertEqual(next(row["status"] for row in checks if row["id"] == "private_root_permissions"), "failed")

    @override_settings(PRIVATE_FILE_SCANNER_COMMAND="", PRIVATE_FILE_ROOT="/nonexistent")
    def test_missing_scanner_is_failed_and_signature_probe_is_blocked(self):
        checks = []
        Command()._scanner_checks(checks, probe=True, root_ok=False)
        statuses = {row["id"]: row["status"] for row in checks}
        self.assertEqual(statuses["scanner_available"], "failed")
        self.assertEqual(statuses["scanner_signatures"], "blocked")
        self.assertEqual(statuses["scanner_probe"], "blocked")

    @override_settings(PRIVATE_FILE_SCANNER_COMMAND="/usr/bin/true {path}")
    def test_unsupported_scanner_cannot_claim_signature_readiness_or_probe(self):
        checks = []
        Command()._scanner_checks(checks, probe=False, root_ok=False)
        statuses = {row["id"]: row["status"] for row in checks}
        self.assertEqual(statuses["scanner_available"], "passed")
        self.assertEqual(statuses["scanner_signatures"], "blocked")
        self.assertEqual(statuses["scanner_probe"], "blocked")

    def test_opt_in_scanner_probe_checks_clean_and_eicar_and_cleans_temporary_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "private"
            root.mkdir(mode=0o700)
            root.chmod(0o700)
            outcomes = iter((0, 1))

            def scan(_parts, path):
                self.assertTrue(path.exists())
                return next(outcomes)

            checks = []
            with override_settings(PRIVATE_FILE_ROOT=root, PRIVATE_FILE_SCANNER_COMMAND="/usr/bin/true {path}"):
                with patch.object(Command, "_run_scanner", side_effect=scan):
                    Command()._scanner_checks(checks, probe=True, root_ok=True)
            probe = next(row for row in checks if row["id"] == "scanner_probe")
            self.assertEqual(probe["status"], "passed")
            self.assertEqual(list(root.iterdir()), [])

    def test_scanner_probe_runtime_failure_is_failed_without_command_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "private"
            root.mkdir(mode=0o700)
            checks = []
            with override_settings(PRIVATE_FILE_ROOT=root, PRIVATE_FILE_SCANNER_COMMAND="/usr/bin/true {path}"):
                with patch.object(Command, "_run_scanner", side_effect=OSError("contains secret")):
                    Command()._scanner_checks(checks, probe=True, root_ok=True)
            row = next(row for row in checks if row["id"] == "scanner_probe")
            self.assertEqual(row["status"], "failed")
            self.assertNotIn("secret", row["message"])
            self.assertEqual(list(root.iterdir()), [])

    def test_smtp_is_not_touched_without_network_opt_in(self):
        checks = []
        with patch("django.core.mail.get_connection") as get_connection:
            Command._smtp_check(checks, network=False, recipient=None)
        get_connection.assert_not_called()
        self.assertEqual(next(row["status"] for row in checks if row["id"] == "smtp_tls_connection"), "blocked")
        self.assertEqual(next(row["status"] for row in checks if row["id"] == "smtp_test_email"), "blocked")

    def test_send_mail_requires_network_opt_in(self):
        checks = []
        with patch("django.core.mail.get_connection") as get_connection:
            Command._smtp_check(checks, network=False, recipient="operator@example.test")
        get_connection.assert_not_called()
        self.assertEqual(next(row["status"] for row in checks if row["id"] == "smtp_test_email"), "blocked")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.example.test",
                       EMAIL_USE_TLS=True, EMAIL_USE_SSL=False)
    def test_opted_in_smtp_connection_failure_is_structured_and_redacted(self):
        checks = []
        backend = MagicMock()
        backend.open.side_effect = RuntimeError("smtp password must not appear")
        with patch("django.core.mail.get_connection", return_value=backend):
            Command._smtp_check(checks, network=True, recipient="operator@example.test")
        statuses = {row["id"]: row["status"] for row in checks}
        self.assertEqual(statuses["smtp_tls_connection"], "failed")
        self.assertEqual(statuses["smtp_test_email"], "failed")
        self.assertNotIn("password", json.dumps(checks))
        backend.close.assert_called_once()

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.example.test",
                       EMAIL_USE_TLS=True, EMAIL_USE_SSL=False)
    def test_smtp_close_failure_is_recorded_without_exception_details(self):
        checks = []
        backend = MagicMock()
        backend.close.side_effect = RuntimeError("smtp credential detail")
        with patch("django.core.mail.get_connection", return_value=backend):
            Command._smtp_check(checks, network=True, recipient=None)
        cleanup = next(row for row in checks if row["id"] == "smtp_connection_cleanup")
        self.assertEqual(cleanup["status"], "failed")
        self.assertNotIn("credential", cleanup["message"])

    @override_settings(ALLOWED_HOSTS=["cms.example.test"])
    def test_https_target_rejects_local_addresses_before_opening_network(self):
        checks = []
        with patch("schools.management.commands.verify_release.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]), \
             patch("schools.management.commands.verify_release._PinnedHTTPSConnection") as pinned:
            Command._https_check(checks, "https://cms.example.test/health/ready/")
        pinned.assert_not_called()
        self.assertEqual(checks[0]["status"], "failed")

    @override_settings(ALLOWED_HOSTS=["cms.example.test"])
    def test_https_probe_pins_request_to_the_validated_public_dns_address(self):
        checks = []
        headers = {
            "Strict-Transport-Security": "max-age=3600",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
        }
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"status":"ok"}'
        response.headers = headers
        connection_obj = MagicMock()
        connection_obj.getresponse.return_value = response
        dns = [(2, 1, 6, "", ("1.1.1.1", 443))]
        with patch("schools.management.commands.verify_release.socket.getaddrinfo", return_value=dns), \
             patch("schools.management.commands.verify_release._PinnedHTTPSConnection", return_value=connection_obj) as pinned:
            Command._https_check(checks, "https://cms.example.test/health/ready/")
        pinned.assert_called_once_with("cms.example.test", "1.1.1.1", 443, timeout=8)
        connection_obj.request.assert_called_once_with("GET", "/health/ready/", headers={"User-Agent": "School-CMS-release-preflight/1"})
        self.assertEqual(checks[0]["status"], "passed")

    def test_report_includes_commit_environment_timestamp_and_structured_checks(self):
        out = __import__("io").StringIO()
        command = Command(stdout=out)
        with patch.object(command, "_commit", return_value="a" * 40), \
             patch.object(command, "_settings_checks", side_effect=lambda checks: checks.append({"id": "settings", "status": "passed", "message": "ok"})), \
             patch.object(command, "_database_checks", side_effect=lambda checks: checks.extend([
                 {"id": "database", "status": "passed", "message": "ok"}])), \
             patch.object(command, "_private_root_checks", return_value=True), \
             patch.object(command, "_scanner_checks", side_effect=lambda checks, probe, root: checks.append({"id": "scanner", "status": "passed", "message": "ok"})), \
             patch.object(command, "_smtp_check", side_effect=lambda checks, network, recipient: checks.extend([
                 {"id": "smtp", "status": "passed", "message": "ok"}])), \
             patch.object(command, "_https_check", side_effect=lambda checks, url: checks.append({"id": "https_health", "status": "passed", "message": "ok"})):
            command.handle(json_output=True, network_checks=True, health_url="https://cms.example.test/health/live/",
                           probe_scanner=True, send_test_email=None)
        report = json.loads(out.getvalue())
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["commit"], "a" * 40)
        self.assertIn("python", report["environment"])
        self.assertTrue(report["checked_at"])
        self.assertEqual(report["checks"][0]["status"], "passed")


class ReleasePreflightDatabaseTests(TestCase):
    @skipUnless(connection.vendor == "postgresql", "requires the configured real PostgreSQL test database")
    def test_live_postgresql_version_and_migration_state_are_read_from_real_database(self):
        checks = []
        Command._database_checks(checks)
        statuses = {row["id"]: row["status"] for row in checks}
        self.assertEqual(statuses["database_connection"], "passed")
        self.assertEqual(statuses["database_version"], "passed")
        self.assertEqual(statuses["migration_state"], "passed")
        self.assertTrue(any("PostgreSQL" in row["message"] for row in checks if row["id"] == "database_version"))

    def test_database_probe_uses_the_test_database_connection(self):
        # Exercise an actual query against Django's configured test database.
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)
        checks = []
        Command._database_checks(checks)
        if connection.vendor == "postgresql":
            self.assertEqual(next(row["status"] for row in checks if row["id"] == "database_connection"), "passed")
        else:
            self.assertEqual(next(row["status"] for row in checks if row["id"] == "database_connection"), "blocked")
