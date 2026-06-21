from django.conf import settings
from django.db import models
from django.utils import timezone


class Device(models.Model):
    """A host discovered on the local network via an ARP scan (or added manually)."""

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
        """Failed-ping percentage over this device's most recent samples."""
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
    """A single latency-check result, optionally tied to the user who triggered it
    and/or a known Device. This is the persisted version of the model that was
    sketched out (commented-out) in the original monitor/models.py."""

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


class Alert(models.Model):
    SEVERITY_CHOICES = [
        ("critical", "Critical"),
        ("warning", "Warning"),
        ("info", "Info"),
    ]

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alerts",
    )
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="info")
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True, default="")
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def resolve(self):
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.save(update_fields=["is_resolved", "resolved_at"])

    @property
    def badge_class(self):
        # alert-card uses "critical/warning/info", badge uses "danger/warning/info"
        return "danger" if self.severity == "critical" else self.severity


class SystemSettings(models.Model):
    """Singleton-style row holding the system/notification settings shown on the
    Settings pages. Use SystemSettings.load() to get-or-create the single row."""

    site_name = models.CharField(max_length=100, default="Network Monitor")
    timezone_name = models.CharField(max_length=50, default="Asia/Tehran")
    poll_interval_seconds = models.PositiveIntegerField(default=30)
    description = models.TextField(blank=True, default="")
    scan_subnet = models.CharField(max_length=50, default="192.168.1.1/24")

    notify_email = models.BooleanField(default=True)
    notify_in_app = models.BooleanField(default=True)
    notify_on_critical = models.BooleanField(default=True)

    class Meta:
        verbose_name = "System settings"
        verbose_name_plural = "System settings"

    def __str__(self):
        return "System settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
