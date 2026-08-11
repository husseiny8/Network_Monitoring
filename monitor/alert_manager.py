from django.db import transaction
from django.utils import timezone

from .models import Alert, AlertState


SEVERITY_PRIORITY = {
    "info": 1,
    "warning": 2,
    "critical": 3,
}


@transaction.atomic
def get_alert_state(alert_key):
    """
    دریافت یا ایجاد State مربوط به alert_key.

    select_for_update باعث می‌شود در Pollهای همزمان،
    Counterها دچار Race Condition نشوند.
    """

    state, _ = (
        AlertState.objects
        .select_for_update()
        .get_or_create(
            alert_key=alert_key,
        )
    )

    return state


@transaction.atomic
def raise_alert(
    *,
    alert_key,
    alert_type,
    title,
    message="",
    severity="info",
    status="down",
    device=None,
    occurrence_count=None,
):
    """
    ایجاد یا به‌روزرسانی Incident.

    اگر Incident باز وجود داشته باشد:
        Alert جدید ساخته نمی‌شود.

    occurrence_count:
        در ایجاد اولیه، اگر مقدار داده شود از آن استفاده می‌شود.
    """

    now = timezone.now()

    alert = (
        Alert.objects
        .select_for_update()
        .filter(
            alert_key=alert_key,
            is_resolved=False,
        )
        .order_by("-created_at")
        .first()
    )

    if alert:

        alert.occurrence_count += 1
        alert.last_seen_at = now

        if title:
            alert.title = title

        if message:
            alert.message = message

        if device is not None:
            alert.device = device

        current_priority = SEVERITY_PRIORITY.get(
            alert.severity,
            1,
        )

        new_priority = SEVERITY_PRIORITY.get(
            severity,
            1,
        )

        if new_priority > current_priority:
            alert.severity = severity

        if status in dict(Alert.STATUS_CHOICES):
            alert.status = status

        alert.save(
            update_fields=[
                "occurrence_count",
                "last_seen_at",
                "title",
                "message",
                "device",
                "severity",
                "status",
            ]
        )

        return alert, False

    initial_count = occurrence_count or 1

    alert = Alert.objects.create(
        alert_key=alert_key,
        alert_type=alert_type,
        device=device,
        severity=severity,
        status=status,
        title=title,
        message=message,
        is_resolved=False,
        occurrence_count=initial_count,
        last_seen_at=now,
    )

    return alert, True


@transaction.atomic
def resolve_alert(
    *,
    alert_key,
    message=None,
):
    """
    Resolve کردن Incident باز.
    """

    alert = (
        Alert.objects
        .select_for_update()
        .filter(
            alert_key=alert_key,
            is_resolved=False,
        )
        .order_by("-created_at")
        .first()
    )

    if not alert:
        return None

    alert.resolve(message=message)

    return alert


@transaction.atomic
def process_failure(
    *,
    alert_key,
    alert_type,
    title,
    message,
    severity,
    status,
    failure_threshold,
    device=None,
    value=None,
):
    """
    ثبت یک Failure و اجرای Hysteresis.

    مثال:
        threshold = 3

        Failure 1 -> فقط State
        Failure 2 -> فقط State
        Failure 3 -> ایجاد Incident
        Failure 4 -> update همان Incident
    """

    state = get_alert_state(alert_key)

    state.consecutive_failures += 1
    state.consecutive_successes = 0

    state.last_status = status
    state.last_severity = severity
    state.last_value = value
    state.last_message = message

    state.save(
        update_fields=[
            "consecutive_failures",
            "consecutive_successes",
            "last_status",
            "last_severity",
            "last_value",
            "last_message",
            "updated_at",
        ]
    )

    # اگر Incident از قبل باز است،
    # دیگر لازم نیست threshold را دوباره بررسی کنیم.
    existing_alert = (
        Alert.objects
        .select_for_update()
        .filter(
            alert_key=alert_key,
            is_resolved=False,
        )
        .first()
    )

    if existing_alert:

        alert, created = raise_alert(
            alert_key=alert_key,
            alert_type=alert_type,
            title=title,
            message=message,
            severity=severity,
            status=status,
            device=device,
        )

        return {
            "alert": alert,
            "created": created,
            "triggered": True,
            "failure_count": state.consecutive_failures,
            "success_count": state.consecutive_successes,
        }

    # هنوز به Threshold نرسیده‌ایم
    if state.consecutive_failures < max(1, failure_threshold):

        return {
            "alert": None,
            "created": False,
            "triggered": False,
            "failure_count": state.consecutive_failures,
            "success_count": state.consecutive_successes,
        }

    # Threshold رسیده است -> Incident ایجاد شود
    alert, created = raise_alert(
        alert_key=alert_key,
        alert_type=alert_type,
        title=title,
        message=message,
        severity=severity,
        status=status,
        device=device,
        occurrence_count=state.consecutive_failures,
    )

    return {
        "alert": alert,
        "created": created,
        "triggered": True,
        "failure_count": state.consecutive_failures,
        "success_count": state.consecutive_successes,
    }


@transaction.atomic
def process_recovery(
    *,
    alert_key,
    recovery_threshold,
    recovery_message="",
):
    """
    ثبت یک Recovery Check و اجرای Recovery Hysteresis.

    مثال:
        recovery_threshold = 2

        Success 1 -> هنوز Resolved نمی‌شود
        Success 2 -> Incident Resolve می‌شود
    """

    state = get_alert_state(alert_key)

    state.consecutive_successes += 1
    state.consecutive_failures = 0

    state.last_status = "resolved"
    state.last_message = recovery_message

    state.save(
        update_fields=[
            "consecutive_successes",
            "consecutive_failures",
            "last_status",
            "last_message",
            "updated_at",
        ]
    )

    # اگر Incident بازی نداریم،
    # فقط State را Reset/Update می‌کنیم.
    open_alert = (
        Alert.objects
        .select_for_update()
        .filter(
            alert_key=alert_key,
            is_resolved=False,
        )
        .first()
    )

    if not open_alert:

        return {
            "alert": None,
            "resolved": False,
            "recovery_count": state.consecutive_successes,
        }

    # هنوز Recovery Threshold نرسیده
    if state.consecutive_successes < max(
        1,
        recovery_threshold,
    ):

        return {
            "alert": open_alert,
            "resolved": False,
            "recovery_count": state.consecutive_successes,
        }

    # Recovery کامل شد
    resolved_alert = resolve_alert(
        alert_key=alert_key,
        message=recovery_message,
    )

    # Counterها برای Incident بعدی از صفر شروع شوند
    state.consecutive_failures = 0
    state.consecutive_successes = 0
    state.save(
        update_fields=[
            "consecutive_failures",
            "consecutive_successes",
            "updated_at",
        ]
    )

    return {
        "alert": resolved_alert,
        "resolved": bool(resolved_alert),
        "recovery_count": recovery_threshold,
    }


def is_alert_open(alert_key):
    return Alert.objects.filter(
        alert_key=alert_key,
        is_resolved=False,
    ).exists()