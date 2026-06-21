"""
Background monitoring loop.

This is the "always on" counterpart to the dashboard's live ping and the
devices page's "scan now" button: those only collect data while someone
has the page open / clicks the button. Run this as a long-lived process
(systemd service, Docker container, `screen`/`tmux` session, etc.) or on a
schedule (cron, `--once` + a timer) to keep Ping/Device/Alert history
populated continuously.

It deliberately reuses monitor.views.sync_devices()/record_ping() instead
of re-implementing the persistence + alerting logic, so the web UI and
this command always agree on what counts as "online" or "alert-worthy".

Examples
--------
Run forever, using the interval configured on the Settings page:
    python manage.py run_monitor

Run a single check-and-scan cycle and exit (e.g. from cron):
    python manage.py run_monitor --once

Override the ping target and the polling interval:
    python manage.py run_monitor --target 1.1.1.1 --interval 60
"""

import time

from django.core.management.base import BaseCommand

from monitor.models import SystemSettings
from monitor.views import record_ping, sync_devices


class Command(BaseCommand):
    help = "Continuously (or once) ping a target and scan the network, persisting results."

    def add_arguments(self, parser):
        parser.add_argument(
            "--target",
            default="8.8.8.8",
            help="Host to ping each cycle (default: 8.8.8.8).",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=None,
            help="Seconds between cycles. Defaults to the Settings page's "
            "poll interval (SystemSettings.poll_interval_seconds).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run a single ping + scan cycle and exit, instead of looping forever.",
        )
        parser.add_argument(
            "--skip-scan",
            action="store_true",
            help="Only ping; skip the ARP network scan (useful without raw-socket privileges).",
        )

    def handle(self, *args, **options):
        target = options["target"]
        once = options["once"]
        skip_scan = options["skip_scan"]
        interval = options["interval"] or SystemSettings.load().poll_interval_seconds

        self.stdout.write(self.style.SUCCESS(
            f"Starting monitor: target={target} interval={interval}s "
            f"scan={'off' if skip_scan else 'on'} mode={'once' if once else 'loop'}"
        ))

        try:
            while True:
                self._run_cycle(target, skip_scan)
                if once:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Stopped."))

    def _run_cycle(self, target, skip_scan):
        result = record_ping(target)
        if result["success"]:
            self.stdout.write(f"ping {target}: OK ({result['latency']} ms)")
        else:
            self.stdout.write(self.style.WARNING(f"ping {target}: FAILED ({result['message']})"))

        if not skip_scan:
            ok, error = sync_devices()
            if ok:
                self.stdout.write("network scan: OK")
            else:
                self.stdout.write(self.style.WARNING(f"network scan: skipped ({error})"))
