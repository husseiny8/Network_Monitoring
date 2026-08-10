from django.urls import path

from monitor.views import (
    alert_detail_view,
    alerts_view,
    dashboard_view,
    device_detail_view,
    devices_scan_view,
    devices_view,
    ping_api,
    report_csv_view,
    report_detail_view,
    reports_view,
    network_logs_api,
    services_api,
    settings_notifications_view,
    settings_view,
    settings_ping_view,
)

urlpatterns = [
    path("", dashboard_view, name="dashboard"),
    path("api/ping/", ping_api, name="ping_api"),
    path("api/services/", services_api, name="services_api"),

    path("settings", settings_view, name="settings"),
    path("settings/notifications", settings_notifications_view, name="settings_notifications"),
    path("settings/ping", settings_ping_view, name="settings_ping"),
    path(
    "api/network-logs/", network_logs_api, name="network_logs_api"),
    path("devices", devices_view, name="devices"),
    path("devices/scan", devices_scan_view, name="devices_scan"),
    path("devices/<int:device_id>", device_detail_view, name="device_detail"),

    path("alerts", alerts_view, name="alerts"),
    path("alerts/<int:alert_id>", alert_detail_view, name="alert_detail"),

    path("reports", reports_view, name="reports"),
    path("reports/<str:period>", report_detail_view, name="report_detail"),
    path("reports/<str:period>/export.csv", report_csv_view, name="report_csv"),
]
