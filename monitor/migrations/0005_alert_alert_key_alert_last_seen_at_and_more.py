# Generated manually to restore the missing migration in the migration chain.

from django.db import migrations, models
import django.db.models.deletion
import django.db.models


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0003_systemsettings_ping_target"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="alert_key",
            field=models.CharField(
                max_length=255,
                db_index=True,
                default="legacy-alert",
            ),
            preserve_default=False,
        ),

        migrations.AddField(
            model_name="alert",
            name="status",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("degraded", "Degraded"),
                    ("down", "Down"),
                    ("resolved", "Resolved"),
                ],
                default="down",
            ),
        ),

        migrations.AddField(
            model_name="alert",
            name="last_seen_at",
            field=models.DateTimeField(
                auto_now=True,
            ),
        ),

        migrations.AddField(
            model_name="alert",
            name="occurrence_count",
            field=models.PositiveIntegerField(
                default=1,
            ),
        ),

        migrations.AlterField(
            model_name="alert",
            name="alert_type",
            field=models.CharField(
                max_length=30,
                choices=[
                    ("internet_down", "Internet"),
                    ("device_down", "Device"),
                    ("service_down", "Service"),
                    ("high_latency", "High Latency"),
                    ("packet_loss", "Packet Loss"),
                ],
                default="internet_down",
            ),
        ),

        migrations.AlterField(
            model_name="alert",
            name="device",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="alerts",
                to="monitor.device",
            ),
        ),

        migrations.AddConstraint(
            model_name="alert",
            constraint=models.UniqueConstraint(
                condition=django.db.models.Q(
                    is_resolved=False
                ),
                fields=("alert_key",),
                name="unique_open_alert_key",
            ),
        ),
    ]