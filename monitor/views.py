import csv
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from Connection.ping import ping_and_store
from Connection.health import calculate_health_score
from Connection.services import gateway_ip_from_subnet,get_default_gateway, run_all as run_service_checks
from Devices import device as device_scanner
from .models import Alert, Device, Ping, SystemSettings
from .alert_manager import raise_alert,resolve_alert

PERIOD_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}
PERIOD_LABELS = {
    "daily": "گزارش روزانه",
    "weekly": "گزارش هفتگی",
    "monthly": "گزارش ماهانه",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def sync_devices(subnet=None):
    """Run an ARP scan and reconcile the results into the Device table,
    raising Alert rows for devices that go offline/come back online.

    Device alert behavior:
        ONLINE -> OFFLINE:
            Create one device_down alert.

        OFFLINE -> OFFLINE:
            Keep the same alert open and increase occurrence_count.

        OFFLINE -> ONLINE:
            Resolve the device_down alert.
            Create a "back online" info alert.
    """
    if subnet is None:
        subnet = SystemSettings.load().scan_subnet

    try:
        found = device_scanner.scan(subnet)
    except Exception as exc:
        return False, str(exc)

    found_by_ip = {item["ip"]: item.get("mac", "") for item in found}
    existing_by_ip = {d.ip_address: d for d in Device.objects.all()}

    for ip, mac in found_by_ip.items():
        existing = existing_by_ip.get(ip)
        if existing:
            was_offline = not existing.is_online
            existing.mac_address = mac or existing.mac_address
            existing.is_online = True
            existing.save()
            if was_offline:
                raise_alert(
                    alert_type="device_restored",
                    device=existing,
                    severity="info",
                    title=f"{existing.display_name} is back online",
                    message=f"{existing.ip_address} responded to the latest network scan.",
                )
        else:
            Device.objects.create(ip_address=ip, mac_address=mac, is_online=True)

    for ip, existing in existing_by_ip.items():
        if ip not in found_by_ip and existing.is_online:
            existing.is_online = False
            existing.save()
            raise_alert(
                alert_type="device_restored",
                device=existing,
                severity="critical",
                title=f"{existing.display_name} disconnected",
                message=f"{existing.ip_address} did not respond to the latest network scan.",
            )

    return True, None

def record_ping(target, user=None, device=None):
    """Ping `target`, persist it, and keep a single open "connectivity lost"
    alert in sync (opened on first failure, resolved + logged on recovery)
    instead of creating one alert per failed ping."""

    target = SystemSettings.objects.all().first().ping_target
    result = ping_and_store(target, user=user, device=device)

    open_alert = Alert.objects.filter(
        title="Internet connectivity lost",
        is_resolved=False
    ).first()

    if not result["success"]:
        if not open_alert:
            raise_alert(
                alert_type="internet_down",
                severity="critical",
                device=None,
                title="Internet connectivity lost",
                message=f"Ping to {target} failed: {result['message']}",
            )
    elif open_alert:
        open_alert.resolve()
        raise_alert(
            alert_type="internet_restored",
            device=None,
            severity="info",
            title="Internet connectivity restored",
            message=f"Ping to {target} succeeded again ({result['latency']} ms).",
        )

    return result


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

    services = run_service_checks(gateway_ip)

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


def services_api(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Authentication required"}, status=401
        )

    gateway_ip = get_default_gateway()
    services = run_service_checks(gateway_ip)
    return JsonResponse({"services": services})


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

@login_required
def alerts_view(request):
    alerts = Alert.objects.all()
    severity = request.GET.get("severity")
    if severity in dict(Alert.SEVERITY_CHOICES):
        alerts = alerts.filter(severity=severity)
    alerts = alerts[:200]
    return render(request, "alerts/list.html", {"alerts": alerts, "severity": severity})


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
# Settings
# --------------------------------------------------------------------------

@login_required
def settings_view(request):
    settings_obj = SystemSettings.load()
    if request.method == "POST":
        settings_obj.site_name = request.POST.get("site_name", "").strip() or settings_obj.site_name
        settings_obj.timezone_name = request.POST.get("timezone_name", settings_obj.timezone_name)
        try:
            settings_obj.poll_interval_seconds = max(
                5, int(request.POST.get("poll_interval_seconds", settings_obj.poll_interval_seconds))
            )
        except (TypeError, ValueError):
            pass
        settings_obj.scan_subnet = request.POST.get("scan_subnet", "").strip() or settings_obj.scan_subnet
        settings_obj.save()
        messages.success(request, "تنظیمات با موفقیت ذخیره شد.")
        return redirect("settings")
    return render(request, "settings/general.html", {"settings": settings_obj})


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
