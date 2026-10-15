#!/usr/bin/env python3
"""Restore a recovery bundle to an empty disposable DB and private-file root."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

_loader = SourceFileLoader("backup_bundle", str(Path(__file__).with_name("backup-bundle.py")))
_spec = spec_from_loader(_loader.name, _loader)
backup_bundle = module_from_spec(_spec)
_loader.exec_module(backup_bundle)

MAX_TOTAL_BYTES = backup_bundle.MAX_TOTAL_BYTES
MAX_MEMBERS = 100_000
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    return backup_bundle.sha256_file(path)


def _verify_outer_artifact(bundle: Path, key: bytes) -> None:
    try:
        digest_expected = Path(str(bundle) + ".sha256").read_text(encoding="ascii").strip()
        mac_expected = Path(str(bundle) + ".hmac").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise backup_bundle.BundleError("Recovery bundle authentication metadata is missing") from exc
    if not HEX64.fullmatch(digest_expected) or not HEX64.fullmatch(mac_expected):
        raise backup_bundle.BundleError("Recovery bundle authentication metadata is invalid")
    digest = hashlib.sha256()
    mac = hmac.new(backup_bundle.hmac_key(key), digestmod=hashlib.sha256)
    with bundle.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            mac.update(block)
    if not hmac.compare_digest(digest.hexdigest(), digest_expected) or not hmac.compare_digest(mac.hexdigest(), mac_expected):
        raise backup_bundle.BundleError("Recovery bundle authentication failed")


def _safe_members(archive: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    members = archive.getmembers()
    if len(members) > MAX_MEMBERS:
        raise backup_bundle.BundleError("Recovery bundle has too many entries")
    result: dict[str, tarfile.TarInfo] = {}
    total = 0
    for info in members:
        name = info.name
        pure = PurePosixPath(name)
        if (not name or name.startswith("/") or "\\" in name or ".." in pure.parts
                or pure.as_posix() != name or not info.isfile()):
            raise backup_bundle.BundleError("Recovery bundle contains an unsafe archive entry")
        if name in result:
            raise backup_bundle.BundleError("Recovery bundle contains duplicate paths")
        total += info.size
        if info.size < 0 or total > MAX_TOTAL_BYTES:
            raise backup_bundle.BundleError("Recovery bundle exceeds the size limit")
        result[name] = info
    manifest_name = "manifest.json"
    if manifest_name not in result or result[manifest_name].size > MAX_MANIFEST_BYTES:
        raise backup_bundle.BundleError("Recovery bundle manifest is missing or too large")
    return result


def _load_manifest(archive: tarfile.TarFile, members: dict[str, tarfile.TarInfo]) -> dict[str, object]:
    stream = archive.extractfile(members["manifest.json"])
    if stream is None:
        raise backup_bundle.BundleError("Recovery bundle manifest is unreadable")
    try:
        manifest = json.loads(stream.read(MAX_MANIFEST_BYTES + 1))
    except (ValueError, UnicodeDecodeError) as exc:
        raise backup_bundle.BundleError("Recovery bundle manifest is invalid") from exc
    if (not isinstance(manifest, dict) or manifest.get("format") != "school-cms-recovery-bundle"
            or manifest.get("version") != 1 or not isinstance(manifest.get("private_files"), list)):
        raise backup_bundle.BundleError("Unsupported recovery bundle format")
    return manifest


def stage_private_files(archive: tarfile.TarFile, members: dict[str, tarfile.TarInfo],
                        manifest: dict[str, object], stage: Path) -> str:
    files = manifest["private_files"]
    assert isinstance(files, list)
    declared: dict[str, tuple[int, str]] = {}
    for entry in files:
        if not isinstance(entry, dict):
            raise backup_bundle.BundleError("Recovery bundle manifest is invalid")
        rel = entry.get("path")
        size = entry.get("size")
        digest = entry.get("sha256")
        if (not isinstance(rel, str) or not rel or "\\" in rel or PurePosixPath(rel).is_absolute()
                or ".." in PurePosixPath(rel).parts or PurePosixPath(rel).as_posix() != rel
                or not isinstance(size, int) or size < 0 or not isinstance(digest, str) or not HEX64.fullmatch(digest)
                or rel in declared):
            raise backup_bundle.BundleError("Recovery bundle manifest contains an unsafe file entry")
        declared[rel] = (size, digest)
    pg_name = manifest.get("postgres_dump")
    if (not isinstance(pg_name, str) or PurePosixPath(pg_name).name != pg_name
            or not pg_name.endswith(".dump.enc")):
        raise backup_bundle.BundleError("Recovery bundle PostgreSQL dump reference is invalid")
    pg_prefix = f"pg/{pg_name}"
    expected = {"manifest.json", pg_prefix, pg_prefix + ".sha256", pg_prefix + ".hmac"}
    expected.update(f"private/{name}" for name in declared)
    if set(members) != expected:
        raise backup_bundle.BundleError("Recovery bundle entries do not match its manifest")
    dump = archive.extractfile(members[pg_prefix])
    if dump is None:
        raise backup_bundle.BundleError("Recovery bundle PostgreSQL dump is unreadable")
    target_dump = stage / pg_name
    with target_dump.open("xb") as output:
        shutil.copyfileobj(dump, output, 1024 * 1024)
    if not isinstance(manifest.get("postgres_sha256"), str) or not hmac.compare_digest(
            _sha256(target_dump), str(manifest["postgres_sha256"])):
        raise backup_bundle.BundleError("Recovery bundle PostgreSQL dump digest does not match its manifest")
    for suffix in (".sha256", ".hmac"):
        src = archive.extractfile(members[pg_prefix + suffix])
        if src is None:
            raise backup_bundle.BundleError("Recovery bundle PostgreSQL metadata is unreadable")
        with (stage / (pg_name + suffix)).open("xb") as output:
            shutil.copyfileobj(src, output, 4096)
    for rel, (size, expected_hash) in declared.items():
        member = members[f"private/{rel}"]
        if member.size != size:
            raise backup_bundle.BundleError("Recovery bundle private-file size does not match its manifest")
        source = archive.extractfile(member)
        if source is None:
            raise backup_bundle.BundleError("Recovery bundle private file is unreadable")
        destination = stage / "files" / rel
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        file_hash = hashlib.sha256()
        size_seen = 0
        with destination.open("xb") as output:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                size_seen += len(block)
                file_hash.update(block)
                output.write(block)
        if size_seen != size or not hmac.compare_digest(file_hash.hexdigest(), expected_hash):
            raise backup_bundle.BundleError("Recovery bundle private-file integrity check failed")
        os.chmod(destination, 0o600)
    return pg_name


def validate_empty_root(root: Path) -> Path:
    if root.is_symlink() or not root.exists() or not root.is_dir():
        raise backup_bundle.BundleError("Restore private-file root must be an existing real empty directory")
    if any(root.iterdir()):
        raise backup_bundle.BundleError("Restore private-file root must be empty")
    return root.resolve(strict=True)


def restore_bundle(bundle: Path, private_root: Path, marker: Path, key_file: Path,
                   private_root_disposable: bool = False) -> None:
    backup_bundle.require_quiesced_marker(marker)
    if not private_root_disposable:
        raise backup_bundle.BundleError("Explicit disposable private-root attestation is required")
    if (os.environ.get("RESTORE_TARGET_DISPOSABLE") != "YES"
            or os.environ.get("RESTORE_TARGET_ENVIRONMENT") != "disposable"
            or os.environ.get("DJANGO_ENVIRONMENT") != "disposable"):
        raise backup_bundle.BundleError("Explicit disposable restore attestations are required")
    target_db = os.environ.get("PGDATABASE", "")
    production_db = os.environ.get("RESTORE_PRODUCTION_DATABASE_NAME", "")
    if not target_db or not production_db:
        raise backup_bundle.BundleError("PGDATABASE and RESTORE_PRODUCTION_DATABASE_NAME are required")
    if target_db == production_db:
        raise backup_bundle.BundleError("Refusing restore: target matches the configured production database")
    key = backup_bundle.read_key(key_file)
    if bundle.is_symlink() or not bundle.is_file():
        raise backup_bundle.BundleError("Recovery bundle must be a regular file")
    root = validate_empty_root(private_root)
    _verify_outer_artifact(bundle, key)
    parent = root.parent
    with tempfile.TemporaryDirectory(prefix="schoolcms-restore-", dir=parent) as temp_name:
        work = Path(temp_name)
        plain_tar = work / "bundle.tar"
        try:
            subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "600000",
                            "-in", str(bundle), "-out", str(plain_tar), "-pass", f"file:{key_file}"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise backup_bundle.BundleError("Recovery bundle decryption failed") from exc
        if plain_tar.stat().st_size > MAX_TOTAL_BYTES:
            raise backup_bundle.BundleError("Recovery bundle exceeds the size limit")
        extract_dir = work / "staged"
        extract_dir.mkdir(mode=0o700)
        try:
            with tarfile.open(plain_tar, "r:") as archive:
                members = _safe_members(archive)
                manifest = _load_manifest(archive, members)
                pg_name = stage_private_files(archive, members, manifest, extract_dir)
        except (tarfile.TarError, OSError, ValueError) as exc:
            if isinstance(exc, backup_bundle.BundleError):
                raise
            raise backup_bundle.BundleError("Recovery bundle contents are invalid") from exc

        scripts = Path(__file__).resolve().parent
        env = os.environ.copy()
        try:
            result = subprocess.run([str(scripts / "restore-postgres.sh"), str(extract_dir / pg_name)],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, check=False, env=env)
        except OSError as exc:
            raise backup_bundle.BundleError("PostgreSQL restore command could not be started") from exc
        if result.returncode:
            raise backup_bundle.BundleError("PostgreSQL restore failed; private files were not published")
        try:
            staged_files = extract_dir / "files"
            if not staged_files.exists():
                staged_files.mkdir(mode=0o700)
            # Replace the initially empty destination directory atomically so
            # readers can never observe a partially copied private-file tree.
            os.rmdir(root)
            os.replace(staged_files, root)
        except OSError as exc:
            raise backup_bundle.BundleError(
                "PostgreSQL restored but private files were not published; keep the application stopped and discard the target database"
            ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--private-root-disposable", required=True, action="store_true",
                        help="attest that the explicitly selected empty private root is disposable")
    parser.add_argument("--quiesced-marker", required=True, type=Path)
    args = parser.parse_args()
    key_file = os.environ.get("BACKUP_ENCRYPTION_KEY_FILE")
    if not key_file:
        print("Set BACKUP_ENCRYPTION_KEY_FILE to a protected backup key file", file=sys.stderr)
        return 2
    try:
        restore_bundle(args.bundle, args.private_root, args.quiesced_marker, Path(key_file),
                       private_root_disposable=args.private_root_disposable)
    except backup_bundle.BundleError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError:
        print("Recovery bundle could not be restored", file=sys.stderr)
        return 1
    print("Authenticated database and private-file restore completed to the disposable targets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
