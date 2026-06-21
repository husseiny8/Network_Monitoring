import scapy.all as scapy

### Network Scanning to Find All Devices in our Network ####
def scan(ip, timeout=5):
    """ARP-scan a subnet (e.g. "192.168.1.1/24") and return a list of
    {"ip": ..., "mac": ...} dicts for every host that answers.

    Sending raw ARP frames needs raw-socket access (root/CAP_NET_RAW on
    Linux, admin on Windows). On machines/containers without that
    privilege - or without a real local network to scan - this raises
    instead of returning results, so callers should not assume this
    always succeeds.
    """
    arp_request = scapy.ARP(pdst=ip)
    broadcast = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
    arp_request_broadcast = broadcast / arp_request
    answered_list = scapy.srp(arp_request_broadcast, timeout=timeout, verbose=False)[0]

    clients_list = []
    for element in answered_list:
        clients_list.append({"ip": element[1].psrc, "mac": element[1].hwsrc})
    return clients_list
