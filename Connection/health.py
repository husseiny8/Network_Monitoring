def calculate_service_score(service):

    if not service:
        return None

    status = service.get("status")

    if status == "success":
        return 100

    if status == "warning":
        return 60

    if status == "danger":
        return 0

    return None


def calculate_latency_score(latency_ms):

    if latency_ms is None:
        return None

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

    if packet_loss is None:
        return None

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

    if availability is None:
        return None

    return max(0, min(100, float(availability)))


def _weighted_average(scores):

    valid_scores = [
        (score, weight)
        for score, weight in scores
        if score is not None
    ]

    if not valid_scores:
        return 0

    total_weight = sum(
        weight for _, weight in valid_scores
    )

    if total_weight <= 0:
        return 0

    weighted_sum = sum(
        score * weight
        for score, weight in valid_scores
    )

    return weighted_sum / total_weight


def calculate_health_score(
    availability,
    packet_loss,
    latency_ms,
    services=None,
):
    """
    Calculate overall network health.
    We consider:
        - Availability
        - Packet Loss
        - Latency
        - DNS
        - Web Server
        - TCP Port
        - Gateway
        - Database
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

    service_scores = {}

    if services:

        for service in services:

            name = service.get("name")

            score = calculate_service_score(
                service
            )

            if score is not None:
                service_scores[name] = score

    dns_score = service_scores.get("DNS")
    web_score = service_scores.get("Web Server")
    tcp_score = service_scores.get("TCP Port")
    gateway_score = service_scores.get("Gateway")

    scores = [
        (availability_score, 0.20),
        (packet_loss_score, 0.20),
        (latency_score, 0.15),
        (dns_score, 0.10),
        (web_score, 0.10),
        (tcp_score, 0.10),
        (gateway_score, 0.15),
    ]

    health_score = _weighted_average(
        scores
    )

    return round(
        max(0, min(100, health_score)),
        1,
    )