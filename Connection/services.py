import socket
import time
import urllib.error
import urllib.request
import ping3
from django.db import connection as db_connection
from django.db.utils import Error as DatabaseError

DNS_HOSTNAME = "google.com"
WEB_URL = "https://www.google.com"

DEGRADED_THRESHOLD_MS = {
    "DNS": 200,
    "Web Server": 1000,
    "Database": 100,
    "Gateway": 50,
}


def _classify(name, success, latency_ms):
    if not success:
        return "danger"
    threshold = DEGRADED_THRESHOLD_MS.get(name)
    if threshold is not None and latency_ms is not None and latency_ms > threshold:
        return "warning"
    return "success"


def _result(name, success, latency_ms, message):
    return {
        "name": name,
        "status": _classify(name, success, latency_ms),
        "success": success,
        "latency_ms": latency_ms,
        "message": message,
    }


def check_dns(hostname=DNS_HOSTNAME, timeout=3):
    start = time.monotonic()
    try:
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname(hostname)
    except OSError as exc:
        return _result("DNS", False, None, str(exc))
    finally:
        socket.setdefaulttimeout(None)
    latency_ms = round((time.monotonic() - start) * 1000, 1)
    return _result("DNS", True, latency_ms, "OK")

# sub with HTTP
def check_web(url=WEB_URL, timeout=4):
    start = time.monotonic()
    try:
        urllib.request.urlopen(url, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return _result("Web Server", False, None, str(exc))
    latency_ms = round((time.monotonic() - start) * 1000, 1)
    return _result("Web Server", True, latency_ms, "OK")

# sub with TCP
def check_database():
    start = time.monotonic()
    try:
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as exc:
        return _result("Database", False, None, str(exc))
    latency_ms = round((time.monotonic() - start) * 1000, 1)
    return _result("Database", True, latency_ms, "OK")


def gateway_ip_from_subnet(scan_subnet):
    """Best-effort: treat the IP portion of the configured scan subnet
    (SystemSettings.scan_subnet, e.g. "192.168.1.1/24") as the LAN
    gateway address - there's no dedicated gateway field, and routers
    conventionally sit at the base address of their subnet."""
    if not scan_subnet:
        return None
    return scan_subnet.split("/")[0].strip() or None


def check_gateway(gateway_ip, timeout=2):
    if not gateway_ip:
        return _result("Gateway", False, None, "No gateway configured")
    try:
        ping_time = ping3.ping(gateway_ip, timeout=timeout)
    except Exception as exc:
        return _result("Gateway", False, None, str(exc))
    if ping_time is None:
        return _result("Gateway", False, None, "Timeout")
    return _result("Gateway", True, round(ping_time * 1000, 1), "OK")


def run_all(gateway_ip):
    return [
        check_dns(),
        check_web(),
        check_database(),
        check_gateway(gateway_ip),
    ]
