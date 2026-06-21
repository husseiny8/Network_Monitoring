from django.contrib import admin

from .models import Alert, Device, Ping, SystemSettings


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("display_name", "ip_address", "mac_address", "is_online", "last_seen")
    list_filter = ("is_online", "device_type")
    search_fields = ("ip_address", "mac_address", "name")


@admin.register(Ping)
class PingAdmin(admin.ModelAdmin):
    list_display = ("target", "success", "latency_ms", "user", "device", "created_at")
    list_filter = ("success",)
    search_fields = ("target",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("title", "severity", "device", "is_resolved", "created_at")
    list_filter = ("severity", "is_resolved")
    search_fields = ("title", "message")


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ("site_name", "scan_subnet", "poll_interval_seconds")
