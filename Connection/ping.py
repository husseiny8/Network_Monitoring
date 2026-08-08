import ping3
from monitor.models import Ping

def ping_and_store(ip, user=None, device=None):
    try:
        ping_time = ping3.ping(ip)
        if ping_time is None:
            result = {
                "success": False,
                "latency": None,
                "message": "Timeout"
            }
        else:
            result = {
                "success": True,
                "latency": round(ping_time * 1000, 2),
                "message": "OK",
            }
    except Exception as e:
        result = {
            "success": False,
            "latency": None,
            "message": str(e)
        }

    try:
        Ping.objects.create(
            user=user if user and user.is_authenticated else None,
            device=device,
            target=ip,
            success=result["success"],
            latency_ms=result["latency"],
            message=result["message"],
        )
    except Exception:
        pass

    return result
