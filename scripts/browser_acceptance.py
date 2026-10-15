#!/usr/bin/env python3
"""Disposable-database Playwright acceptance smoke for five synthetic roles.

This script owns a temporary SQLite database and an ephemeral loopback Django
server. It refuses non-loopback targets and never prints credentials, page
contents, storage state, traces, or screenshots.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_PASSWORD = "Browser-Smoke-Only-47!"
ROLE_USERS = {
    "school administrator": "e2e-admin",
    "registrar": "e2e-registrar",
    "teacher": "e2e-teacher",
    "student": "e2e-student",
    "accountant": "e2e-accountant",
}


def _loopback(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port is not None
    except ValueError:
        return False


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _safe_browser_message(message: str) -> str:
    # Runtime diagnostics remain useful while making accidental synthetic
    # credential echoes impossible to print.
    for secret in (SYNTHETIC_PASSWORD, *ROLE_USERS.values()):
        message = message.replace(secret, "[redacted]")
    return message[:300]


def _route(name: str, **kwargs) -> str:
    from django.urls import reverse
    return reverse(name, **kwargs)


def _is_expected_403_resource_error(message_type: str, text: str, location_url: str, allowed_paths: set[str]) -> bool:
    if message_type != "error" or "Failed to load resource:" not in text or "403" not in text:
        return False
    try:
        resource_path = urlsplit(location_url).path
    except ValueError:
        return False
    return resource_path in allowed_paths


def _bootstrap_django(temp_root: Path):
    os.environ.update({
        "DJANGO_SETTINGS_MODULE": "schoolcms.settings",
        "DJANGO_DEBUG": "true",
        "DJANGO_SECRET_KEY": "browser-smoke-only-secret-key-not-for-deployment",
        "DATABASE_URL": f"sqlite:///{temp_root / 'browser-acceptance.sqlite3'}",
        "PRIVATE_FILE_ROOT": str(temp_root / "private-files"),
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "",
        "DJANGO_TRUST_PROXY": "false",
        "DJANGO_EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
        "DJANGO_EMAIL_HOST": "localhost",
        "DJANGO_EMAIL_HOST_USER": "",
        "DJANGO_EMAIL_HOST_PASSWORD": "",
        "DJANGO_EMAIL_USE_TLS": "false",
        "DJANGO_EMAIL_USE_SSL": "false",
        "DJANGO_DEFAULT_FROM_EMAIL": "School-CMS browser smoke <no-reply@example.invalid>",
        "MFA_ENCRYPTION_KEY": "",
        "PRIVATE_FILE_SCANNER_COMMAND": "",
    })
    for file_setting in (
        "DJANGO_SECRET_KEY_FILE", "DATABASE_URL_FILE", "MFA_ENCRYPTION_KEY_FILE",
        "DJANGO_EMAIL_HOST_PASSWORD_FILE",
    ):
        os.environ.pop(file_setting, None)
    sys.path.insert(0, str(ROOT))
    import django
    django.setup()
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)
    _seed_synthetic_school()


def _seed_synthetic_school():
    from datetime import date
    from accounts.models import SchoolMembership, User
    from academics.models import SchoolClass, Section, Subject
    from learning.models import TeacherAssignment
    from learning.services import create_assignment
    from schools.models import AcademicYear, School
    from students.services import register_student

    school = School.objects.create(name="Browser Smoke School", slug="browser-smoke")
    School.objects.create(name="Unassigned Smoke School", slug="unassigned-smoke")
    year = AcademicYear.objects.create(
        school=school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31),
    )
    grade = SchoolClass.objects.create(school=school, name="Class 4")
    section = Section.objects.create(school_class=grade, academic_year=year, name="A")
    subject = Subject.objects.create(school=school, name="Science", code="SCI")

    users = {}
    for role, username in ROLE_USERS.items():
        user = User.objects.create_user(
            username=username, email=f"{username}@example.invalid", password=SYNTHETIC_PASSWORD,
        )
        users[role] = user
    role_values = {
        "school administrator": SchoolMembership.Role.SCHOOL_ADMIN,
        "registrar": SchoolMembership.Role.REGISTRAR,
        "teacher": SchoolMembership.Role.TEACHER,
        "student": SchoolMembership.Role.STUDENT,
        "accountant": SchoolMembership.Role.ACCOUNTANT,
    }
    for role, user in users.items():
        SchoolMembership.objects.create(user=user, school=school, role=role_values[role])

    TeacherAssignment.objects.create(user=users["teacher"], section=section, subject=subject)
    _, enrollment = register_student(
        user=users["registrar"], school=school, first_name="Amina", last_name="Example",
        academic_year=year, section=section, roll_number="4A-01", student_user=users["student"],
    )
    create_assignment(
        users["teacher"], section, subject,
        title="Synthetic science practice", instructions="Describe a plant lifecycle.", publish=True,
    )
    return {"school": school, "year": year, "section": section, "enrollment": enrollment}


def _wait_for_server(base_url: str, process: subprocess.Popen, timeout: float = 25.0) -> None:
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The isolated Django acceptance server exited before becoming ready.")
        try:
            with urllib.request.urlopen(base_url + "/health/live/", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("The isolated Django acceptance server did not become ready.")


def _axe_check(page, axe_url: str, violations: list[str]) -> None:
    page.add_script_tag(url=axe_url)
    results = page.evaluate("async () => await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } })")
    for item in results["violations"]:
        violations.append(f"{item['id']} ({item['impact']}): {item['help']}")


def _assert_keyboard_shell(page) -> None:
    page.goto(page.url)
    page.keyboard.press("Tab")
    skip = page.get_by_role("link", name="Skip to main content")
    assert skip.evaluate("el => document.activeElement === el"), "The first keyboard stop should be the skip link."
    assert skip.is_visible(), "The focused skip link should be visible."
    outline = skip.evaluate("el => getComputedStyle(el).outlineStyle")
    assert outline != "none", "Keyboard focus must have a visible outline."
    page.keyboard.press("Enter")
    assert page.locator("main#main-content").evaluate("el => document.activeElement === el"), "Skip link must move focus to main content."
    assert page.get_by_role("navigation", name="Account").count() == 1


def _assert_named_controls(page) -> None:
    unnamed = page.locator("input:not([type=hidden]), select, textarea, button").evaluate_all(
        "elements => elements.filter(el => {"
        "const aria = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby');"
        "const label = el.labels && el.labels.length > 0;"
        "const text = (el.innerText || '').trim();"
        "return !(aria || label || text || (el.type === 'submit' && el.value));"
        "}).map(el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''))"
    )
    assert not unnamed, "Unlabeled interactive controls: " + ", ".join(unnamed)


def _login(page, base_url: str, username: str, expected_denial_paths: set[str]) -> None:
    login_path = _route("login")
    page.goto(base_url + login_path)
    assert page.locator('input[name="csrfmiddlewaretoken"]').count() == 1
    _assert_named_controls(page)
    expected_denial_paths.add(login_path)
    rejected = page.request.post(
        base_url + login_path,
        form={"username": username, "password": SYNTHETIC_PASSWORD},
        fail_on_status_code=False,
    )
    # BrowserContext.request shares cookies, but the rejected unsafe POST must
    # leave the user anonymous. Do not rely on this request's content in logs.
    assert rejected.status == 403, "Login POST without CSRF token should be rejected."
    assert page.get_by_role("heading", name="Sign in").count() == 1
    page.locator('input[name="username"]').fill(username)
    page.locator('input[name="password"]').fill(SYNTHETIC_PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(base_url + _route("home"))
    assert page.get_by_text(username, exact=True).count() == 1


def run(base_url: str, skip_axe: bool = False) -> int:
    if not _loopback(base_url):
        raise ValueError("Refusing non-loopback browser target. Use an isolated http://127.0.0.1:<port> test server.")

    from playwright.sync_api import sync_playwright
    axe_path = ROOT / "tests/e2e/node_modules/axe-core/axe.min.js"
    if not skip_axe and not axe_path.is_file():
        raise RuntimeError("Pinned axe-core is missing. Run npm ci --prefix tests/e2e or pass --skip-axe.")

    console_errors: list[str] = []
    page_errors: list[str] = []
    axe_violations: list[str] = []
    completed_roles: list[str] = []
    ignored_expected_403_console_errors = 0
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            if "Executable doesn't exist" in str(exc):
                raise RuntimeError("Chromium is not installed; run python -m playwright install chromium.") from None
            raise
        try:
            axe_bytes = axe_path.read_bytes() if not skip_axe else b""
            for role, username in ROLE_USERS.items():
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                axe_url = base_url + "/__e2e_axe__.js"
                if not skip_axe:
                    # Fulfill the pinned local bytes through a same-origin URL.
                    # This preserves the application's strict script-src 'self'
                    # policy and does not disable or bypass CSP.
                    page.route(
                        axe_url,
                        lambda route, body=axe_bytes: route.fulfill(
                            status=200, content_type="application/javascript", body=body,
                            headers={"Cache-Control": "no-store"},
                        ),
                    )
                expected_denial_paths = {
                    _route("login"), _route("logout"),
                    _route("finance:school-home", kwargs={"school_slug": "unassigned-smoke"}),
                }

                def record_console(msg, allowed_paths=expected_denial_paths):
                    nonlocal ignored_expected_403_console_errors
                    if msg.type != "error":
                        return
                    location = msg.location or {}
                    expected_403 = _is_expected_403_resource_error(
                        msg.type, msg.text, location.get("url", ""), allowed_paths,
                    )
                    if expected_403:
                        ignored_expected_403_console_errors += 1
                    else:
                        console_errors.append(_safe_browser_message(f"console.{msg.type}: {msg.text}"))

                page.on("console", record_console)
                page.on("pageerror", lambda error: page_errors.append(_safe_browser_message(str(error))))
                try:
                    _login(page, base_url, username, expected_denial_paths)
                    page.goto(base_url + _route("home"))
                    _assert_keyboard_shell(page)

                    if role == "school administrator":
                        journey_path = _route("oversight:dashboard", kwargs={"school_slug": "browser-smoke"})
                    elif role == "registrar":
                        journey_path = _route("students:admissions", kwargs={"school_slug": "browser-smoke"})
                    elif role == "teacher":
                        journey_path = _route("learning:home")
                    elif role == "student":
                        journey_path = _route("learning:home")
                    else:
                        journey_path = _route("finance:school-home", kwargs={"school_slug": "browser-smoke"})

                    page.goto(base_url + journey_path)
                    assert page.locator("main#main-content").count() == 1, f"Missing main landmark for {role}."
                    assert page.get_by_role("heading", level=1).count() >= 1, f"Missing page heading for {role}."
                    assert page.get_by_role("navigation", name="Account").count() == 1
                    _assert_named_controls(page)
                    if not skip_axe:
                        _axe_check(page, axe_url, axe_violations)
                    forbidden_path = _route("finance:school-home", kwargs={"school_slug": "unassigned-smoke"})
                    expected_denial_paths.add(forbidden_path)
                    status = page.request.get(base_url + forbidden_path).status
                    assert status == 403, f"Expected school-scope 403 for {role}, got {status}."

                    # Django's logout view must reject an unsafe POST without a
                    # form token; the visible shell form submits the valid token.
                    rejected = page.request.post(base_url + _route("logout"), fail_on_status_code=False)
                    assert rejected.status == 403, f"Logout without CSRF token should be rejected for {role}."
                    page.goto(base_url + journey_path)
                    page.get_by_role("button", name="Sign out").click()
                    page.wait_for_url(base_url + _route("logged_out"))
                    assert page.get_by_role("heading", name="You’re signed out").count() == 1
                    completed_roles.append(role)
                finally:
                    context.close()
        finally:
            browser.close()

    failures = []
    if console_errors:
        failures.append("Browser console errors: " + "; ".join(console_errors[:8]))
    if page_errors:
        failures.append("Browser page errors: " + "; ".join(page_errors[:8]))
    if axe_violations:
        failures.append("axe-core violations: " + "; ".join(axe_violations[:12]))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: isolated Chromium smoke covered CSRF login/logout, all five synthetic roles, school-scope 403s, keyboard skip-focus, labels/navigation landmarks, and runtime browser errors.")
    if ignored_expected_403_console_errors:
        print(f"Ignored {ignored_expected_403_console_errors} Chromium resource messages for the exact expected CSRF/scope 403 routes.")
    if not skip_axe:
        print("PASS: axe-core WCAG 2.1 A/AA automated checks on all five role journeys (automated scan only; hosted human acceptance remains separate).")
    print("Roles completed: " + ", ".join(completed_roles))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-axe", action="store_true", help="Skip axe-core checks while retaining browser/keyboard smoke checks.")
    args = parser.parse_args()

    try:
        with tempfile.TemporaryDirectory(prefix="schoolcms-e2e-") as temporary:
            temp_root = Path(temporary)
            _bootstrap_django(temp_root)
            port = _port()
            base_url = f"http://127.0.0.1:{port}"
            if not _loopback(base_url):
                raise ValueError("Refusing non-loopback browser target.")
            server_env = os.environ.copy()
            server = subprocess.Popen(
                [sys.executable, str(ROOT / "manage.py"), "runserver", f"127.0.0.1:{port}", "--noreload"],
                cwd=ROOT, env=server_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                _wait_for_server(base_url, server)
                return run(base_url, skip_axe=args.skip_axe)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
    except Exception as exc:
        # Exception messages can include paths and query strings. Keep the
        # emitted diagnostic to exception class and its safe, generic message.
        if isinstance(exc, AssertionError):
            print(f"FAIL: {exc}", file=sys.stderr)
        elif isinstance(exc, RuntimeError) and str(exc).startswith("Chromium is not installed"):
            print(f"FAIL: {exc}", file=sys.stderr)
        else:
            print(f"FAIL: browser acceptance could not complete ({type(exc).__name__}).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
