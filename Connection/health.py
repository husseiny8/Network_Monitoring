def calculate_latency_score(latency_ms):
    """
    تبدیل latency به امتیاز 0 تا 100.
    هرچه latency کمتر باشد، امتیاز بیشتر است.
    """

    if latency_ms is None:
        return 0

    if latency_ms <= 50:
        return 100

    if latency_ms <= 100:
        return 80

    if latency_ms <= 200:
        return 60

    if latency_ms <= 500:
        return 30

    return 0


def calculate_packet_loss_score(packet_loss):
    """
    تبدیل Packet Loss به امتیاز 0 تا 100.
    """

    if packet_loss <= 0:
        return 100

    if packet_loss <= 1:
        return 90

    if packet_loss <= 5:
        return 70

    if packet_loss <= 10:
        return 50

    if packet_loss <= 30:
        return 20

    return 0


def calculate_availability_score(availability):
    """
    Availability به صورت درصدی بین 0 تا 100.
    """

    return max(0, min(100, availability))


def calculate_health_score(
    availability,
    packet_loss,
    latency_ms,
):
    """
    محاسبه Network Health Score.
    """

    availability_score = calculate_availability_score(
        availability
    )

    packet_loss_score = calculate_packet_loss_score(
        packet_loss
    )

    latency_score = calculate_latency_score(
        latency_ms
    )

    health_score = (
        availability_score * 0.40
        + packet_loss_score * 0.30
        + latency_score * 0.30
    )

    return round(health_score, 1)