import hashlib
import io
import stat
import os
import shlex
import subprocess  # nosec B404  # trusted operator scanner command; no shell or user-supplied executable.
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import get_valid_filename

from audit.services import record_event
from accounts.models import SchoolMembership
from learning.models import Assignment, Submission
from learning.services import can_manage_section, student_enrollment_for_assignment
from .models import PrivateAttachment


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".text"}
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


def _ensure_private_directory(path):
    path = Path(path)
    if path.is_symlink():
        raise ValidationError("Private storage cannot use a symbolic-link directory.")
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)
        info = path.lstat()
    except OSError as exc:
        raise ValidationError("Private storage permissions are not secure.") from exc
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValidationError("Private storage must be owned by this service and accessible only to it.")
    return path


def _root():
    configured = getattr(settings, "PRIVATE_FILE_ROOT", None)
    root = Path(configured) if configured else Path(settings.BASE_DIR) / "privatefiles_data"
    # Django settings normalize paths; inspect the raw deployment value too so a
    # configured symlink cannot silently redirect private storage.
    raw_configured = os.environ.get("PRIVATE_FILE_ROOT")
    if raw_configured is None and os.environ.get("PRIVATE_FILE_ROOT_FILE"):
        try:
            raw_configured = Path(os.environ["PRIVATE_FILE_ROOT_FILE"]).read_text().strip()
        except OSError as exc:
            raise ValidationError("Private storage configuration could not be read.") from exc
    if raw_configured:
        raw_path = Path(os.path.abspath(os.path.normpath(raw_configured)))
        if raw_path.is_symlink() or raw_path.resolve() != raw_path:
            raise ValidationError("Private storage cannot use a symbolic-link directory.")
    root = _ensure_private_directory(root)
    return root.resolve(strict=True)


def _max_bytes():
    return int(getattr(settings, "PRIVATE_FILE_MAX_BYTES", DEFAULT_MAX_BYTES))


def sanitize_filename(name):
    """Return a bounded basename safe for a download header; never used as a path."""
    basename = str(name or "attachment").replace("\\", "/").split("/")[-1]
    basename = "".join(ch for ch in basename if ch.isprintable() and ord(ch) >= 32)
    basename = get_valid_filename(basename)[:180].strip("._")
    return basename or "attachment.txt"


def _read_limited(upload):
    limit = _max_bytes()
    size = 0
    chunks = []
    for chunk in upload.chunks():
        size += len(chunk)
        if size > limit:
            raise ValidationError(f"Files must be no larger than {limit} bytes.")
        chunks.append(chunk)
    if not size:
        raise ValidationError("Empty files are not accepted.")
    return b"".join(chunks)


def _validate_content(name, data):
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationError("Only PDF and plain text attachments are supported.")
    if data.startswith(b"%PDF-"):
        if suffix != ".pdf" or b"%%EOF" not in data[-2048:]:
            raise ValidationError("The file does not contain a valid PDF signature and trailer.")
        try:
            from pypdf import PdfReader, filters
            # Bound decoded Flate streams in this process. pypdf 6.10.0 exposes this
            # guard to prevent small compressed inputs from expanding without limit.
            for budget_name in (
                "ZLIB_MAX_OUTPUT_LENGTH", "LZW_MAX_OUTPUT_LENGTH", "RUN_LENGTH_MAX_OUTPUT_LENGTH",
                "MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH", "JBIG2_MAX_OUTPUT_LENGTH",
            ):
                if hasattr(filters, budget_name):
                    setattr(filters, budget_name, 32 * 1024 * 1024)
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 500:
                raise ValueError("encrypted, empty, or oversized PDF")
            _ = reader.pages[0].mediabox
            dangerous_keys = {"/JavaScript", "/JS", "/OpenAction", "/AA", "/AcroForm", "/XFA",
                              "/EmbeddedFiles", "/Filespec", "/Launch", "/SubmitForm", "/ImportData",
                              "/URI", "/RichMedia", "/Movie", "/Sound", "/EmbeddedFile", "/EF",
                              "/GoToR", "/Thread", "/3D", "/Screen", "/Rendition"}
            seen = set()
            stack = [reader.trailer]
            while stack:
                current = stack.pop()
                if hasattr(current, "idnum") and hasattr(current, "get_object"):
                    marker = (current.idnum, getattr(current, "generation", 0))
                    if marker in seen:
                        continue
                    seen.add(marker)
                    if len(seen) > 100_000:
                        raise ValueError("PDF object budget exceeded")
                    current = current.get_object()
                if hasattr(current, "items"):
                    for key, value in current.items():
                        if str(key) in dangerous_keys:
                            raise ValueError("active or embedded PDF content is not accepted")
                        stack.append(value)
                elif isinstance(current, (list, tuple)):
                    stack.extend(current)
        except Exception as exc:
            raise ValidationError("The file does not contain a safe, valid PDF.") from exc
        return "application/pdf"
    if suffix not in {".txt", ".text"}:
        raise ValidationError("The file contents do not match the file extension.")
    try:
        decoded = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationError("Text attachments must use UTF-8 encoding.") from exc
    if "\x00" in decoded or any(ord(ch) < 32 and ch not in "\n\r\t\f" for ch in decoded):
        raise ValidationError("The file does not contain safe plain text.")
    printable = sum(ch.isprintable() or ch in "\n\r\t\f" for ch in decoded)
    if printable / max(1, len(decoded)) < 0.98:
        raise ValidationError("The file does not contain safe plain text.")
    return "text/plain; charset=utf-8"


def _scanner_command():
    configured = getattr(settings, "PRIVATE_FILE_SCANNER_COMMAND", None)
    if not configured:
        return None
    if isinstance(configured, str):
        command = shlex.split(configured)
    else:
        command = list(configured)
    return command or None


def _scan(path):
    command = _scanner_command()
    if not command:
        raise ValidationError("Private file scanning is unavailable; the upload was rejected.")
    expanded = [str(part).replace("{path}", str(path)) for part in command]
    if not any("{path}" in str(part) for part in command):
        expanded.append(str(path))
    timeout = int(getattr(settings, "PRIVATE_FILE_SCAN_TIMEOUT", 30))
    try:
        result = subprocess.run(expanded, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,  # nosec B603  # trusted scanner argv, opaque app-created path, shell=False.
                                stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError("Private file scanning is unavailable; the upload was rejected.") from exc
    if result.returncode == 0:
        return PrivateAttachment.ScanStatus.CLEAN
    if result.returncode == 1:
        return PrivateAttachment.ScanStatus.QUARANTINED
    raise ValidationError("Private file scanning failed; the upload was rejected.")


def _authorize_submission_upload(user, submission):
    assignment = submission.assignment
    active_enrollment = student_enrollment_for_assignment(user, assignment)
    if not assignment.is_published or active_enrollment is None or active_enrollment.pk != submission.enrollment_id:
        raise PermissionDenied("Only an actively enrolled student may upload to this submission.")
    if submission.enrollment.student.user_id != user.pk:
        raise PermissionDenied("This submission belongs to another student.")
    if submission.graded_at is not None:
        raise PermissionDenied("Attachments cannot be added after grading.")
    if assignment.due_at and timezone.now() > assignment.due_at:
        from learning.services import _school_policy
        if not bool(_school_policy(assignment.section.school_class.school, "late_submission_allowed", True)):
            raise PermissionDenied("Late submission attachments are not allowed for this school.")
    return assignment, submission


def _authorized_upload(user, *, assignment=None, submission=None):
    if (assignment is None) == (submission is None):
        raise ValidationError("Choose exactly one assignment or submission.")
    if submission is not None:
        submission = Submission.objects.select_related(
            "assignment__section__school_class__school", "assignment__subject", "enrollment__student"
        ).get(pk=submission.pk)
        return _authorize_submission_upload(user, submission)
    assignment = Assignment.objects.select_related("section__school_class__school", "subject").get(pk=assignment.pk)
    if not can_manage_section(user, assignment.section, assignment.subject):
        raise PermissionDenied("You are not authorized for this assignment.")
    return assignment, None


def create_attachment(user, uploaded_file, *, assignment=None, submission=None):
    assignment, submission = _authorized_upload(user, assignment=assignment, submission=submission)
    assignment_id = assignment.pk
    submission_id = submission.pk if submission else None
    original_name = sanitize_filename(getattr(uploaded_file, "name", "attachment.txt"))
    data = _read_limited(uploaded_file)
    content_type = _validate_content(original_name, data)
    sha256 = hashlib.sha256(data).hexdigest()
    root = _root()
    staging = _ensure_private_directory(root / ".staging")
    key = uuid.uuid4().hex
    staged_path = staging / key
    final_path = root / "quarantine" / key
    status = None
    try:
        fd = os.open(staged_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        status = _scan(staged_path)
        with transaction.atomic():
            if submission_id:
                submission = Submission.objects.select_for_update().select_related(
                    "assignment__section__school_class__school", "assignment__subject", "enrollment__student"
                ).get(pk=submission_id)
                assignment, submission = _authorize_submission_upload(user, submission)
            else:
                assignment, submission = _authorized_upload(user, assignment=assignment)
            destination_dir = _ensure_private_directory(
                root / ("clean" if status == PrivateAttachment.ScanStatus.CLEAN else "quarantine")
            )
            final_path = destination_dir / key
            os.replace(staged_path, final_path)
            attachment = PrivateAttachment.objects.create(
                assignment=assignment if submission is None else None, submission=submission, storage_key=key,
                original_name=original_name, content_type=content_type, size=len(data),
                sha256=sha256, uploaded_by=user, scan_status=status,
            )
            school = assignment.section.school_class.school
            record_event(school=school, actor=user, action="privatefiles.attachment_uploaded",
                         object_type="private_attachment", object_id=attachment.pk,
                         details={"owner_type": "submission" if submission else "assignment",
                                  "owner_id": str(submission.pk if submission else assignment.pk),
                                  "size": len(data), "scan_status": status})
            return attachment
    except Exception:
        for path in (staged_path, final_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _attachment_path(attachment):
    if not attachment.storage_key or "/" in attachment.storage_key or "\\" in attachment.storage_key or ".." in attachment.storage_key:
        raise ValidationError("Invalid private storage key.")
    state_dir = "clean" if attachment.scan_status == PrivateAttachment.ScanStatus.CLEAN else "quarantine"
    root = _root()
    directory = _ensure_private_directory(root / state_dir)
    path = directory / attachment.storage_key
    if path.is_symlink() or root not in path.resolve().parents:
        raise ValidationError("Invalid private storage path.")
    return path


def authorize_download(user, attachment):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    if attachment.scan_status != PrivateAttachment.ScanStatus.CLEAN:
        raise PermissionDenied("This file is quarantined and cannot be downloaded.")
    assignment = attachment.assignment if attachment.assignment_id else attachment.submission.assignment
    assignment = Assignment.objects.select_related("section__school_class__school", "subject").get(pk=assignment.pk)
    if attachment.submission_id:
        submission = Submission.objects.select_related("enrollment__student").get(pk=attachment.submission_id)
        if submission.enrollment.student.user_id == user.pk and submission.enrollment.student.school_id == assignment.section.school_class.school_id:
            if not SchoolMembership.objects.filter(user=user, user__is_active=True, school=assignment.section.school_class.school,
                school__is_active=True, role=SchoolMembership.Role.STUDENT, is_active=True).exists():
                raise PermissionDenied
            return
    if not can_manage_section(user, assignment.section, assignment.subject):
        if not attachment.submission_id and assignment.is_published and student_enrollment_for_assignment(user, assignment):
            return
        raise PermissionDenied


def open_attachment(user, attachment):
    authorize_download(user, attachment)
    path = _attachment_path(attachment)
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077
                or info.st_nlink != 1 or info.st_size != attachment.size):
            os.close(descriptor)
            raise ValidationError("Private file is unavailable.")
        source = os.fdopen(descriptor, "rb")
        digest = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
        if digest.hexdigest() != attachment.sha256:
            source.close()
            raise ValidationError("Private file integrity check failed.")
        source.seek(0)
    except OSError as exc:
        raise ValidationError("Private file is unavailable.") from exc
    try:
        record_event(school=attachment.assignment.section.school_class.school if attachment.assignment_id
                     else attachment.submission.assignment.section.school_class.school,
                     actor=user, action="privatefiles.attachment_downloaded", object_type="private_attachment",
                     object_id=attachment.pk, details={"size": attachment.size})
    except Exception:
        source.close()
        raise
    return source
