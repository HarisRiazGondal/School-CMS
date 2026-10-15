"""Read-only, evidence-oriented production preflight.

Network probes and antivirus test files are opt-in. This command never sends
mail unless an operator supplies --send-test-email explicitly.
"""
import datetime as dt
import http.client
import ipaddress
import json
import os
import re
import shlex
import shutil
import socket
import ssl
import stat
# subprocess is limited below to fixed Git argv and the operator-configured scanner, always without a shell.
import subprocess  # nosec B404
import tempfile
import urllib.parse
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def _check(checks, key, status, message):
    checks.append({"id": key, "status": status, "message": message})


def _public_https_url(value):
    """Validate the explicit target and reject DNS results that could SSRF."""
    parsed = urllib.parse.urlsplit(value or "")
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in {"/health/live/", "/health/ready/"}):
        raise ValueError("Provide an HTTPS health URL with no credentials/query and a health endpoint path.")
    host = parsed.hostname.rstrip(".").lower()
    if host not in {entry.lower().lstrip(".") for entry in settings.ALLOWED_HOSTS if entry != "*"}:
        raise ValueError("Target host is not an exact configured ALLOWED_HOSTS entry.")
    addresses = {answer[4][0] for answer in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Target DNS must resolve exclusively to public IP addresses.")
    return parsed, sorted(addresses)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS with verified TLS/SNI while connecting only to an approved IP."""
    def __init__(self, host, address, port, timeout):
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._approved_address = address

    def connect(self):
        sock = socket.create_connection((self._approved_address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class Command(BaseCommand):
    help = "Collect production release checks as structured JSON without exposing secrets."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="json_output", help="Emit machine-readable JSON.")
        parser.add_argument("--network-checks", action="store_true", help="Opt in to SMTP TLS and/or the explicit --health-url probe.")
        parser.add_argument("--health-url", help="Explicit public HTTPS /health/live/ or /health/ready/ target (only with --network-checks).")
        parser.add_argument("--probe-scanner", action="store_true", help="Opt in to clean and EICAR test-file scanner probes with cleanup.")
        parser.add_argument("--send-test-email", metavar="RECIPIENT", help="Explicitly send one test message to this controlled mailbox; requires --network-checks.")

    def handle(self, *args, **opts):
        checks = []
        commit = self._commit(checks)
        self._settings_checks(checks)
        self._database_checks(checks)
        root_ok = self._private_root_checks(checks)
        self._scanner_checks(checks, opts["probe_scanner"], root_ok)

        if opts["health_url"] and not opts["network_checks"]:
            _check(checks, "https_health", "blocked", "--health-url requires explicit --network-checks opt-in.")
        elif opts["health_url"]:
            self._https_check(checks, opts["health_url"])
        else:
            _check(checks, "https_health", "blocked", "No explicit public health target supplied; network probing was skipped.")

        if opts["send_test_email"] and not opts["network_checks"]:
            _check(checks, "smtp_test_email", "blocked", "Sending requires explicit --network-checks opt-in.")
        else:
            self._smtp_check(checks, bool(opts["network_checks"]), opts["send_test_email"])

        status = "failed" if any(item["status"] == "failed" for item in checks) else (
            "blocked" if any(item["status"] == "blocked" for item in checks) else "passed")
        result = {
            "schema_version": 1,
            "status": status,
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "commit": commit,
            "environment": {"python": os.sys.version.split()[0], "django": self._django_version(),
                            "platform": os.name, "debug": bool(settings.DEBUG)},
            "checks": checks,
        }
        output = json.dumps(result, sort_keys=True) if opts["json_output"] else json.dumps(result, indent=2, sort_keys=True)
        self.stdout.write(output)
        if status != "passed":
            # Keep JSON on stdout for CI while providing a useful process exit code.
            raise SystemExit(1)

    @staticmethod
    def _django_version():
        import django
        return django.get_version()

    @staticmethod
    def _commit(checks):
        try:
            git = shutil.which("git")
            if not git:
                raise OSError("git executable unavailable")
            # The executable is resolved from PATH; both Git subcommands and all arguments are fixed by code.
            result = subprocess.run(  # nosec B603
                                    [git, "rev-parse", "HEAD"], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                    timeout=5, check=True)
            commit = result.stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
                raise ValueError
            # This second Git call also has a fixed code-owned argv and no shell.
            dirty = subprocess.run(  # nosec B603
                                   [git, "status", "--porcelain"], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                   timeout=5, check=True).stdout.strip()
            _check(checks, "source_commit", "blocked" if dirty else "passed",
                   "Exact Git commit recorded; worktree is clean." if not dirty else "HEAD recorded, but uncommitted changes mean it does not identify all executed source.")
            return commit
        except (OSError, subprocess.SubprocessError, ValueError):
            _check(checks, "source_commit", "blocked", "Exact Git commit could not be established.")
            return None

    @staticmethod
    def _settings_checks(checks):
        prod = not settings.DEBUG
        required = [
            (prod, "debug", "Production DEBUG is disabled."),
            (settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql", "database_engine", "Configured database engine is PostgreSQL."),
            (bool(settings.ALLOWED_HOSTS) and "*" not in settings.ALLOWED_HOSTS, "allowed_hosts", "Explicit non-wildcard host allowlist is configured."),
            (bool(settings.CSRF_TRUSTED_ORIGINS) and all(v.startswith("https://") and "*" not in v for v in settings.CSRF_TRUSTED_ORIGINS), "csrf_origins", "Explicit HTTPS CSRF origins are configured."),
            (bool(getattr(settings, "SECURE_SSL_REDIRECT", False) and getattr(settings, "SESSION_COOKIE_SECURE", False) and getattr(settings, "CSRF_COOKIE_SECURE", False) and getattr(settings, "SECURE_CONTENT_TYPE_NOSNIFF", False)), "https_security", "HTTPS redirect, secure cookies, and content-type protection are enabled."),
            (bool(getattr(settings, "SECURE_HSTS_SECONDS", 0) >= 3600), "hsts", "HSTS is configured for at least one hour."),
            (bool(settings.MFA_REQUIRED_FOR_STAFF and settings.MFA_REQUIRED_FOR_PRIVILEGED_ROLES), "mfa_policy", "Production MFA policies are enabled."),
            (settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and bool(settings.EMAIL_HOST) and settings.EMAIL_HOST not in {"localhost", "127.0.0.1"}, "smtp_configuration", "An explicit SMTP backend and non-local host are configured."),
            (bool(settings.EMAIL_USE_TLS) != bool(settings.EMAIL_USE_SSL), "smtp_transport", "Exactly one SMTP TLS or SSL mode is configured."),
        ]
        for ok, key, message in required:
            _check(checks, "settings_" + key, "passed" if ok else "failed", message if ok else "Required production setting is missing or unsafe.")
        secret = getattr(settings, "SECRET_KEY", "")
        _check(checks, "settings_secret_key", "passed" if prod and len(secret) >= 50 else "failed",
               "Production secret key has an acceptable configured length." if prod and len(secret) >= 50 else "Production secret key policy is not satisfied.")

    @staticmethod
    def _database_checks(checks):
        if connection.vendor != "postgresql":
            _check(checks, "database_connection", "blocked", "A real PostgreSQL connection is required; configured backend is not PostgreSQL.")
            _check(checks, "database_version", "blocked", "PostgreSQL server version is unavailable.")
            _check(checks, "migration_state", "blocked", "Migration state requires a real PostgreSQL connection.")
            return
        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
            _check(checks, "database_connection", "passed", "Live PostgreSQL connection succeeded.")
            safe_version = str(version).splitlines()[0][:100]
            _check(checks, "database_version", "passed", "Connected server: " + safe_version)
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
            _check(checks, "migration_state", "failed" if pending else "passed",
                   "Unapplied migrations are present." if pending else "No unapplied migrations on the live database.")
        except Exception:
            _check(checks, "database_connection", "failed", "PostgreSQL connection or metadata query failed; details withheld.")
            _check(checks, "database_version", "blocked", "PostgreSQL server version could not be verified.")
            _check(checks, "migration_state", "blocked", "Migration state could not be verified.")

    @staticmethod
    def _private_root_checks(checks):
        root = Path(settings.PRIVATE_FILE_ROOT)
        try:
            info = root.lstat()
            secure = (stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                      and info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0)
            _check(checks, "private_root_permissions", "passed" if secure else "failed",
                   "Private root exists as a service-owned directory with no group/world access." if secure else "Private root is missing, linked, incorrectly owned, or too broadly accessible.")
            configured = os.environ.get("PRIVATE_FILE_ROOT", "")
            outside_app = not root.resolve(strict=True).is_relative_to(Path(settings.BASE_DIR).resolve())
            path_ok = bool(configured and Path(configured).is_absolute() and root.resolve(strict=True) == Path(configured) and outside_app)
            _check(checks, "private_root_configuration", "passed" if path_ok else "failed",
                   "Private root is explicitly configured outside the application." if path_ok else "Private root configuration is not explicit, stable, or outside the application.")
            # Directory metadata cannot prove that an operator mounted persistent storage.
            _check(checks, "private_root_persistence", "blocked", "Persistence across container replacement requires deployment-volume evidence outside this process.")
            return secure and path_ok
        except (OSError, RuntimeError, ValueError):
            for key, message in (("private_root_permissions", "Private root metadata could not be verified."),
                                 ("private_root_configuration", "Private root configuration could not be verified."),
                                 ("private_root_persistence", "Persistent-volume evidence is unavailable.")):
                _check(checks, key, "failed" if key != "private_root_persistence" else "blocked", message)
            return False

    def _scanner_checks(self, checks, probe, root_ok):
        configured = getattr(settings, "PRIVATE_FILE_SCANNER_COMMAND", "")
        try:
            parts = shlex.split(configured) if isinstance(configured, str) else list(configured)
            executable = shutil.which(parts[0]) if parts else None
        except (ValueError, TypeError, IndexError):
            parts, executable = [], None
        available = bool(executable and any("{path}" in part for part in parts))
        _check(checks, "scanner_available", "passed" if available else "failed",
               "Configured scanner executable and {path} argument are available." if available else "Configured scanner command is missing, malformed, or executable is unavailable.")
        if not available:
            _check(checks, "scanner_signatures", "blocked", "Scanner signature readiness cannot be checked without the configured scanner.")
            _check(checks, "scanner_probe", "blocked", "Clean/EICAR probe cannot run without the configured scanner.")
            return
        name = Path(executable).name.lower()
        if name not in {"clamscan", "clamscan.exe"}:
            _check(checks, "scanner_signatures", "blocked", "Signature readiness is unsupported for this scanner executable; no PASS inferred.")
        else:
            try:
                # The scanner path is resolved with shutil.which; the only supplied argument is --version.
                result = subprocess.run(  # nosec B603
                    [executable, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, timeout=10, check=False, text=True)
                ready = result.returncode == 0 and bool(re.search(r"ClamAV\s+\S+/\d+", result.stdout))
                _check(checks, "scanner_signatures", "passed" if ready else "failed",
                       "ClamAV version reports a loaded signature database." if ready else "ClamAV signature database readiness was not reported.")
            except (OSError, subprocess.SubprocessError):
                _check(checks, "scanner_signatures", "failed", "ClamAV signature readiness probe failed; details withheld.")
        if not probe:
            _check(checks, "scanner_probe", "blocked", "Clean/EICAR scanner behavior not tested; use --probe-scanner to opt in.")
            return
        if not root_ok:
            _check(checks, "scanner_probe", "blocked", "Scanner probe requires a verified private root for temporary files.")
            return
        try:
            with tempfile.TemporaryDirectory(prefix=".release-probe-", dir=settings.PRIVATE_FILE_ROOT) as temporary:
                os.chmod(temporary, 0o700)
                clean = Path(temporary) / "clean.txt"
                infected = Path(temporary) / "eicar.txt"
                clean.write_bytes(b"School-CMS release preflight clean file.\n")
                infected.write_bytes(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*\n")
                os.chmod(clean, 0o600)
                os.chmod(infected, 0o600)
                clean_result = self._run_scanner(parts, clean)
                infected_result = self._run_scanner(parts, infected)
            ok = clean_result == 0 and infected_result == 1
            _check(checks, "scanner_probe", "passed" if ok else "failed",
                   "Scanner accepted clean test content and detected EICAR; temporary files removed." if ok else "Scanner did not produce the expected clean/infected results; temporary files removed.")
        except (OSError, subprocess.SubprocessError):
            _check(checks, "scanner_probe", "failed", "Scanner probe failed; temporary files are cleaned when possible and details withheld.")

    @staticmethod
    def _run_scanner(parts, path):
        argv = [str(part).replace("{path}", str(path)) for part in parts]
        # Scanner argv is deployment-controlled configuration plus an app-created path; shell remains disabled.
        return subprocess.run(  # nosec B603
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=settings.PRIVATE_FILE_SCAN_TIMEOUT,
            check=False).returncode

    @staticmethod
    def _smtp_check(checks, network, recipient):
        if not network:
            _check(checks, "smtp_tls_connection", "blocked", "SMTP connection skipped; use --network-checks to opt in.")
            _check(checks, "smtp_test_email", "blocked", "No message sent; use --send-test-email only for an operator-controlled mailbox.")
            return
        if (settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend"
                or not settings.EMAIL_HOST or settings.EMAIL_HOST in {"localhost", "127.0.0.1"}
                or bool(settings.EMAIL_USE_TLS) == bool(settings.EMAIL_USE_SSL)):
            _check(checks, "smtp_tls_connection", "blocked", "SMTP TLS probe requires a valid explicit SMTP backend/host and exactly one encrypted transport mode.")
            _check(checks, "smtp_test_email", "blocked", "SMTP transport was not attempted; no message sent.")
            return
        from django.core.mail import get_connection, EmailMessage
        backend = None
        try:
            backend = get_connection(fail_silently=False)
            backend.open()
            _check(checks, "smtp_tls_connection", "passed", "Configured SMTP connection and transport negotiation succeeded.")
        except Exception:
            _check(checks, "smtp_tls_connection", "failed", "SMTP connection or transport negotiation failed; server details withheld.")
            if recipient:
                _check(checks, "smtp_test_email", "failed", "Controlled test message could not be sent; server details withheld.")
        else:
            if recipient:
                try:
                    message = EmailMessage("School-CMS release preflight", "Controlled operator-requested delivery test.",
                                           settings.DEFAULT_FROM_EMAIL, [recipient], connection=backend)
                    sent = message.send(fail_silently=False)
                    _check(checks, "smtp_test_email", "passed" if sent == 1 else "failed",
                           "One test message accepted by SMTP." if sent == 1 else "SMTP did not accept the test message.")
                except Exception:
                    _check(checks, "smtp_test_email", "failed", "Controlled test message failed; server details withheld.")
        finally:
            if backend is not None:
                try:
                    backend.close()
                except Exception:
                    _check(checks, "smtp_connection_cleanup", "failed", "SMTP connection cleanup failed; details withheld.")
        if not recipient:
            _check(checks, "smtp_test_email", "blocked", "No message sent; supply --send-test-email only for an operator-controlled mailbox.")

    @staticmethod
    def _https_check(checks, url):
        try:
            parsed, addresses = _public_https_url(url)
            connection_obj = _PinnedHTTPSConnection(parsed.hostname, addresses[0], parsed.port or 443, timeout=8)
            try:
                connection_obj.request("GET", parsed.path, headers={"User-Agent": "School-CMS-release-preflight/1"})
                response = connection_obj.getresponse()
                payload = response.read(8193)
                body = json.loads(payload)
                healthy = response.status == 200 and len(payload) <= 8192 and isinstance(body, dict) and body.get("status") == "ok"
                headers = response.headers
                required = {
                    "strict-transport-security": bool(re.search(r"max-age=(?:[1-9]\d{3,}|[1-9]\d{4,})", headers.get("Strict-Transport-Security", ""), re.I)),
                    "x-content-type-options": headers.get("X-Content-Type-Options", "").lower() == "nosniff",
                    "x-frame-options": headers.get("X-Frame-Options", "").lower() in {"deny", "sameorigin"},
                    "referrer-policy": bool(headers.get("Referrer-Policy")),
                    "content-security-policy": bool(re.search(r"frame-ancestors\s+'none'", headers.get("Content-Security-Policy", ""), re.I)),
                }
                missing = [header for header, valid in required.items() if not valid]
                passed = healthy and not missing
                message = "HTTPS health response and security headers verified." if passed else "Health response was not ready or required security headers were missing or unsafe: " + ", ".join(missing)
                _check(checks, "https_health", "passed" if passed else "failed", message)
            finally:
                connection_obj.close()
        except (ValueError, OSError, TimeoutError, json.JSONDecodeError, http.client.HTTPException):
            _check(checks, "https_health", "failed", "Explicit HTTPS target validation/request failed; details withheld.")
