#!/usr/bin/env python3
"""Exercise the real PostgreSQL + private-files bundle path on disposable PG."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

MARKER_BYTES = b"SCHOOL-CMS-QUIESCED-V1\n"


def run(argv: list[str], env: dict[str, str], *, capture: bool = False) -> str:
    result = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, check=False, text=True)
    if result.returncode:
        raise RuntimeError("A recovery rehearsal command failed")
    return result.stdout.strip() if capture else ""


def main() -> int:
    if os.environ.get("RECOVERY_REHEARSAL_DISPOSABLE") != "YES":
        print("Refusing rehearsal: explicitly set RECOVERY_REHEARSAL_DISPOSABLE=YES on an isolated disposable PostgreSQL server", file=sys.stderr)
        return 2
    for name in ("PGHOST", "PGPORT", "PGUSER", "BACKUP_ENCRYPTION_KEY_FILE"):
        if not os.environ.get(name):
            print(f"{name} is required", file=sys.stderr)
            return 2
    key = Path(os.environ["BACKUP_ENCRYPTION_KEY_FILE"])
    if not key.is_file():
        print("The recovery key file is unavailable", file=sys.stderr)
        return 2
    scripts = Path(__file__).resolve().parent
    env = os.environ.copy()
    env["PGDATABASE"] = env.get("PGDATABASE") or "postgres"
    env["PGPASS_DATABASE"] = "*"
    suffix = f"{os.getpid()}_{secrets.token_hex(4)}"
    source_db = f"schoolcms_rehearsal_{suffix}"
    target_db = f"schoolcms_restore_{suffix}"
    created: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="schoolcms-recovery-acceptance-") as temp:
            work = Path(temp)
            marker = work / "maintenance.marker"
            marker.write_bytes(MARKER_BYTES)
            source_files = work / "source-private"
            source_files.mkdir(mode=0o700)
            (source_files / "clean-payload.bin").write_bytes(b"private fixture v1\x00\xff")
            (source_files / "quarantine").mkdir(mode=0o700)
            (source_files / "quarantine" / "pending-scan.bin").write_bytes(b"quarantined fixture")
            restored_files = work / "restored-private"
            restored_files.mkdir(mode=0o700)

            run(["createdb", "--no-password", source_db], env)
            created.append(source_db)
            source_env = env | {"PGDATABASE": source_db}
            run(["psql", "--no-password", "--set", "ON_ERROR_STOP=1", "--command",
                 "CREATE TABLE recovery_probe (marker text PRIMARY KEY); INSERT INTO recovery_probe VALUES ('db-restored-v1');"], source_env)
            bundle_dir = work / "bundles"
            bundle_env = source_env | {"BACKUP_ENCRYPTION_KEY_FILE": str(key)}
            run([sys.executable, str(scripts / "backup-bundle.py"), "--private-root", str(source_files),
                 "--output-dir", str(bundle_dir), "--quiesced-marker", str(marker)], bundle_env)
            bundles = list(bundle_dir.glob("*.scb.enc"))
            if len(bundles) != 1:
                raise RuntimeError("Recovery rehearsal did not produce exactly one bundle")

            run(["createdb", "--no-password", target_db], env)
            created.append(target_db)
            target_env = env | {
                "PGDATABASE": target_db,
                "RESTORE_PRODUCTION_DATABASE_NAME": env.get("RESTORE_PRODUCTION_DATABASE_NAME") or "schoolcms_production",
                "BACKUP_ENCRYPTION_KEY_FILE": str(key),
                "RESTORE_TARGET_DISPOSABLE": "YES",
                "RESTORE_TARGET_ENVIRONMENT": "disposable",
                "DJANGO_ENVIRONMENT": "disposable",
            }
            run([sys.executable, str(scripts / "restore-bundle.py"), str(bundles[0]),
                 "--private-root", str(restored_files), "--private-root-disposable",
                 "--quiesced-marker", str(marker)], target_env)
            marker_value = run(["psql", "--no-password", "--tuples-only", "--no-align", "--command",
                                "SELECT marker FROM recovery_probe"], target_env, capture=True)
            if marker_value != "db-restored-v1":
                raise RuntimeError("Restored PostgreSQL marker did not match")
            if (restored_files / "clean-payload.bin").read_bytes() != b"private fixture v1\x00\xff":
                raise RuntimeError("Restored private file did not match")
            if (restored_files / "quarantine" / "pending-scan.bin").read_bytes() != b"quarantined fixture":
                raise RuntimeError("Restored quarantined file did not match")
        print("Real PostgreSQL and private-files recovery rehearsal passed")
        return 0
    except (OSError, RuntimeError) as exc:
        # Keep diagnostics generic; children may inherit credential-bearing env.
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        env["PGDATABASE"] = env.get("PGDATABASE") or "postgres"
        for database in reversed(created):
            subprocess.run(["dropdb", "--if-exists", "--no-password", database], env=env,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
