from django.conf import settings
from django.db import models
from django.utils import timezone


class Device(models.Model):

    ip_address = models.GenericIPAddressField(unique=True)
    mac_address = models.CharField(max_length=17, blank=True, default="")
    name = models.CharField(max_length=100, blank=True, default="")
    device_type = models.CharField(max_length=50, blank=True, default="Unknown")
    is_online = models.BooleanField(default=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ip_address"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.name or self.ip_address

    @property
    def latest_ping(self):
        return self.pings.first()  # Ping.Meta.ordering = ["-created_at"]

    @property
    def latency_ms(self):
        ping = self.latest_ping
        return ping.latency_ms if ping and ping.success else None

    @property
    def packet_loss_percent(self):
        recent = list(self.pings.all()[:20])
        if not recent:
            return None
        failed = sum(1 for p in recent if not p.success)
        return round((failed / len(recent)) * 100, 1)

    @property
    def uptime_percent(self):
        recent = list(self.pings.all()[:50])
        if not recent:
            return None
        ok = sum(1 for p in recent if p.success)
        return round((ok / len(recent)) * 100, 1)


class Ping(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pings",
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pings",
    )
    target = models.CharField(max_length=100, default="8.8.8.8")
    success = models.BooleanField(default=False)
    latency_ms = models.FloatField(null=True, blank=True)
    message = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.success:
            return f"{self.target} - {self.latency_ms} ms"
        return f"{self.target} - {self.message or 'failed'}"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Alert(models.Model):

    ALERT_TYPE_CHOICES = [
        ("internet_down", "Internet"),
        ("device_down", "Device"),
        ("service_down", "Service"),
        ("high_latency", "High Latency"),
        ("packet_loss", "Packet Loss"),
    ]

    SEVERITY_CHOICES = [
        ("critical", "Critical"),
        ("warning", "Warning"),
        ("info", "Info"),
    ]

    STATUS_CHOICES = [
        ("degraded", "Degraded"),
        ("down", "Down"),
        ("resolved", "Resolved"),
    ]


    alert_key = models.CharField(max_length=255,db_index=True,)
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alerts",
    )

    alert_type = models.CharField(max_length=30,choices=ALERT_TYPE_CHOICES,)
    severity = models.CharField(max_length=10,choices=SEVERITY_CHOICES,default="info",)
    status = models.CharField(max_length=20,choices=STATUS_CHOICES,default="down",)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True,default="")
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True,blank=True)
    occurrence_count = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["alert_key"],
                condition=models.Q(is_resolved=False),
                name="unique_open_alert_key",
            )
        ]

    def __str__(self):
        return self.title

    @property
    def duration_seconds(self):

        end_time = self.resolved_at or timezone.now()

        return max(
            0,
            int(
                (end_time - self.created_at).total_seconds()
            )
        )

    @property
    def duration_display(self):

        seconds = self.duration_seconds
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)

        if days:
            return f"{days}d {hours}h"

        if hours:
            return f"{hours}h {minutes}m"

        if minutes:
            return f"{minutes}m {seconds}s"

        return f"{seconds}s"

    def resolve(self, message=None):

        if self.is_resolved:
            return self

        self.is_resolved = True
        self.status = "resolved"
        self.resolved_at = timezone.now()

        if message:
            self.message = message

        self.save(
            update_fields=[
                "is_resolved",
                "status",
                "resolved_at",
                "message",
                "last_seen_at",
            ]
        )

        return self

    @property
    def badge_class(self):
        if self.status == "resolved":
            return "success"

        if self.severity == "critical":
            return "danger"

        if self.severity == "warning":
            return "warning"

        return "info"

class SystemSettings(models.Model):

    site_name = models.CharField(max_length=100,default="Network Monitor")
    timezone_name = models.CharField(max_length=50,default="Asia/Tehran")
    poll_interval_seconds = models.PositiveIntegerField(default=30)
    scan_subnet = models.CharField(max_length=50,default="192.168.1.1/24")
    ping_target = models.CharField(max_length=100,default="8.8.8.8")
    # ==========================================================
    # Service Monitoring
    # ==========================================================

    dns_hostname = models.CharField(max_length=255,default="google.com")
    web_url = models.URLField(max_length=500,default="https://www.google.com")
    tcp_host = models.CharField(max_length=255,default="www.google.com")
    tcp_port = models.PositiveIntegerField(default=443)
    # --------------------------------------------------
    # Notification Settings
    # --------------------------------------------------
    notify_email = models.BooleanField(default=True)
    notify_in_app = models.BooleanField(default=True)
    notify_on_critical = models.BooleanField(default=True)
    # --------------------------------------------------
    # Alert Hysteresis
    # --------------------------------------------------
    hysteresis_enabled = models.BooleanField(default=True,help_text="Enable consecutive failure/recovery confirmation.")
    failure_threshold = models.PositiveIntegerField(default=1,help_text="Number of consecutive failures required to trigger an alert.")
    recovery_threshold = models.PositiveIntegerField(default=1,help_text="Number of consecutive successful checks required to recover an alert.")
    # --------------------------------------------------
    # Packet Loss Thresholds
    # --------------------------------------------------
    packet_loss_warning_percent = models.FloatField(default=10.0,help_text="Packet loss percentage that triggers a warning.")
    packet_loss_critical_percent = models.FloatField(default=30.0,help_text="Packet loss percentage that triggers a critical alert.")
    # --------------------------------------------------
    # Latency Thresholds
    # --------------------------------------------------
    high_latency_warning_ms = models.FloatField(default=200.0,help_text="Latency in milliseconds that triggers a warning.")
    high_latency_critical_ms = models.FloatField(default=500.0,help_text="Latency in milliseconds that triggers a critical alert.")

    class Meta:
        verbose_name = "System settings"
        verbose_name_plural = "System settings"

    def __str__(self):
        return "System settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AlertState(models.Model):

    alert_key = models.CharField(max_length=255,unique=True,db_index=True,)
    consecutive_failures = models.PositiveIntegerField(default=0,)
    consecutive_successes = models.PositiveIntegerField(default=0,)
    last_status = models.CharField(max_length=20,blank=True,default="",)
    last_severity = models.CharField(max_length=10,blank=True,default="",)
    last_value = models.FloatField(null=True,blank=True,)
    last_message = models.TextField(blank=True,default="",)
    updated_at = models.DateTimeField(auto_now=True,)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return (
            f"{self.alert_key} "
            f"(failures={self.consecutive_failures}, "
            f"successes={self.consecutive_successes})"
        )

    def reset_failures(self):
        self.consecutive_failures = 0

    def reset_successes(self):
        self.consecutive_successes = 0