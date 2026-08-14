import socket
import time
import platform
import subprocess
import ping3
import requests

DEGRADED_THRESHOLD_MS = {
    "DNS": 200,
    "Web Server": 2000,
    "TCP Port": 300,
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


def check_dns(hostname, port=443, timeout=3):
    start = time.monotonic()
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        return _result("DNS", False, None, str(exc))
    finally:
        socket.setdefaulttimeout(old_timeout)
    latency_ms = round((time.monotonic() - start) * 1000, 1)
    return _result("DNS", True, latency_ms, "OK")


def check_web(url, timeout=4):
    """Full HTTP(S) GET - exercises DNS + TCP + TLS + the actual HTTP
    response, so a failure here with DNS/TCP both green usually means
    the site itself (or its certificate) is the problem."""
    start = time.monotonic()
    try:
        response = requests.get(url, timeout=timeout, allow_redirects=True)
    except requests.Timeout:
        return _result("Web Server", False, None, "Timeout")
    except requests.RequestException as exc:
        return _result("Web Server", False, None, str(exc))
    latency_ms = round((time.monotonic() - start) * 1000, 1)
    success = 200 <= response.status_code < 400
    message = f"HTTP {response.status_code}"
    return _result("Web Server", success, latency_ms if success else None, message)


def check_tcp(host, port, timeout=2):
    """Raw TCP connect with no HTTP/TLS on top. Sits between DNS and Web
    Server: tells you whether a firewall/port block is the issue when
    DNS resolves fine but the full HTTP check above fails."""
    if not host:
        return _result("TCP Port", False, None, "No target configured")
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except (socket.timeout, TimeoutError):
        return _result("TCP Port", False, None, "Timeout")
    except OSError as exc:
        return _result("TCP Port", False, None, str(exc))
    latency_ms = round((time.monotonic() - start) * 1000, 1)
    return _result("TCP Port", True, latency_ms, f"OK (port {port})")


def gateway_ip_from_subnet(scan_subnet):

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


def get_default_gateway():
    system = platform.system()
    try:
        result = subprocess.run(
            ["route", "print", "0.0.0.0"],
            capture_output=True,
            text=True,
            timeout=3,
        )

        for line in result.stdout.splitlines():

            line = line.strip()

            if line.startswith("0.0.0.0"):

                parts = line.split()

                if len(parts) >= 3:
                    gateway = parts[2]

                    if gateway != "0.0.0.0":
                        return gateway
    except (
        subprocess.SubprocessError,
        OSError,
    ):
        pass

    return None

def run_all(gateway_ip, settings_obj=None):
    if settings_obj is None:
        from monitor.models import SystemSettings
        settings_obj = SystemSettings.load()

    return [
        check_dns(hostname=settings_obj.dns_hostname),
        check_web(url=settings_obj.web_url),
        check_tcp(host=settings_obj.tcp_host,port=settings_obj.tcp_port),
        check_gateway(gateway_ip),
    ]