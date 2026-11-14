"""Internet detection that does NOT depend on DNS.

Tier 1: direct TCP connections to independent public IPs (Google, Cloudflare).
Tier 2: only if Tier 1 fails - a trusted Iranian site (bmi.ir). Its IP is resolved once
        (system resolver) and cached, so later checks are direct TCP as well.
Any reachable target => online. All unreachable => offline.
"""
import socket
import struct
import threading
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed

NetStatus = namedtuple("NetStatus", "online scope")   # scope: global | domestic | none

GLOBAL_TARGETS = [("1.1.1.1", 443), ("8.8.8.8", 443), ("1.0.0.1", 443), ("8.8.4.4", 443)]
DOMESTIC_HOST = "bmi.ir"
_cached_domestic_ip = None


def _tcp(ip, port, timeout):
    """One bare TCP handshake (SYN/SYN-ACK/ACK) and an immediate RST: ~200 bytes, no data sent."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        return s.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        if s is not None:
            s.close()


def _check_global(timeout):
    # normal case: a single handshake to one target and we are done
    if _tcp(*GLOBAL_TARGETS[0], min(timeout, 1.5)):
        return True
    # it failed: only now try the remaining targets in parallel before declaring "offline"
    rest = GLOBAL_TARGETS[1:]
    pool = ThreadPoolExecutor(max_workers=len(rest))
    try:
        futures = [pool.submit(_tcp, ip, port, timeout) for ip, port in rest]
        for f in as_completed(futures, timeout=timeout + 1):
            if f.result():
                return True
    except Exception:
        pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return False


def _resolve(host, wait):
    box = []

    def work():
        try:
            box.append(socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0])
        except OSError:
            pass

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(wait)
    return box[0] if box else None


def _check_domestic(timeout):
    global _cached_domestic_ip
    if _cached_domestic_ip and (_tcp(_cached_domestic_ip, 443, timeout) or _tcp(_cached_domestic_ip, 80, timeout)):
        return True
    _cached_domestic_ip = None
    ip = _resolve(DOMESTIC_HOST, timeout + 1)
    if ip and (_tcp(ip, 443, timeout) or _tcp(ip, 80, timeout)):
        _cached_domestic_ip = ip
        return True
    return False


def check_internet(timeout=2.0) -> NetStatus:
    if _check_global(timeout):
        return NetStatus(True, "global")
    if _check_domestic(timeout):
        return NetStatus(True, "domestic")
    return NetStatus(False, "none")
