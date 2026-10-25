"""Local network addresses phones can use to reach this PC (no internet lookups)."""
import ipaddress
import socket

import psutil

VIRTUAL_HINTS = ('vethernet', 'virtual', 'vmware', 'hyper-v', 'wsl', 'loopback', 'bluetooth',
                 'tailscale', 'zerotier', 'vpn', 'tap', 'docker')


def addresses():
    """Up IPv4 adapters with private addresses, home adapters first."""
    found = []
    try:
        stats = psutil.net_if_stats()
        for adapter, entries in psutil.net_if_addrs().items():
            if adapter in stats and not stats[adapter].isup:
                continue
            for entry in entries:
                if entry.family != socket.AF_INET:
                    continue
                ip = ipaddress.ip_address(entry.address)
                if ip.is_loopback or ip.is_link_local or not ip.is_private:
                    continue
                virtual = any(hint in adapter.lower() for hint in VIRTUAL_HINTS)
                found.append({'ip': entry.address, 'adapter': adapter, 'preferred': not virtual})
    except (OSError, ValueError):
        pass
    if not found:
        try:
            for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
                if not ip.startswith('127.'):
                    found.append({'ip': ip, 'adapter': 'Network', 'preferred': True})
        except OSError:
            pass
    unique = {item['ip']: item for item in found}
    return sorted(unique.values(), key=lambda item: (not item['preferred'], item['ip']))
