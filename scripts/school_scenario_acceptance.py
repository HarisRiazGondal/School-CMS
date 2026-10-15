#!/usr/bin/env python3
"""Run the synthetic cross-module school lifecycle on a disposable SQLite DB.

This is Django HTTP/service-level acceptance, not a browser/UI test. The
temporary database and private-file directory are removed when the process
exits. It intentionally starts with a small controlled environment so local
SMTP, MFA, database, and production settings cannot leak into the run.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    # Preserve only process-launch essentials; app configuration below is all
    # explicit and synthetic. Inherited production credential/config variables
    # are intentionally omitted.
    env = {
        key: os.environ[key]
        for key in ("PATH", "PYTHONPATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "TMP", "TEMP", "TMPDIR")
        if key in os.environ
    }
    with tempfile.TemporaryDirectory(prefix="school-scenario-") as temporary:
        temp_root = Path(temporary)
        env.update({
            "DJANGO_SETTINGS_MODULE": "schoolcms.settings",
            "DJANGO_DEBUG": "true",
            "DJANGO_SECRET_KEY": "synthetic-scenario-only-secret-key-not-for-deployment",
            "DATABASE_URL": f"sqlite:///{temp_root / 'scenario.sqlite3'}",
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
            "DJANGO_DEFAULT_FROM_EMAIL": "Synthetic acceptance <no-reply@example.invalid>",
            "MFA_ENCRYPTION_KEY": "",
            "PRIVATE_FILE_SCANNER_COMMAND": "",
        })
        command = [
            sys.executable, str(ROOT / "manage.py"), "test",
            "tests.test_school_scenarios", "tests.test_school_http_journey", "--verbosity", "1",
        ]
        result = subprocess.run(
            command, cwd=ROOT, env=env, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        output = result.stdout or ""
        ran_match = re.search(r"^Ran\s+(\d+)\s+tests?\b", output, re.MULTILINE)
        summary_match = re.search(r"\b(?:FAILED|OK)\s*\(([^)]*)\)", output)
        summary = summary_match.group(1) if summary_match else ""
        count = lambda label: int(match.group(1)) if (match := re.search(rf"\b{label}=(\d+)\b", summary)) else 0
        tests_run = int(ran_match.group(1)) if ran_match else 0
        passed = result.returncode == 0 and tests_run == 2 and count("skipped") == 0
        report = {
            "acceptance_type": "django_request_and_service_level",
            "django_request_views_executed": tests_run == 2,
            "network_or_browser_transport_executed": False,
            "browser_or_ui_executed": False,
            "status": "passed" if passed else "failed",
            "tests_run": tests_run,
            "failures": count("failures"),
            "errors": count("errors"),
            "skipped": count("skipped"),
            "partial_matrix_coverage": True,
            "full_browser_scenarios_passed": 0,
            "matrix_areas_exercised": [
                "admission approval and rejection",
                "valid timetable slot and overlapping teacher booking",
                "attendance correction request and administrator approval",
                "student classwork submission and teacher grading",
                "objective/manual assessment scoring, administrator finalization and publication",
                "class 7 fee plan, concession, partial payment and reversal",
                "manual invoice issuance and duplicate/unauthorized operation denials",
                "promotion with retained student identity, enrollment and historical records",
                "class 8 fee plan and explicit invoice issuance",
                "cross-school access denials",
            ],
            "validated_assertions": [
                "PKR 10,000 class 7 fee less PKR 1,000 concession gives PKR 9,000 due.",
                "PKR 3,000 partial payment reduces the balance to PKR 6,000; reversal restores PKR 9,000 and preserves the receipt.",
                "A PKR 12,000 class 8 plan is issued against the promoted enrollment; prior year invoice remains available.",
                "The student UUID and permanent code remain unchanged across promotion, and the published assessment remains in the historical transcript.",
                "A fee plan alone creates no invoice; an accountant explicitly issues each invoice.",
                "The request-level journey checks actual login/CSRF/forms/views for five roles; a PKR 10,000 invoice minus PKR 3,000 payment leaves PKR 7,000, with a separate PKR 12,000 next-class invoice.",
            ] if passed else [],
            "manual_fee_workflow": "Automatic invoice generation is not implemented; explicit staff issuance is the exercised workflow.",
            "unexpected_errors": [] if passed else [output[-12000:] or "Runner exited before producing test output."],
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if passed else (result.returncode or 1)


if __name__ == "__main__":
    raise SystemExit(main())
