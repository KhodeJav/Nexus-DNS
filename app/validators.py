"""Input validation. Nothing invalid may ever reach the database or Windows."""
import ipaddress


def parse_ipv4(text: str):
    """Return a normalised IPv4 string, or None when the value is not a usable DNS server."""
    try:
        ip = ipaddress.IPv4Address((text or "").strip())
    except ValueError:
        return None
    if ip.is_unspecified or ip.is_loopback or ip.is_multicast or ip.is_reserved:
        return None
    if str(ip) == "255.255.255.255":
        return None
    return str(ip)


def clean_name(text: str, max_len: int = 40):
    name = " ".join((text or "").split())
    if not name or len(name) > max_len:
        return None
    return name
