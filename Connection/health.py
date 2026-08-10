def calculate_service_score(service):

    if not service:
        return 0

    if service.get("status") == "success":
        return 100

    if service.get("status") == "warning":
        return 60

    return 0


def calculate_latency_score(latency_ms):

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
    return max(0, min(100, availability))


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

    dns_score = 0
    web_score = 0
    tcp_score = 0
    gateway_score = 0
    database_score = 0

    if services:

        for service in services:

            name = service.get("name")

            if name == "DNS":
                dns_score = calculate_service_score(service)

            elif name == "Web Server":
                web_score = calculate_service_score(service)

            elif name == "TCP Port":
                tcp_score = calculate_service_score(service)

            elif name == "Gateway":
                gateway_score = calculate_service_score(service)

            elif name == "Database":
                database_score = calculate_service_score(service)

    health_score = (
        availability_score * 0.20
        + packet_loss_score * 0.15
        + latency_score * 0.15

        + dns_score * 0.10
        + web_score * 0.10
        + tcp_score * 0.05
        + gateway_score * 0.15
        + database_score * 0.05
    )

    return round(
        max(0, min(100, health_score)),
        1
    )