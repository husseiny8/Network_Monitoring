"""Host network interface throughput.

Unlike Connection.ping/services (which probe a *remote* target), this
measures the local machine's own NIC counters via psutil - always
available with no dependency on any other host responding, so it gives
a real "beyond ping" monitoring signal even on a network with nothing
else instrumented.
"""

import psutil


def read_counters():
    counters = psutil.net_io_counters()
    return {
        "bytes_sent": counters.bytes_sent,
        "bytes_recv": counters.bytes_recv,
    }


def compute_rate(previous, current, elapsed_seconds):
    """Bits-per-second throughput between two {bytes_sent, bytes_recv}
    readings taken `elapsed_seconds` apart.
    """
    if elapsed_seconds <= 0:
        return 0.0, 0.0

    sent_delta = current["bytes_sent"] - previous["bytes_sent"]
    recv_delta = current["bytes_recv"] - previous["bytes_recv"]

    sent_bps = max(0, sent_delta) * 8 / elapsed_seconds
    recv_bps = max(0, recv_delta) * 8 / elapsed_seconds

    return round(sent_bps, 1), round(recv_bps, 1)
