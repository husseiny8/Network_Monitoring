# Network Monitoring

A Django web app for monitoring a local network and internet connectivity: discovers
devices on your LAN, tracks ping/latency history, raises alerts when something goes
down (and resolves them automatically when it comes back), and surfaces all of it on
a dashboard with reports and per-user accounts. UI is in Persian (RTL).

## Features

- **Dashboard** — live latency to a target host (auto-refreshing), open alert count,
  online device count, packet loss, and a recent-latency trend chart.
- **Devices** — ARP-scans your local subnet to discover devices, tracks each one's
  online/offline status and ping history, computes per-device latency/uptime/packet
  loss.
- **Alerts** — auto-created when a device goes offline or the configured ping target
  stops responding, auto-resolved (with a follow-up "restored" alert) when it comes
  back. Filterable by severity, resolvable from the alert detail page.
- **Reports** — daily/weekly/monthly availability, average latency, and alert counts
  computed from stored ping history, with a CSV export of the raw data.
- **Settings** — system name, timezone, poll interval, scan subnet, and notification
  preferences, persisted in the database.
- **Users** — sign up (the first account created becomes an administrator), staff-only
  user management with three roles (Administrator / Operator / Viewer).
- **Background monitoring** — a `run_monitor` management command that keeps pinging
  and re-scanning on a schedule, independent of anyone having the dashboard open.

## Setup

```bash
git clone https://github.com/husseiny8/Network_Monitoring.git
cd Network_Monitoring
python3 -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirement.txt

cp .env.example .env       # optional for local dev; see below
python manage.py migrate
python manage.py runserver
```

Then open `http://127.0.0.1:8000/accounts/signup` and create an account — the
first user created is automatically made an administrator (`is_staff` +
`is_superuser`), so you'll immediately have access to the Users page too. You can
also use `python manage.py createsuperuser` instead if you prefer.

### Environment variables

`Core/settings.py` reads `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, and
`DJANGO_ALLOWED_HOSTS` from the environment, falling back to safe local-dev defaults
if they're not set — see `.env.example`. Set real values (and `DJANGO_DEBUG=False`)
before deploying anywhere reachable by other people.

### A note on network scanning

Device discovery (`Devices/device.py`) sends raw ARP frames via `scapy`, which needs
raw-socket privileges:

- **Linux:** run with `sudo`, or grant the capability once with
  `sudo setcap cap_net_raw+eip $(readlink -f venv/bin/python3)`.
- **Windows:** install [Npcap](https://npcap.com/) and run as Administrator.
- **Containers/CI/no real LAN:** scanning will fail — the app handles that
  gracefully (an alert/message is shown, existing device data is left alone) rather
  than crashing, so the rest of the app still works without it.

### Background monitoring

The dashboard's live ping and the "scan now" button only collect data while
someone's looking at the page. To keep history flowing continuously, run:

```bash
python manage.py run_monitor                  # loop forever, using Settings' poll interval
python manage.py run_monitor --once            # one cycle and exit (e.g. from cron)
python manage.py run_monitor --target 1.1.1.1 --interval 60
python manage.py run_monitor --skip-scan       # ping only, no ARP scan
```

## Project structure

```
Core/         Django project settings, root URLconf
monitor/      Dashboard, devices, alerts, reports, settings - models, views, admin
account/      Login/signup/logout, staff-only user management
Devices/      ARP network scanning (scapy)
Connection/   Ping logic (ping3) + the legacy standalone connectivity logger
templates/    All HTML templates (Persian, RTL)
statics/      CSS/JS/images
```