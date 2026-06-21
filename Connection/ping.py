import ping3
from monitor.models import Ping

def ping_and_store(ip, user=None, device=None):
    """Ping `ip` once and persist the result as a monitor.models.Ping row.

    `user`/`device` are optional - pass them when the caller knows who
    triggered the check or which known Device it relates to, so the
    history can be filtered/joined later.
    """
    # Imported lazily so this module stays import-safe even if Django's
    # app registry isn't ready yet at import time.

    try:
        ping_time = ping3.ping(ip)
        if ping_time is None:
            result = {"success": False, "latency": None, "message": "Timeout"}
        else:
            result = {
                "success": True,
                "latency": round(ping_time * 1000, 2),
                "message": "OK",
            }
    except Exception as e:
        result = {"success": False, "latency": None, "message": str(e)}

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
        # Persisting history should never break the live ping response -
        # e.g. migrations not yet applied. The caller still gets a result.
        pass

    return result
