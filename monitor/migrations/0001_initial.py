import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Device",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ip_address", models.GenericIPAddressField(unique=True)),
                ("mac_address", models.CharField(blank=True, default="", max_length=17)),
                ("name", models.CharField(blank=True, default="", max_length=100)),
                ("device_type", models.CharField(blank=True, default="Unknown", max_length=50)),
                ("is_online", models.BooleanField(default=True)),
                ("first_seen", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["ip_address"],
            },
        ),
        migrations.CreateModel(
            name="SystemSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("site_name", models.CharField(default="Network Monitor", max_length=100)),
                ("timezone_name", models.CharField(default="Asia/Tehran", max_length=50)),
                ("poll_interval_seconds", models.PositiveIntegerField(default=30)),
                ("description", models.TextField(blank=True, default="")),
                ("scan_subnet", models.CharField(default="192.168.1.1/24", max_length=50)),
                ("notify_email", models.BooleanField(default=True)),
                ("notify_in_app", models.BooleanField(default=True)),
                ("notify_on_critical", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "System settings",
                "verbose_name_plural": "System settings",
            },
        ),
        migrations.CreateModel(
            name="Alert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("severity", models.CharField(choices=[("critical", "Critical"), ("warning", "Warning"), ("info", "Info")], default="info", max_length=10)),
                ("title", models.CharField(max_length=200)),
                ("message", models.TextField(blank=True, default="")),
                ("is_resolved", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("device", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="alerts", to="monitor.device")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Ping",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target", models.CharField(default="8.8.8.8", max_length=100)),
                ("success", models.BooleanField(default=False)),
                ("latency_ms", models.FloatField(blank=True, null=True)),
                ("message", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("device", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="pings", to="monitor.device")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="pings", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
