"""Best-effort SNMP polling for network equipment (routers, switches,
managed APs, ...) that expose the standard MIB-II objects.

This is intentionally optional and *never* raises out of this module:
most home/small-office gear ships with SNMP turned off by default, so a
timeout here is an expected, common outcome - not a bug. If the
`pysnmp` package isn't installed at all, every call below returns an
"unavailable" result instead of raising an ImportError at import time,
so the rest of the app keeps working without it.

Setup
-----
    pip install "pysnmp==4.4.12" "pyasn1<0.5.0"

pysnmp 4.4.12 is the last release before the project's async-first
rewrite, and is what the synchronous getCmd()/next() pattern below
targets. It still depends on Python's old `asyncore` module, which was
removed in Python 3.12 - on 3.12+ also run:

    pip install pyasyncore

instructions above are in requirements.txt as well.
"""

try:
    from pysnmp.hlapi import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        getCmd,
    )
    SNMP_AVAILABLE = True
except ImportError:
    SNMP_AVAILABLE = False


# Standard MIB-II OIDs - present on essentially any SNMP-speaking
# device, unlike vendor-specific MIBs which would need a per-brand OID
# table just to read a description string.
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"  # TimeTicks: hundredths of a second


def _unavailable(error):
    return {
        "reachable": False,
        "sys_descr": "",
        "uptime_seconds": None,
        "error": error,
    }


def poll_device(ip_address, community="public", port=161, timeout=2):
    """Single SNMP GET for sysDescr + sysUpTime.

    Always returns a dict safe to render directly:
        {"reachable": bool, "sys_descr": str,
         "uptime_seconds": int | None, "error": str | None}
    """

    if not SNMP_AVAILABLE:
        return _unavailable("کتابخانه pysnmp نصب نشده است.")

    try:
        iterator = getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),  # mpModel=1 -> SNMPv2c
            UdpTransportTarget((ip_address, port), timeout=timeout, retries=0),
            ContextData(),
            ObjectType(ObjectIdentity(OID_SYS_DESCR)),
            ObjectType(ObjectIdentity(OID_SYS_UPTIME)),
        )

        error_indication, error_status, error_index, var_binds = next(iterator)

        if error_indication:
            return _unavailable(str(error_indication))

        if error_status:
            return _unavailable(error_status.prettyPrint())

        sys_descr = str(var_binds[0][1])
        uptime_ticks = int(var_binds[1][1])

        return {
            "reachable": True,
            "sys_descr": sys_descr,
            "uptime_seconds": uptime_ticks // 100,
            "error": None,
        }

    except Exception as exc:
        # Any transport/library failure (timeout, unreachable host,
        # malformed response, ...) degrades to "not reachable" instead
        # of a 500 - this is a best-effort probe, not a core check.
        return _unavailable(str(exc))
