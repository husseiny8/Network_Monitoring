import ping3

def ping_and_store(ip):

    try:
        ping_time = ping3.ping(ip)
        if ping_time is None:
            return {
                "success": False,
                "latency": None,
                "message": "Timeout"
            }

        return {
            "success": True,
            "latency": round(ping_time * 1000, 2),
            "message": "OK"
        }

    except Exception as e:
        return {
            "success": False,
            "latency": None,
            "message": str(e)
        }