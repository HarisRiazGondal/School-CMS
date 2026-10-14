from .models import AuditEvent


def record_event(*, school, action, object_type, object_id, actor=None, details=None):
    """Append an audit event after validating its bounded, non-secret details."""
    return AuditEvent.objects.create(
        school=school,
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        details={} if details is None else details,
    )
