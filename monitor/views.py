import csv
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from Connection.dns_lookup import lookup as dns_lookup
from Connection.ping import ping_and_store
from Connection.health import calculate_health_score
from Connection.services import get_default_gateway, run_all as run_service_checks
from .models import Device, SystemSettings
from Devices import device as device_scanner
from .models import Ping
from time import timezone
from .alert_manager import *

PERIOD_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}
PERIOD_LABELS = {
    "daily": "گزارش روزانه",
    "weekly": "گزارش هفتگی",
    "monthly": "گزارش ماهانه",
}

HIGH_LATENCY_WARNING_MS = 200
HIGH_LATENCY_CRITICAL_MS = 500

PACKET_LOSS_WARNING_PERCENT = 10
PACKET_LOSS_CRITICAL_PERCENT = 30

PACKET_LOSS_SAMPLE_SIZE = 10


def custom_404(request, exception):
    return render(
        request,
        "errors/404.html",
        status=404,
    )


def custom_500(request):
    return render(
        request,
        "errors/500.html",
        status=500,
    )

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def sync_devices(subnet=None):
    """
    ARP scan و هماهنگ‌سازی Deviceها.

    Hysteresis:
        Failureهای متوالی -> Device Down
        Successهای متوالی -> Device Recovery

    هر Device یک alert_key مستقل دارد:
        device:<device_id>:down
    """

    settings_obj = SystemSettings.load()

    if subnet is None:
        subnet = settings_obj.scan_subnet

    failure_threshold = (
        settings_obj.failure_threshold
        if settings_obj.hysteresis_enabled
        else 1
    )

    recovery_threshold = (
        settings_obj.recovery_threshold
        if settings_obj.hysteresis_enabled
        else 1
    )

    try:
        found = device_scanner.scan(subnet)
    except Exception as exc:
        return False, str(exc)

    found_by_ip = {
        item["ip"]: item.get("mac", "")
        for item in found
        if item.get("ip")
    }

    existing_by_ip = {
        device.ip_address: device
        for device in Device.objects.all()
    }

    # ==========================================================
    # Devices found by ARP scan
    # ==========================================================

    for ip, mac in found_by_ip.items():

        device = existing_by_ip.get(ip)

        # ------------------------------------------------------
        # New device
        # ------------------------------------------------------

        if device is None:

            device = Device.objects.create(
                ip_address=ip,
                mac_address=mac,
                is_online=True,
            )

            continue

        was_offline = not device.is_online

        device.mac_address = (
            mac or device.mac_address
        )

        device.is_online = True
        device.last_seen = timezone.now()

        device.save(
            update_fields=[
                "mac_address",
                "is_online",
                "last_seen",
            ]
        )

        # ------------------------------------------------------
        # Device recovery
        # ------------------------------------------------------

        alert_key = f"device:{device.id}:down"

        recovery_result = process_recovery(
            alert_key=alert_key,
            recovery_threshold=recovery_threshold,
            recovery_message=(
                f"{device.display_name} is back online. "
                f"{device.ip_address} responded to the "
                f"latest network scan."
            ),
        )

        if recovery_result["resolved"]:

            device.is_online = True
            device.last_seen = timezone.now()

            device.save(
                update_fields=[
                    "is_online",
                    "last_seen",
                ]
            )

    # ==========================================================
    # Devices missing from ARP scan
    # ==========================================================

    for ip, device in existing_by_ip.items():

        if ip in found_by_ip:
            continue

        alert_key = f"device:{device.id}:down"

        failure_result = process_failure(
            alert_key=alert_key,
            alert_type="device_down",
            title=f"{device.display_name} disconnected",
            message=(
                f"{device.ip_address} did not respond "
                f"to the latest network scan."
            ),
            severity="critical",
            status="down",
            failure_threshold=failure_threshold,
            device=device,
        )

        # ------------------------------------------------------
        # Only mark Device offline after the threshold is reached
        # ------------------------------------------------------

        if failure_result["triggered"]:

            if device.is_online:

                device.is_online = False

                device.save(
                    update_fields=[
                        "is_online",
                    ]
                )

    return True, None



def record_ping(target=None, user=None, device=None):
    """
    اجرای Ping و مدیریت:
        Internet Down
        Internet Recovery
        High Latency
        Packet Loss
    """

    settings_obj = SystemSettings.load()

    if target is None:
        target = settings_obj.ping_target

    target = str(target).strip()

    if not target:
        return {
            "success": False,
            "latency": None,
            "message": "No ping target configured.",
        }

    result = ping_and_store(
        target,
        user=user,
        device=device,
    )

    failure_threshold = (
        settings_obj.failure_threshold
        if settings_obj.hysteresis_enabled
        else 1
    )

    recovery_threshold = (
        settings_obj.recovery_threshold
        if settings_obj.hysteresis_enabled
        else 1
    )

    internet_alert_key = f"internet:{target}"

    # =========================================================
    # Ping FAILED
    # =========================================================

    if not result.get("success"):

        failure_message = result.get(
            "message",
            "Ping failed.",
        )

        failure_result = process_failure(
            alert_key=internet_alert_key,
            alert_type="internet_down",
            title="Internet connectivity lost",
            message=(
                f"Ping to {target} failed: "
                f"{failure_message}"
            ),
            severity="critical",
            status="down",
            failure_threshold=failure_threshold,
            device=device,
        )

        result["alert_triggered"] = (
            failure_result["triggered"]
        )

        result["alert_created"] = (
            failure_result["created"]
        )

        if failure_result["alert"]:
            alert = failure_result["alert"]

            result["alert_id"] = alert.id
            result["alert_status"] = alert.status
            result["alert_occurrence_count"] = (
                alert.occurrence_count
            )
            result["alert_duration_seconds"] = (
                alert.duration_seconds
            )

        result["failure_count"] = (
            failure_result["failure_count"]
        )

        result["recovery_count"] = (
            failure_result["success_count"]
        )

        # در زمان Down بودن، High Latency معنا ندارد.
        process_recovery(
            alert_key=f"latency:{target}",
            recovery_threshold=1,
            recovery_message=(
                f"High latency monitoring stopped because "
                f"{target} is unreachable."
            ),
        )

        return result

    # =========================================================
    # Ping SUCCESS
    # =========================================================

    recovery_result = process_recovery(
        alert_key=internet_alert_key,
        recovery_threshold=recovery_threshold,
        recovery_message=(
            f"Internet connectivity restored. "
            f"Ping to {target} succeeded."
            + (
                f" Latency: {result.get('latency')} ms."
                if result.get("latency") is not None
                else ""
            )
        ),
    )

    result["internet_recovery_count"] = (
        recovery_result["recovery_count"]
    )

    if recovery_result["resolved"]:
        recovered_alert = recovery_result["alert"]

        result["internet_alert_resolved"] = True
        result["internet_alert_id"] = recovered_alert.id
        result["internet_outage_duration_seconds"] = (
            recovered_alert.duration_seconds
        )
    else:
        result["internet_alert_resolved"] = False

    # =========================================================
    # High Latency
    # =========================================================

    latency = result.get("latency")

    if latency is not None:

        latency_key = f"latency:{target}"

        if latency < settings_obj.high_latency_warning_ms:

            latency_recovery = process_recovery(
                alert_key=latency_key,
                recovery_threshold=recovery_threshold,
                recovery_message=(
                    f"Latency to {target} returned to normal. "
                    f"Current latency: {latency} ms."
                ),
            )

            result["latency_alert"] = {
                "status": (
                    "resolved"
                    if latency_recovery["resolved"]
                    else "healthy"
                ),
                "alert_id": (
                    latency_recovery["alert"].id
                    if latency_recovery["alert"]
                    else None
                ),
                "recovery_count": (
                    latency_recovery["recovery_count"]
                ),
            }

        else:

            severity = (
                "critical"
                if latency >= settings_obj.high_latency_critical_ms
                else "warning"
            )

            latency_failure = process_failure(
                alert_key=latency_key,
                alert_type="high_latency",
                title=f"High latency to {target}",
                message=(
                    f"Latency to {target} is "
                    f"{latency} ms."
                ),
                severity=severity,
                status="degraded",
                failure_threshold=failure_threshold,
                device=device,
                value=latency,
            )

            result["latency_alert"] = {
                "status": (
                    "degraded"
                    if latency_failure["triggered"]
                    else "pending"
                ),
                "severity": severity,
                "alert_id": (
                    latency_failure["alert"].id
                    if latency_failure["alert"]
                    else None
                ),
                "failure_count": (
                    latency_failure["failure_count"]
                ),
            }

    # =========================================================
    # Packet Loss
    # =========================================================

    packet_loss = get_packet_loss_for_target(
        target=target,
        device=device,
        sample_size=10,
    )

    result["packet_loss"] = packet_loss

    if packet_loss is not None:

        packet_loss_key = f"packet_loss:{target}"

        if (
            packet_loss
            < settings_obj.packet_loss_warning_percent
        ):

            packet_recovery = process_recovery(
                alert_key=packet_loss_key,
                recovery_threshold=recovery_threshold,
                recovery_message=(
                    f"Packet loss to {target} returned "
                    f"to normal. Current loss: "
                    f"{packet_loss}%."
                ),
            )

            result["packet_loss_alert"] = {
                "status": (
                    "resolved"
                    if packet_recovery["resolved"]
                    else "healthy"
                ),
                "alert_id": (
                    packet_recovery["alert"].id
                    if packet_recovery["alert"]
                    else None
                ),
                "recovery_count": (
                    packet_recovery["recovery_count"]
                ),
            }

        else:

            severity = (
                "critical"
                if packet_loss
                >= settings_obj.packet_loss_critical_percent
                else "warning"
            )

            packet_failure = process_failure(
                alert_key=packet_loss_key,
                alert_type="packet_loss",
                title=f"Packet loss detected for {target}",
                message=(
                    f"Packet loss to {target} is "
                    f"{packet_loss}%."
                ),
                severity=severity,
                status="degraded",
                failure_threshold=failure_threshold,
                device=device,
                value=packet_loss,
            )

            result["packet_loss_alert"] = {
                "status": (
                    "degraded"
                    if packet_failure["triggered"]
                    else "pending"
                ),
                "severity": severity,
                "alert_id": (
                    packet_failure["alert"].id
                    if packet_failure["alert"]
                    else None
                ),
                "failure_count": (
                    packet_failure["failure_count"]
                ),
            }

    return result



def sync_high_latency_alert(
    target,
    latency_ms,
    device=None,
):
    """
    مدیریت Incident مربوط به High Latency.

    وضعیت‌ها:

        latency < 200ms
            -> healthy / resolve

        200ms <= latency < 500ms
            -> degraded / warning

        latency >= 500ms
            -> degraded / critical

    نکته:
        High Latency زمانی بررسی می‌شود که Ping موفق باشد.
        Ping ناموفق توسط internet_down یا device_down مدیریت می‌شود.
    """

    if latency_ms is None:
        return None

    alert_key = f"latency:{target}"

    # ---------------------------------------------------------
    # Latency طبیعی
    # ---------------------------------------------------------

    if latency_ms < HIGH_LATENCY_WARNING_MS:

        resolved_alert = resolve_alert(
            alert_key=alert_key,
            message=(
                f"Latency to {target} returned to normal. "
                f"Current latency: {latency_ms} ms."
            ),
        )

        return {
            "alert": resolved_alert,
            "status": "resolved" if resolved_alert else "healthy",
        }

    # ---------------------------------------------------------
    # Latency بالا
    # ---------------------------------------------------------

    if latency_ms >= HIGH_LATENCY_CRITICAL_MS:

        severity = "critical"

    else:

        severity = "warning"

    alert, created = raise_alert(
        alert_key=alert_key,
        alert_type="high_latency",
        severity=severity,
        status="degraded",
        device=device,
        title=f"High latency to {target}",
        message=(
            f"Latency to {target} is {latency_ms} ms. "
            f"Warning threshold: "
            f"{HIGH_LATENCY_WARNING_MS} ms."
        ),
    )

    return {
        "alert": alert,
        "status": "degraded",
        "severity": severity,
        "created": created,
        "latency_ms": latency_ms,
    }


def get_packet_loss_for_target(
    target,
    device=None,
    sample_size=10,
):
    """
    محاسبه Packet Loss از آخرین Pingهای Target.
    """

    queryset = Ping.objects.filter(
        target=target,
    )

    if device is not None:
        queryset = queryset.filter(
            device=device,
        )

    recent_pings = list(
        queryset.order_by("-created_at")[:sample_size]
    )

    if not recent_pings:
        return None

    failed = sum(
        1
        for ping in recent_pings
        if not ping.success
    )

    return round(
        (failed / len(recent_pings)) * 100,
        1,
    )



def sync_packet_loss_alert(
    target,
    device=None,
):
    """
    مدیریت Incident مربوط به Packet Loss.

    کمتر از 10%:
        Normal

    بین 10% تا 30%:
        Degraded / Warning

    بیشتر یا مساوی 30%:
        Degraded / Critical

    Packet Loss به تنهایی باعث Down شدن سرویس نمی‌شود.
    """

    packet_loss = get_packet_loss_for_target(
        target=target,
        device=device,
    )

    if packet_loss is None:
        return None

    alert_key = f"packet_loss:{target}"

    # ---------------------------------------------------------
    # Packet Loss طبیعی
    # ---------------------------------------------------------

    if packet_loss < PACKET_LOSS_WARNING_PERCENT:

        resolved_alert = resolve_alert(
            alert_key=alert_key,
            message=(
                f"Packet loss to {target} returned to normal. "
            ),
        )

        return {
            "alert": resolved_alert,
            "status": "resolved" if resolved_alert else "healthy",
            "packet_loss": packet_loss,
        }

    # ---------------------------------------------------------
    # تعیین Severity
    # ---------------------------------------------------------

    if packet_loss >= PACKET_LOSS_CRITICAL_PERCENT:

        severity = "critical"

    else:

        severity = "warning"

    # ---------------------------------------------------------
    # ایجاد / بروزرسانی Incident
    # ---------------------------------------------------------

    alert, created = raise_alert(
        alert_key=alert_key,
        alert_type="packet_loss",
        severity=severity,
        status="degraded",
        device=device,
        title=f"Packet loss detected for {target}",
        message=(
            f"Packet loss to {target} is "
            f"{packet_loss}%. "
            f"Warning threshold: "
            f"{PACKET_LOSS_WARNING_PERCENT}%."
        ),
    )

    return {
        "alert": alert,
        "status": "degraded",
        "severity": severity,
        "created": created,
        "packet_loss": packet_loss,
    }


# --------------------------------------------------------------------------
# Dashboard / live ping API
# --------------------------------------------------------------------------

@login_required
def network_logs_api(request):
    logs = []

    pings = Ping.objects.all().order_by("-created_at")[:15]

    for ping in pings:
        local_time = timezone.localtime(ping.created_at)

        if ping.success:
            level = "INFO"
            message = (
                f" Ping to {ping.target} successful - "
                f"{ping.latency_ms} ms"
            )
        else:
            level = "WARNING"
            message = (
                f" Ping to {ping.target} failed - "
                f"{ping.message}"
            )

        logs.append({
            "timestamp": ping.created_at.timestamp(),
            "time": local_time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        })

    alerts = Alert.objects.all().order_by("-created_at")[:15]

    for alert in alerts:
        local_time = timezone.localtime(alert.created_at)

        logs.append({
            "timestamp": alert.created_at.timestamp(),
            "time": local_time.strftime("%H:%M:%S"),
            "level": alert.severity.upper(),
            "message": alert.title,
        })

    logs.sort(
        key=lambda x: x["timestamp"],
        reverse=True
    )

    logs = logs[:20]

    return JsonResponse({
        "logs": logs
    })


@login_required
def dashboard_view(request):
    online_devices = Device.objects.filter(is_online=True)
    open_alerts = Alert.objects.filter(is_resolved=False)
    critical_alert_count = open_alerts.filter(severity="critical").count()
    all_alerts = Alert.objects.all().order_by("-created_at")[:5]

    recent_pings = list(Ping.objects.all().order_by("-created_at")[:10])
    last_pings = Ping.objects.all().order_by("-created_at")[:7]

    sample_size = len(recent_pings)
    failed = sum(1 for p in recent_pings if not p.success)

    packet_loss = (
        round((failed / sample_size) * 100, 1)
        if sample_size
        else 0
    )

    availability = round(100 - packet_loss,1)

    successful_latencies = [
        p.latency_ms
        for p in recent_pings
        if p.success and p.latency_ms is not None
    ]

    latest_latency = (
        successful_latencies[0]
        if successful_latencies
        else None
    )

    gateway_ip = get_default_gateway()

    settings_obj = SystemSettings.load()

    services = run_service_checks(
        gateway_ip,
        settings_obj
    )

    health_score = calculate_health_score(
        availability=availability,
        packet_loss=packet_loss,
        latency_ms=latest_latency,
        services=services,
    )

    trend = list(reversed(recent_pings))

    latencies = [
        p.latency_ms
        for p in trend
        if p.success and p.latency_ms is not None
    ]

    max_latency = max(latencies) if latencies else 1
    if max_latency < 1:
        max_latency = 1

    trend_bars = []

    for p in trend:
        if p.success and p.latency_ms is not None:
            height_percent = round(
                (p.latency_ms / max_latency) * 100
            )
        else:
            height_percent = 4

        trend_bars.append({
            "latency_ms": p.latency_ms if p.latency_ms is not None else 0,
            "height_percent": height_percent,
            "success": p.success,
        })

    settings_obj = SystemSettings.load()

    context = {
        "devices": online_devices,
        "device_count": online_devices.count(),
        "open_alert_count": open_alerts.count(),
        "critical_alert_count": critical_alert_count,
        "recent_alerts": all_alerts,
        "health_score" : health_score,
        "availability": availability,
        "latest_latency" : latest_latency,
        "services": services,
        "trend_bars": trend_bars,
        "last_pings": last_pings,
        "packet_loss": packet_loss,
        "poll_interval_ms": settings_obj.poll_interval_seconds * 1000,
    }

    return render(request, "dashboard.html", context)

def ping_api(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "latency": None, "message": "Authentication required"},
            status=401,
        )

    # TODO:
    # 1.target should possible to change in templates(settings)
    # 2.instead of device = None its should be a device for example : 192.168.120.1 or device id
    # target = request.GET.get("target", "8.8.8.8")
    target = SystemSettings.objects.all().first().ping_target
    device = None
    device_id = request.GET.get("device_id")
    if device_id:
        device = Device.objects.filter(pk=device_id).first()

    result = record_ping(target, user=request.user, device=device)
    return JsonResponse(result)

def sync_service_alert(service):
    """
    وضعیت یک Service را با سیستم Incident/Alert هماهنگ می‌کند.

    status سرویس در services.py:
        success -> سرویس سالم
        warning -> سرویس Degraded
        danger  -> سرویس Down

    وضعیت Alert:
        success -> resolve
        warning -> degraded
        danger  -> down

    برای هر Service یک alert_key مستقل داریم.
    """

    service_name = service.get("name")

    if not service_name:
        return None

    service_status = service.get("status")
    success = service.get("success", False)
    latency_ms = service.get("latency_ms")
    message = service.get("message", "")

    # ---------------------------------------------------------
    # Alert key
    # ---------------------------------------------------------

    alert_key = f"service:{service_name}"

    # ---------------------------------------------------------
    # Service سالم
    # ---------------------------------------------------------

    if success and service_status == "success":

        resolved_alert = resolve_alert(
            alert_key=alert_key,
            message=(
                f"{service_name} recovered successfully."
                + (
                    f" Current latency: {latency_ms} ms."
                    if latency_ms is not None
                    else ""
                )
            ),
        )

        return {
            "alert": resolved_alert,
            "status": "resolved" if resolved_alert else "healthy",
        }

    # ---------------------------------------------------------
    # Service Degraded
    # ---------------------------------------------------------

    if service_status == "warning":

        alert, created = raise_alert(
            alert_key=alert_key,
            alert_type="service_down",
            severity="warning",
            status="degraded",
            title=f"{service_name} degraded",
            message=(
                f"{service_name} is responding slower than expected. "
                f"{message}"
                + (
                    f" Latency: {latency_ms} ms."
                    if latency_ms is not None
                    else ""
                )
            ),
        )

        return {
            "alert": alert,
            "status": "degraded",
            "created": created,
        }

    # ---------------------------------------------------------
    # Service Down
    # ---------------------------------------------------------

    if service_status == "danger" or not success:

        alert, created = raise_alert(
            alert_key=alert_key,
            alert_type="service_down",
            severity="critical",
            status="down",
            title=f"{service_name} is down",
            message=(
                f"{service_name} is unavailable. "
                f"{message}"
            ),
        )

        return {
            "alert": alert,
            "status": "down",
            "created": created,
        }

    return None


@login_required
def services_api(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "success": False,
                "message": "Authentication required"
            },
            status=401
        )

    settings_obj = SystemSettings.load()

    gateway_ip = get_default_gateway()

    services = run_service_checks(
        gateway_ip,
        settings_obj
    )

    process_service_alerts(
        services
    )

    return JsonResponse({
        "services": services
    })


# --------------------------------------------------------------------------
# Devices
# --------------------------------------------------------------------------

@login_required
def devices_view(request):
    devices = Device.objects.all()
    return render(request, "devices/list.html", {"devices": devices})


@login_required
def devices_scan_view(request):
    ok, error = sync_devices()
    if ok:
        messages.success(request, "اسکن شبکه با موفقیت انجام شد.")
    else:
        messages.warning(
            request,
            f"اسکن شبکه ممکن نشد ({error}). دستگاه‌های شناخته‌شده قبلی نمایش داده می‌شوند.",
        )
    return redirect("devices")


@login_required
def device_detail_view(request, device_id):
    device = get_object_or_404(Device, pk=device_id)
    ping_history = device.pings.all()[:20]
    return render(
        request,
        "devices/detail.html",
        {"device": device, "ping_history": ping_history},
    )


# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------

def process_service_alerts(services):
    """
    وضعیت Serviceها را بررسی کرده و Alertهای مربوطه را
    با استفاده از Hysteresis Engine مدیریت می‌کند.
    """

    settings_obj = SystemSettings.load()

    failure_threshold = (
        settings_obj.failure_threshold
        if settings_obj.hysteresis_enabled
        else 1
    )

    recovery_threshold = (
        settings_obj.recovery_threshold
        if settings_obj.hysteresis_enabled
        else 1
    )

    results = []

    for service in services:

        name = service.get("name")

        success = service.get("success", False)

        latency = service.get("latency_ms")

        message = service.get(
            "message",
            "",
        )

        if not name:
            continue

        alert_key = f"service:{name}"

        # ======================================================
        # Service DOWN
        # ======================================================

        if not success:

            result = process_failure(
                alert_key=alert_key,
                alert_type="service_down",
                title=f"{name} service is down",
                message=(
                    f"{name} check failed: "
                    f"{message}"
                ),
                severity="critical",
                status="down",
                failure_threshold=failure_threshold,
                value=None,
            )

        # ======================================================
        # Service DEGRADED
        # ======================================================

        elif service.get("status") == "warning":

            result = process_failure(
                alert_key=alert_key,
                alert_type="service_down",
                title=f"{name} service is degraded",
                message=(
                    f"{name} is responding slowly. "
                    f"Latency: {latency} ms."
                ),
                severity="warning",
                status="degraded",
                failure_threshold=failure_threshold,
                value=latency,
            )

        # ======================================================
        # Service HEALTHY
        # ======================================================

        else:

            recovery = process_recovery(
                alert_key=alert_key,
                recovery_threshold=recovery_threshold,
                recovery_message=(
                    f"{name} service has recovered."
                ),
            )

            result = {
                "alert": recovery["alert"],
                "resolved": recovery["resolved"],
                "recovery_count": recovery[
                    "recovery_count"
                ],
            }

        results.append({
            "service": name,
            "result": result,
        })

    return results


@login_required
def alerts_view(request):
    severity = request.GET.get("severity", "").strip().lower()

    valid_severities = {
        choice[0]
        for choice in Alert.SEVERITY_CHOICES
    }

    if severity not in valid_severities:
        severity = ""


    alerts_qs = (
        Alert.objects
        .select_related("device")
        .all()
    )

    if severity:
        alerts_qs = alerts_qs.filter(
            severity=severity
        )

    alerts_qs = alerts_qs.order_by(
        "-last_seen_at",
        "-created_at",
    )

    total_alert_count = Alert.objects.count()

    active_alert_count = Alert.objects.filter(
        is_resolved=False
    ).count()

    alerts = alerts_qs[:200]

    context = {
        "alerts": alerts,
        "severity": severity,

        "total_alert_count": total_alert_count,
        "active_alert_count": active_alert_count,
    }

    return render(
        request,
        "alerts/list.html",
        context,
    )

@login_required
def alert_detail_view(request, alert_id):
    alert = get_object_or_404(Alert, pk=alert_id)
    if request.method == "POST" and request.POST.get("action") == "resolve":
        alert.resolve()
        messages.success(request, "هشدار به‌عنوان رفع‌شده ثبت شد.")
        return redirect("alert_detail", alert_id=alert.id)
    return render(request, "alerts/detail.html", {"alert": alert})


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------

@login_required
def reports_view(request):
    return render(request, "reports/list.html")


@login_required
def report_detail_view(request, period):
    days = PERIOD_DAYS.get(period, 1)
    since = timezone.now() - timedelta(days=days)

    pings_in_period = Ping.objects.filter(created_at__gte=since)
    total = pings_in_period.count()
    successful = pings_in_period.filter(success=True)
    availability = round((successful.count() / total) * 100, 1) if total else None

    avg_latency = successful.aggregate(avg=Avg("latency_ms"))["avg"]
    avg_latency = round(avg_latency, 1) if avg_latency is not None else None

    alert_count = Alert.objects.filter(created_at__gte=since).count()

    context = {
        "period": period,
        "period_label": PERIOD_LABELS.get(period, period),
        "availability": availability,
        "avg_latency": avg_latency,
        "alert_count": alert_count,
        "sample_size": total,
    }
    return render(request, "reports/detail.html", context)


@login_required
def report_csv_view(request, period):
    """Export the raw Ping rows for a report period as CSV (opens fine in
    Excel/Sheets). There's no PDF/template-report generator in this project,
    so this replaces the previously dead 'Download PDF/Excel' links with one
    real export instead of leaving them as non-functional placeholders."""
    days = PERIOD_DAYS.get(period, 1)
    since = timezone.now() - timedelta(days=days)
    pings_in_period = Ping.objects.filter(created_at__gte=since).order_by("created_at")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="report-{period}.csv"'
    writer = csv.writer(response)
    writer.writerow(["target", "success", "latency_ms", "message", "created_at"])
    for p in pings_in_period:
        writer.writerow([p.target, p.success, p.latency_ms, p.message, p.created_at.isoformat()])
    return response


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

@login_required
def dns_lookup_view(request):
    """DNS lookup tool: a hostname runs forward lookups across the common
    record types (A, AAAA, CNAME, MX, NS, TXT, SOA); an IP address runs a
    reverse (PTR) lookup instead. dns_lookup() decides which from the
    shape of the input, so this view just passes the query through and
    renders whichever result comes back."""
    query = request.GET.get("q", "").strip()
    lookup_result = dns_lookup(query) if query else None
    return render(
        request,
        "tools/dns_lookup.html",
        {"query": query, "lookup_result": lookup_result},
    )


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

@login_required
def settings_view(request):

    settings_obj = SystemSettings.load()

    if request.method == "POST":

        # ======================================================
        # General
        # ======================================================

        settings_obj.site_name = (
            request.POST.get("site_name", "").strip()
            or settings_obj.site_name
        )

        settings_obj.timezone_name = (
            request.POST.get(
                "timezone_name",
                settings_obj.timezone_name
            )
        )

        try:
            settings_obj.poll_interval_seconds = max(
                5,
                int(
                    request.POST.get(
                        "poll_interval_seconds",
                        settings_obj.poll_interval_seconds
                    )
                )
            )
        except (TypeError, ValueError):
            pass

        settings_obj.scan_subnet = (
            request.POST.get(
                "scan_subnet",
                ""
            ).strip()
            or settings_obj.scan_subnet
        )

        # ======================================================
        # Service Monitoring
        # ======================================================

        dns_hostname = request.POST.get(
            "dns_hostname",
            ""
        ).strip()

        web_url = request.POST.get(
            "web_url",
            ""
        ).strip()

        tcp_host = request.POST.get(
            "tcp_host",
            ""
        ).strip()

        if dns_hostname:
            settings_obj.dns_hostname = dns_hostname

        if web_url:
            settings_obj.web_url = web_url

        if tcp_host:
            settings_obj.tcp_host = tcp_host

        try:
            tcp_port = int(
                request.POST.get(
                    "tcp_port",
                    settings_obj.tcp_port
                )
            )

            if 1 <= tcp_port <= 65535:
                settings_obj.tcp_port = tcp_port

        except (TypeError, ValueError):
            pass

        # ======================================================
        # Hysteresis
        # ======================================================

        settings_obj.hysteresis_enabled = (
            request.POST.get("hysteresis_enabled")
            == "on"
        )

        try:
            settings_obj.failure_threshold = max(
                1,
                int(
                    request.POST.get(
                        "failure_threshold",
                        settings_obj.failure_threshold
                    )
                )
            )
        except (TypeError, ValueError):
            pass

        try:
            settings_obj.recovery_threshold = max(
                1,
                int(
                    request.POST.get(
                        "recovery_threshold",
                        settings_obj.recovery_threshold
                    )
                )
            )
        except (TypeError, ValueError):
            pass


        try:
            settings_obj.high_latency_warning_ms = max(
                1,
                float(
                    request.POST.get(
                        "high_latency_warning_ms",
                        settings_obj.high_latency_warning_ms
                    )
                )
            )
        except (TypeError, ValueError):
            pass

        try:
            settings_obj.packet_loss_warning_percent = min(
                100,
                max(
                    0,
                    float(
                        request.POST.get(
                            "packet_loss_warning_percent",
                            settings_obj.packet_loss_warning_percent
                        )
                    )
                )
            )
        except (TypeError, ValueError):
            pass

        settings_obj.save()

        messages.success(
            request,
            "تنظیمات با موفقیت ذخیره شد."
        )

        return redirect("settings")

    return render(
        request,
        "settings/general.html",
        {
            "settings": settings_obj
        }
    )

@login_required
def settings_notifications_view(request):
    settings_obj = SystemSettings.load()
    if request.method == "POST":
        settings_obj.notify_email = bool(request.POST.get("notify_email"))
        settings_obj.notify_in_app = bool(request.POST.get("notify_in_app"))
        settings_obj.notify_on_critical = bool(request.POST.get("notify_on_critical"))
        settings_obj.save()
        messages.success(request, "تنظیمات اعلان‌ها ذخیره شد.")
        return redirect("settings_notifications")
    return render(request, "settings/notifications.html", {"settings": settings_obj})


@login_required
def settings_ping_view(request):
    ping_obj = SystemSettings.load()
    if request.method == "POST":
        ping_obj.ping_target = str(request.POST.get("ping_target"))
        ping_obj.save()
        messages.success(request, "تنظیمات پینگ ذخیره شد.")
        return redirect("settings_ping")
    return render(request, "settings/ping.html", {"ping": ping_obj})
