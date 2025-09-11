from scapy.all import UDP, IP, Raw, send, rdpcap
import time

PCAP_FILE = "autriche1tour.pcap"
DST_IP = "127.0.0.1"
DST_PORT = 20777
IFACE = "lo0"  # Interface loopback sur macOS

packets = rdpcap(PCAP_FILE)

while True:
    for pkt in packets:
        if UDP in pkt and Raw in pkt:
            payload = pkt[Raw].load
            new_pkt = IP(dst=DST_IP)/UDP(dport=DST_PORT, sport=pkt[UDP].sport)/Raw(payload)
            send(new_pkt, iface=IFACE, verbose=False)
            print(f"Envoyé {len(payload)} octets UDP -> {DST_IP}:{DST_PORT}")
    time.sleep(0.05)
