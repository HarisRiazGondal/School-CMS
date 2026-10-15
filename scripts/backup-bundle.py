#!/usr/bin/env python3
"""Create a versioned authenticated encrypted database + private-files bundle.

Run only while the application is stopped and all writers to the database and
private storage are quiesced. See docs/RECOVERY_REHEARSAL.md.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

MARKER = b"SCHOOLCMS-QUIESCED-V1\n"
MANIFEST = "manifest.json"
MAX_TOTAL_BYTES = 20 * 1024**3
MAX_FILE_COUNT = 100_000
HMAC_DOMAIN = b"School-CMS recovery bundle HMAC v1\0"


class BundleError(Exception):
    pass


def require_quiesced_marker(path: Path) -> None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        st = os.fstat(descriptor)
        if not stat.S_ISREG(st.st_mode):
            raise BundleError("A valid quiesced marker is required")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            if stream.read(len(MARKER) + 1) != MARKER:
                raise BundleError("A valid quiesced marker is required")
    except OSError as exc:
        raise BundleError("A valid quiesced marker is required") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_key(path: Path) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        st = os.fstat(descriptor)
        if not stat.S_ISREG(st.st_mode) or (stat.S_IMODE(st.st_mode) & 0o077):
            raise BundleError("The backup key file must be a private regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            value = stream.read().rstrip(b"\r\n")
        if not value:
            raise BundleError("The backup key file is empty")
        return value
    except OSError as exc:
        raise BundleError("The backup key file is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def private_file_inventory(root: Path) -> list[dict[str, object]]:
    if root.is_symlink() or not root.is_dir():
        raise BundleError("Private-file root must be a real directory")
    root = root.resolve(strict=True)
    items: list[dict[str, object]] = []
    total = 0
    def walk_error(_error: OSError) -> None:
        raise BundleError("Private storage could not be completely read")

    for current, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=walk_error):
        base = Path(current)
        for name in list(dirs):
            item = base / name
            if item.is_symlink() or not item.is_dir():
                raise BundleError("Private storage contains an unsafe filesystem entry")
        for name in files:
            item = base / name
            rel = item.relative_to(root).as_posix()
            st = item.lstat()
            if not stat.S_ISREG(st.st_mode) or not rel or rel.startswith("/") or ".." in Path(rel).parts:
                raise BundleError("Private storage contains an unsafe filesystem entry")
            total += st.st_size
            if total > MAX_TOTAL_BYTES:
                raise BundleError("Private storage exceeds the recovery bundle size limit")
            digest = hashlib.sha256()
            descriptor = os.open(item, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if (not stat.S_ISREG(opened.st_mode) or opened.st_dev != st.st_dev
                        or opened.st_ino != st.st_ino):
                    raise BundleError("Private storage changed during backup; keep services stopped and retry")
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            items.append({"path": rel, "size": st.st_size, "sha256": digest.hexdigest()})
            if len(items) > MAX_FILE_COUNT:
                raise BundleError("Private storage contains too many files")
    return sorted(items, key=lambda entry: str(entry["path"]))


def hmac_key(passphrase: bytes) -> bytes:
    return hashlib.sha256(HMAC_DOMAIN + passphrase).digest()


def write_sidecars(ciphertext: Path, passphrase: bytes) -> None:
    digest = hashlib.sha256()
    mac = hmac.new(hmac_key(passphrase), digestmod=hashlib.sha256)
    with ciphertext.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            mac.update(block)
    ciphertext.with_name(ciphertext.name + ".sha256").write_text(digest.hexdigest() + "\n", encoding="ascii")
    ciphertext.with_name(ciphertext.name + ".hmac").write_text(mac.hexdigest() + "\n", encoding="ascii")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_quiet(argv: list[str], *, env: dict[str, str] | None = None) -> None:
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, check=False, env=env)
    except OSError as exc:
        raise BundleError("A required recovery command could not be started") from exc
    if result.returncode:
        raise BundleError("A recovery command failed; no sensitive command output was recorded")


def create_bundle(private_root: Path, output_dir: Path, marker: Path, key_file: Path) -> Path:
    require_quiesced_marker(marker)
    key = read_key(key_file)
    inventory = private_file_inventory(private_root)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_dir, 0o700)
    with tempfile.TemporaryDirectory(prefix="schoolcms-recovery-") as scratch_name:
        scratch = Path(scratch_name)
        dump_dir = scratch / "pg"
        dump_dir.mkdir(mode=0o700)
        env = os.environ.copy()
        env["BACKUP_OUTPUT_DIR"] = str(dump_dir)
        scripts = Path(__file__).resolve().parent
        _run_quiet([str(scripts / "backup-postgres.sh")], env=env)
        dumps = list(dump_dir.glob("*.dump.enc"))
        if len(dumps) != 1:
            raise BundleError("PostgreSQL backup did not produce exactly one dump")
        dump = dumps[0]
        for sidecar in (dump.with_name(dump.name + ".sha256"), dump.with_name(dump.name + ".hmac")):
            if not sidecar.is_file() or sidecar.is_symlink():
                raise BundleError("PostgreSQL backup authentication metadata is missing")

        private_root_real = private_root.resolve(strict=True)
        # Recheck the inventory after dumping to detect unexpected writes even if
        # an operator accidentally left a writer active after creating the marker.
        after = private_file_inventory(private_root_real)
        if after != inventory:
            raise BundleError("Private storage changed during backup; keep services stopped and retry")
        manifest = {
            "format": "school-cms-recovery-bundle",
            "version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "private_files": inventory,
            "postgres_dump": dump.name,
            "postgres_sha256": sha256_file(dump),
        }
        plain_tar = scratch / "bundle.tar"
        with tarfile.open(plain_tar, "w", format=tarfile.PAX_FORMAT) as archive:
            info = tarfile.TarInfo(MANIFEST)
            info.mode = 0o600
            encoded = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
            info.size = len(encoded)
            import io
            archive.addfile(info, io.BytesIO(encoded))
            for item in (dump, dump.with_name(dump.name + ".sha256"), dump.with_name(dump.name + ".hmac")):
                archive.add(item, arcname=f"pg/{item.name}", recursive=False)
            for entry in inventory:
                relative = str(entry["path"])
                archive.add(private_root_real / relative, arcname=f"private/{relative}", recursive=False)
        # Catch a source mutation or path swap during archive creation instead
        # of emitting a bundle that only discovers its mismatch on restore.
        with tarfile.open(plain_tar, "r:") as archive:
            members = {item.name: item for item in archive.getmembers()}
            expected_names = {MANIFEST, f"pg/{dump.name}", f"pg/{dump.name}.sha256", f"pg/{dump.name}.hmac"}
            expected_names.update(f"private/{entry['path']}" for entry in inventory)
            if set(members) != expected_names or any(not item.isfile() for item in members.values()):
                raise BundleError("Backup contents changed while the bundle was being created")
            for entry in inventory:
                source = archive.extractfile(members[f"private/{entry['path']}"])
                digest = hashlib.sha256()
                if source is None:
                    raise BundleError("Backup contents changed while the bundle was being created")
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
                if not hmac.compare_digest(digest.hexdigest(), str(entry["sha256"])):
                    raise BundleError("Private storage changed during backup; keep services stopped and retry")
        if plain_tar.stat().st_size > MAX_TOTAL_BYTES:
            raise BundleError("Recovery bundle exceeds the size limit")
        encrypted_tmp = scratch / "bundle.scb.enc"
        _run_quiet(["openssl", "enc", "-aes-256-cbc", "-salt", "-pbkdf2", "-iter", "600000",
                    "-in", str(plain_tar), "-out", str(encrypted_tmp), "-pass", f"file:{key_file}"])
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        final = output_dir / f"schoolcms-recovery-v1-{timestamp}-{secrets.token_hex(5)}.scb.enc"
        with final.open("xb") as stream, encrypted_tmp.open("rb") as source:
            shutil.copyfileobj(source, stream)
        os.chmod(final, 0o600)
        try:
            write_sidecars(final, key)
            os.chmod(final.with_name(final.name + ".sha256"), 0o600)
            os.chmod(final.with_name(final.name + ".hmac"), 0o600)
        except OSError:
            final.unlink(missing_ok=True)
            final.with_name(final.name + ".sha256").unlink(missing_ok=True)
            final.with_name(final.name + ".hmac").unlink(missing_ok=True)
            raise BundleError("Recovery bundle metadata could not be written")
        return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--quiesced-marker", required=True, type=Path)
    args = parser.parse_args()
    key_file = os.environ.get("BACKUP_ENCRYPTION_KEY_FILE")
    if not key_file:
        print("Set BACKUP_ENCRYPTION_KEY_FILE to a protected backup key file", file=sys.stderr)
        return 2
    try:
        result = create_bundle(args.private_root, args.output_dir, args.quiesced_marker, Path(key_file))
    except BundleError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError:
        print("Recovery bundle could not be created", file=sys.stderr)
        return 1
    print(f"Authenticated encrypted recovery bundle created: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
