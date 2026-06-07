import scapy.all as scapy

### Network Scanning to Find All Devices in our Network ####
def scan(ip):
    arp_request = scapy.ARP(pdst=ip)
    broadcast = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
    arp_request_broadcast = broadcast / arp_request
    answered_list = scapy.srp(arp_request_broadcast, timeout=5, verbose=False)[0]

    clients_list = []
    for element in answered_list:
        clients_list.append({"ip": element[1].psrc, "mac": element[1].hwsrc})
    return clients_list

