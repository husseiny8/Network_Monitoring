from django.urls import path

from monitor.views import (
    alert_detail_view,
    alerts_view,
    bandwidth_api,
    dashboard_view,
    device_detail_view,
    device_snmp_check_view,
    devices_scan_view,
    devices_view,
    dns_lookup_view,
    latency_history_api,
    ping_api,
    report_csv_view,
    report_detail_view,
    reports_view,
    network_logs_api,
    services_api,
    settings_notifications_view,
    settings_view,
    settings_ping_view,
    topology_api,
    topology_view,
)

urlpatterns = [
    path("", dashboard_view, name="dashboard"),
    path("api/ping/", ping_api, name="ping_api"),
    path("api/services/", services_api, name="services_api"),
    path("api/latency-history/", latency_history_api, name="latency_history_api"),
    path("api/bandwidth/", bandwidth_api, name="bandwidth_api"),
    path("api/network-logs/", network_logs_api, name="network_logs_api"),

    path("settings", settings_view, name="settings"),
    path("settings/notifications", settings_notifications_view, name="settings_notifications"),
    path("settings/ping", settings_ping_view, name="settings_ping"),

    path("devices", devices_view, name="devices"),
    path("devices/scan", devices_scan_view, name="devices_scan"),
    path("devices/<int:device_id>", device_detail_view, name="device_detail"),
    path("devices/<int:device_id>/snmp-check", device_snmp_check_view, name="device_snmp_check"),

    path("topology", topology_view, name="topology"),
    path("api/topology/", topology_api, name="topology_api"),

    path("alerts", alerts_view, name="alerts"),
    path("alerts/<int:alert_id>", alert_detail_view, name="alert_detail"),

    path("reports", reports_view, name="reports"),
    path("reports/<str:period>", report_detail_view, name="report_detail"),
    path("reports/<str:period>/export.csv", report_csv_view, name="report_csv"),

    path("dns-lookup", dns_lookup_view, name="dns_lookup"),
]
