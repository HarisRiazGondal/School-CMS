"""Authentication abuse controls and compact RFC 6238 TOTP primitives."""
import base64
import binascii
import hashlib
import hmac
import ipaddress
import os
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
import pyotp
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from .models import AuthThrottle, MFADevice, SchoolMembership

THROTTLE_LIMIT = 5
IP_THROTTLE_LIMIT = 30
THROTTLE_WINDOW = timedelta(minutes=15)


def request_ip(request):
    peer = request.META.get("REMOTE_ADDR", "unknown")
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").strip()
        # The deployment proxy must overwrite this with the single client address.
        # Reject chains and malformed values instead of guessing which hop is trusted.
        if forwarded and "," not in forwarded:
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
    return peer[:128]


def throttle_key(kind, value, request):
    material = f"{kind}\0{request_ip(request)}\0{value.strip().casefold()}".encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), material, hashlib.sha256).hexdigest()
    return digest


def auth_throttle_keys(kind, identifier, request):
    return (
        throttle_key(kind, identifier, request),
        throttle_identity_key(kind, identifier),
        throttle_key(f"{kind}-ip", "all-identifiers", request),
    )


def throttle_identity_key(kind, value):
    material = f"{kind}\0{value.strip().casefold()}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), material, hashlib.sha256).hexdigest()


def is_throttled(key):
    row = AuthThrottle.objects.filter(pk=key).only("blocked_until").first()
    return bool(row and row.blocked_until and row.blocked_until > timezone.now())


def record_failure(key, limit=THROTTLE_LIMIT):
    """Increment a shared DB counter with a row lock; tolerates first-hit races."""
    now = timezone.now()
    for _ in range(2):
        AuthThrottle.objects.get_or_create(pk=key, defaults={"window_started": now})
        try:
            from django.db import transaction
            with transaction.atomic():
                row = AuthThrottle.objects.select_for_update().get(pk=key)
                if row.window_started + THROTTLE_WINDOW <= now:
                    row.window_started, row.failures, row.blocked_until = now, 0, None
                row.failures += 1
                if row.failures >= limit:
                    row.blocked_until = now + THROTTLE_WINDOW
                row.save(update_fields=["window_started", "failures", "blocked_until"])
            return
        except AuthThrottle.DoesNotExist:
            continue


def clear_throttle(key):
    AuthThrottle.objects.filter(pk=key).delete()


def mfa_throttle_keys(request, user):
    return auth_throttle_keys("mfa-user", user.get_username(), request)


def mfa_attempt_blocked(request, user):
    return any(is_throttled(key) for key in mfa_throttle_keys(request, user))


def record_mfa_failure(request, user):
    for index, key in enumerate(mfa_throttle_keys(request, user)):
        limit = THROTTLE_LIMIT if index == 0 else (10 if index == 1 else IP_THROTTLE_LIMIT)
        record_failure(key, limit)


def record_auth_failure(kind, identifier, request):
    for index, key in enumerate(auth_throttle_keys(kind, identifier, request)):
        limit = THROTTLE_LIMIT if index == 0 else (10 if index == 1 else IP_THROTTLE_LIMIT)
        record_failure(key, limit)


def clear_mfa_failures(request, user):
    # Leave the shared source-IP counter intact; another account's success must not
    # erase evidence of an IP-wide spray.
    for key in mfa_throttle_keys(request, user)[:2]:
        clear_throttle(key)


def clear_auth_failures(kind, identifier, request):
    # Leave the shared source-IP counter intact after one account succeeds.
    for key in auth_throttle_keys(kind, identifier, request)[:2]:
        clear_throttle(key)


def requires_mfa(user):
    if not user.is_active:
        return False
    if MFADevice.objects.filter(user_id=user.pk, enabled=True).exists():
        return True
    if getattr(settings, "MFA_REQUIRED_FOR_STAFF", not settings.DEBUG) and (user.is_staff or user.is_superuser):
        return True
    if not getattr(settings, "MFA_REQUIRED_FOR_PRIVILEGED_ROLES", not settings.DEBUG):
        return False
    return SchoolMembership.objects.filter(
        user_id=user.pk, user__is_active=True, is_active=True, school__is_active=True,
        role__in=[SchoolMembership.Role.SCHOOL_ADMIN, SchoolMembership.Role.ACCOUNTANT],
    ).exists()


def start_mfa_pending(request, user, backend, next_url=""):
    request.session["mfa_pending_user_id"] = user.pk
    request.session["mfa_pending_backend"] = backend
    request.session["mfa_pending_at"] = timezone.now().timestamp()
    request.session["mfa_pending_auth_hash"] = user.get_session_auth_hash()
    request.session["mfa_next"] = next_url


def clear_mfa_pending(request):
    for key in (
        "mfa_pending_user_id", "mfa_pending_backend", "mfa_pending_at",
        "mfa_pending_auth_hash", "mfa_next",
    ):
        request.session.pop(key, None)


def _fernet():
    key = getattr(settings, "MFA_ENCRYPTION_KEY", "") or os.environ.get("MFA_ENCRYPTION_KEY", "")
    if not key:
        raise ImproperlyConfigured("MFA_ENCRYPTION_KEY must be configured before enrolling MFA.")
    try:
        raw = key.encode("ascii")
        # Accept a Fernet key directly or a raw 32-byte URL-safe key.
        if len(base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))) != 32:
            raise ValueError
        return Fernet(raw)
    except (ValueError, TypeError, UnicodeError, binascii.Error) as exc:
        raise ImproperlyConfigured("MFA_ENCRYPTION_KEY must be a valid Fernet 32-byte URL-safe key.") from exc


def encrypt_secret(secret):
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(ciphertext):
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise ImproperlyConfigured("Could not decrypt stored MFA secret; verify MFA_ENCRYPTION_KEY.") from exc


def new_totp_secret():
    return pyotp.random_base32()


def make_recovery_codes(count=10):
    return [secrets.token_hex(5).upper() for _ in range(count)]


def recovery_code_digest(code):
    normalized = code.strip().upper().encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode(), b"schoolcms-mfa-recovery\0" + normalized, hashlib.sha256).hexdigest()


def hash_recovery_codes(user, codes):
    from .models import MFARecoveryCode
    user.mfa_recovery_codes.all().delete()
    MFARecoveryCode.objects.bulk_create([
        MFARecoveryCode(user=user, code_hash=recovery_code_digest(code)) for code in codes
    ])


def consume_recovery_code(user, supplied):
    if not supplied:
        return False
    from django.db import transaction
    from .models import MFARecoveryCode
    for item in user.mfa_recovery_codes.all():
        if hmac.compare_digest(recovery_code_digest(supplied), item.code_hash):
            with transaction.atomic():
                locked = MFARecoveryCode.objects.select_for_update().filter(pk=item.pk).first()
                if locked and hmac.compare_digest(recovery_code_digest(supplied), locked.code_hash):
                    locked.delete()
                    return True
    return False
