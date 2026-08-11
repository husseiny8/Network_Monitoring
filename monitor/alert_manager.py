from django.db import transaction
from django.utils import timezone

from .models import Alert


@transaction.atomic
def raise_alert(
    *,
    alert_key,
    alert_type,
    title,
    message,
    severity,
    device=None,
    status=None,
):
    """
    Create or update an active Incident.

    اگر Alert باز مربوط به همین alert_key وجود داشته باشد:
        Alert جدید ساخته نمی‌شود.
        occurrence_count افزایش پیدا می‌کند.
        آخرین وضعیت و پیام به‌روزرسانی می‌شوند.

    در غیر این صورت:
        یک Incident جدید ساخته می‌شود.
    """

    if status is None:
        status = (
            "down"
            if severity == "critical"
            else "degraded"
        )

    alert = (
        Alert.objects
        .select_for_update()
        .filter(
            alert_key=alert_key,
            is_resolved=False,
        )
        .first()
    )

    if alert:
        alert.occurrence_count += 1
        alert.last_seen_at = timezone.now()

        alert.severity = severity
        alert.status = status
        alert.title = title
        alert.message = message

        if device is not None:
            alert.device = device

        alert.save(
            update_fields=[
                "occurrence_count",
                "last_seen_at",
                "severity",
                "status",
                "title",
                "message",
                "device",
            ]
        )

        return alert, False

    alert = Alert.objects.create(
        alert_key=alert_key,
        alert_type=alert_type,
        device=device,
        severity=severity,
        status=status,
        title=title,
        message=message,
        is_resolved=False,
        occurrence_count=1,
    )

    return alert, True


@transaction.atomic
def resolve_alert(
    *,
    alert_key,
    message=None,
):
    """
    Resolve the currently active Incident for alert_key.
    """

    alert = (
        Alert.objects
        .select_for_update()
        .filter(
            alert_key=alert_key,
            is_resolved=False,
        )
        .first()
    )

    if not alert:
        return None

    alert.resolve(message=message)

    return alert