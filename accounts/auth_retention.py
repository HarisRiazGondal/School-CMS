"""Bounded retention operations for database-backed authentication throttles."""
from datetime import datetime, timedelta

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from .models import AuthThrottle


def database_now():
    """Return the database server's current timestamp, normalized for Django."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT CURRENT_TIMESTAMP")
        value = cursor.fetchone()[0]
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if timezone.is_naive(value) and timezone.is_aware(timezone.now()):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def stale_throttles(*, cutoff, now):
    """Rows old enough to retire, excluding every currently blocked bucket."""
    return AuthThrottle.objects.filter(window_started__lt=cutoff).filter(
        Q(blocked_until__isnull=True) | Q(blocked_until__lte=now)
    )


def prune_stale_throttles(*, older_than_days=30, batch_size=1000, apply=False):
    """Inspect or delete at most ``batch_size`` stale rows using database time."""
    now = database_now()
    cutoff = now - timedelta(days=older_than_days)
    with transaction.atomic():
        queryset = stale_throttles(cutoff=cutoff, now=now).order_by("window_started", "pk")
        # One extra key tells operators whether another bounded pass is needed.
        keys = list(queryset.select_for_update().values_list("pk", flat=True)[:batch_size + 1])
        selected = keys[:batch_size]
        deleted = 0
        if apply and selected:
            # Reapply the stale predicate at deletion time. The row locks keep a
            # concurrent authentication attempt from extending a selected bucket.
            deleted, _ = stale_throttles(cutoff=cutoff, now=now).filter(pk__in=selected).delete()
    return {
        "eligible": len(selected),
        "deleted": deleted,
        "has_more": len(keys) > batch_size,
        "cutoff": cutoff,
        "database_now": now,
    }
