from __future__ import annotations

import importlib.machinery
import importlib.util
import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, module_name: str):
    loader = importlib.machinery.SourceFileLoader(module_name, str(ROOT / "scripts" / name))
    spec = importlib.util.spec_from_loader(module_name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


backup = load_script("backup-bundle.py", "backup_bundle_test")
restore = load_script("restore-bundle.py", "restore_bundle_test")


class RecoveryBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "private-source"
        self.source.mkdir()
        (self.source / "assignment.bin").write_bytes(b"opaque-private-data\x00")
        (self.source / "quarantine").mkdir()
        (self.source / "quarantine" / "pending.bin").write_bytes(b"pending scan")
        self.marker = self.base / "quiesced.marker"
        self.marker.write_bytes(backup.MARKER)
        self.key = self.base / "backup.key"
        self.key.write_bytes(b"synthetic-test-key\n")
        self.key.chmod(0o600)
        self.output = self.base / "backups"
        self.bundle = None

    def tearDown(self):
        self.temp.cleanup()

    def _fake_dump_command(self, argv, *, env=None):
        if argv and argv[0].endswith("backup-postgres.sh"):
            directory = Path(env["BACKUP_OUTPUT_DIR"])
            name = "schoolcms-20261015T010101Z-test.dump.enc"
            dump = directory / name
            dump.write_bytes(b"synthetic already-encrypted postgres dump")
            dump.with_name(name + ".sha256").write_text(hashlib.sha256(dump.read_bytes()).hexdigest() + "\n")
            dump.with_name(name + ".hmac").write_text("f" * 64 + "\n")
            return
        return self.real_run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, check=False, env=env)

    def make_bundle(self):
        self.real_run = subprocess.run
        with patch.object(backup, "_run_quiet", side_effect=self._fake_dump_command):
            bundle = backup.create_bundle(self.source, self.output, self.marker, self.key)
        self.bundle = bundle
        return bundle

    def _restore_with_mocked_db(self, bundle, root, *, fail_db=False):
        self.real_run = subprocess.run

        def fake_run(argv, **kwargs):
            if argv and argv[0].endswith("restore-postgres.sh"):
                return subprocess.CompletedProcess(argv, 1 if fail_db else 0)
            return self.real_run(argv, **kwargs)

        restore_env = {
            "PGDATABASE": "schoolcms_test_restore",
            "RESTORE_PRODUCTION_DATABASE_NAME": "schoolcms_production",
            "RESTORE_TARGET_DISPOSABLE": "YES",
            "RESTORE_TARGET_ENVIRONMENT": "disposable",
            "DJANGO_ENVIRONMENT": "disposable",
        }
        with patch.dict(os.environ, restore_env), patch.object(restore.subprocess, "run", side_effect=fake_run):
            restore.restore_bundle(bundle, root, self.marker, self.key, private_root_disposable=True)

    def test_filesystem_roundtrip_including_quarantine(self):
        bundle = self.make_bundle()
        root = self.base / "restore-root"
        root.mkdir()
        self._restore_with_mocked_db(bundle, root)
        self.assertEqual((root / "assignment.bin").read_bytes(), b"opaque-private-data\x00")
        self.assertEqual((root / "quarantine" / "pending.bin").read_bytes(), b"pending scan")
        self.assertEqual((root / "assignment.bin").stat().st_mode & 0o777, 0o600)

    def test_tampered_bundle_is_rejected_before_database_restore(self):
        bundle = self.make_bundle()
        with bundle.open("r+b") as stream:
            stream.seek(-1, 2)
            original = stream.read(1)
            stream.seek(-1, 2)
            stream.write(bytes([original[0] ^ 1]))
        root = self.base / "restore-root"
        root.mkdir()
        with self.assertRaisesRegex(restore.backup_bundle.BundleError, "authentication failed"):
            self._restore_with_mocked_db(bundle, root)
        self.assertEqual(list(root.iterdir()), [])

    def test_restore_refuses_nonempty_root_before_database_restore(self):
        bundle = self.make_bundle()
        root = self.base / "restore-root"
        root.mkdir()
        existing = root / "keep"
        existing.write_text("existing")
        with self.assertRaisesRegex(restore.backup_bundle.BundleError, "must be empty"):
            self._restore_with_mocked_db(bundle, root)
        self.assertEqual(existing.read_text(), "existing")

    def test_restore_requires_explicit_disposable_attestation_and_prod_identity(self):
        bundle = self.make_bundle()
        root = self.base / "restore-root"
        root.mkdir()
        with patch.dict(os.environ, {"PGDATABASE": "schoolcms_test_restore"}, clear=True):
            with self.assertRaisesRegex(restore.backup_bundle.BundleError, "attestations are required"):
                restore.restore_bundle(bundle, root, self.marker, self.key, private_root_disposable=True)
        with patch.dict(os.environ, {
            "PGDATABASE": "schoolcms_production",
            "RESTORE_PRODUCTION_DATABASE_NAME": "schoolcms_production",
            "RESTORE_TARGET_DISPOSABLE": "YES",
            "RESTORE_TARGET_ENVIRONMENT": "disposable",
            "DJANGO_ENVIRONMENT": "disposable",
        }):
            with self.assertRaisesRegex(restore.backup_bundle.BundleError, "matches the configured production"):
                restore.restore_bundle(bundle, root, self.marker, self.key, private_root_disposable=True)
        self.assertEqual(list(root.iterdir()), [])

    def test_failed_database_restore_cleans_staging_and_leaves_root_empty(self):
        bundle = self.make_bundle()
        root = self.base / "restore-root"
        root.mkdir()
        with self.assertRaisesRegex(restore.backup_bundle.BundleError, "PostgreSQL restore failed"):
            self._restore_with_mocked_db(bundle, root, fail_db=True)
        self.assertEqual(list(root.iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.base.iterdir()),
                         sorted(["private-source", "quiesced.marker", "backup.key", "backups", "restore-root"]))

    def test_backup_rejects_symlink_inside_private_tree(self):
        outside = self.base / "outside"
        outside.write_text("must not follow")
        (self.source / "unsafe-link").symlink_to(outside)
        with self.assertRaisesRegex(backup.BundleError, "unsafe filesystem entry"):
            backup.create_bundle(self.source, self.output, self.marker, self.key)

    def test_restore_rejects_archive_path_traversal(self):
        archive_path = self.base / "unsafe.tar"
        with tarfile.open(archive_path, "w") as archive:
            info = tarfile.TarInfo("../escape")
            info.size = 1
            import io
            archive.addfile(info, io.BytesIO(b"x"))
        with tarfile.open(archive_path, "r:") as archive:
            with self.assertRaisesRegex(restore.backup_bundle.BundleError, "unsafe archive entry"):
                restore._safe_members(archive)

    def test_backup_requires_quiesced_marker(self):
        self.marker.write_text("not stopped")
        with self.assertRaisesRegex(backup.BundleError, "quiesced marker"):
            backup.create_bundle(self.source, self.output, self.marker, self.key)


if __name__ == "__main__":
    unittest.main()
