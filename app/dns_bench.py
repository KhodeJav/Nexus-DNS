"""Real DNS benchmark engine.

Sends genuine DNS queries over UDP/53 straight to the server's IP address, so the
result never depends on the DNS currently configured in Windows. "Ping" in this app
means DNS response time, not ICMP.
"""
import random
import socket
import struct
import time
from dataclasses import dataclass, field

DOMAINS = [
    "google.com", "cloudflare.com", "microsoft.com", "wikipedia.org", "amazon.com",
    "apple.com", "github.com", "youtube.com", "bing.com", "yahoo.com",
    "instagram.com", "telegram.org", "steampowered.com", "discord.com", "twitch.tv",
]

OK = "OK"
TIMEOUT = "TimeOut"
UNAVAILABLE = "UNAVAILABLE"
INCOMPLETE = "INCOMPLETE"
CANCELLED = "CANCELLED"

MAX_VALID_MS = 999.0        # slower answers are treated as failures
MAX_CONSECUTIVE_FAILS = 3   # then this DNS is abandoned immediately


# ----------------------------------------------------------------------------- packets
def build_query(domain: str, qid: int) -> bytes:
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)  # RD=1, one question
    qname = b"".join(bytes([len(p)]) + p.encode("ascii") for p in domain.split(".")) + b"\x00"
    return header + qname + struct.pack(">HH", 1, 1)          # QTYPE=A, QCLASS=IN


def is_valid_response(data: bytes, qid: int) -> bool:
    """A valid answer: matching ID, QR bit set, RCODE NOERROR(0) or NXDOMAIN(3)."""
    if len(data) < 12:
        return False
    rid, flags = struct.unpack(">HH", data[:4])
    if rid != qid or not (flags & 0x8000):
        return False
    return (flags & 0x000F) in (0, 3)


def parse_reply(data: bytes, qid: int):
    """RCODE of a well-formed reply to OUR query (matching ID, QR bit set), else None."""
    if len(data) < 12:
        return None
    rid, flags = struct.unpack(">HH", data[:4])
    if rid != qid or not (flags & 0x8000):
        return None
    return flags & 0x000F


def query_once(sock, ip, domain, timeout, cancel=None, port=53):
    """Send one query. Returns (ms, usable) when a reply arrived, or None when nothing arrived in time.
    usable = the reply carried an answer (NOERROR / NXDOMAIN); REFUSED, SERVFAIL... arrive but are not usable.
    Raises OSError when the datagram cannot even be sent."""
    qid = random.getrandbits(16)
    packet = build_query(domain, qid)
    t0 = time.perf_counter()
    sock.sendto(packet, (ip, port))
    deadline = t0 + timeout
    while True:
        if cancel and cancel():
            return None
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return None
        sock.settimeout(min(remaining, 0.2))
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except ConnectionResetError:      # Windows: ICMP port-unreachable surfaced on UDP
            return None
        t1 = time.perf_counter()
        if addr[0] != ip:
            continue
        rcode = parse_reply(data, qid)
        if rcode is not None:
            return (t1 - t0) * 1000.0, rcode in (0, 3)
        # wrong ID / garbage: keep waiting until the deadline


# ----------------------------------------------------------------------------- stats
def compute_stats(samples, received=None):
    """samples : ms of every usable answer, None for a request without a usable answer
    received : how many requests got ANY reply (default: the usable ones)

    average : mean of usable response times
    jitter  : mean absolute difference between consecutive usable response times
    loss    : (sent - received) / sent * 100          <- the classic Packet Loss formula
    last    : response time of the last usable answer
    """
    sent = len(samples)
    ok = [s for s in samples if s is not None]
    got = len(ok) if received is None else received
    loss = (sent - got) * 100.0 / sent if sent else 0.0
    if not ok:
        return dict(sent=sent, success=0, last=None, avg=None, jitter=None, loss=loss)
    diffs = [abs(b - a) for a, b in zip(ok, ok[1:])]
    return dict(sent=sent, success=len(ok), last=ok[-1], avg=sum(ok) / len(ok),
                jitter=(sum(diffs) / len(diffs)) if diffs else 0.0, loss=loss)


@dataclass
class BenchResult:
    status: str
    sent: int = 0
    success: int = 0
    last: float = None
    avg: float = None
    jitter: float = None
    loss: float = 100.0
    samples: list = field(default_factory=list)
    received: int = 0          # requests that got any reply
    timeouts: int = 0          # requests that expired with no reply at all
    errors: int = 0            # replies that arrived but carried no answer (REFUSED, SERVFAIL...)

    def to_dict(self):
        return dict(status=self.status, sent=self.sent, success=self.success, last=self.last,
                    avg=self.avg, jitter=self.jitter, loss=self.loss, samples=list(self.samples),
                    received=self.received, timeouts=self.timeouts, errors=self.errors)


def _sleep(seconds, cancel):
    end = time.perf_counter() + seconds
    while True:
        left = end - time.perf_counter()
        if left <= 0 or (cancel and cancel()):
            return
        time.sleep(min(0.05, left))


def run_benchmark(ip, count=20, timeout=1.0, cancel=None, on_sample=None,
                  interval=0.08, port=53):
    samples, consecutive, os_errors, stopped_early = [], 0, 0, False
    received = errors = 0
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return BenchResult(UNAVAILABLE)
    try:
        for i in range(count):
            if cancel and cancel():
                return _result(CANCELLED, samples, received, errors)
            domain = DOMAINS[i % len(DOMAINS)]
            try:
                reply = query_once(sock, ip, domain, timeout, cancel, port)
            except OSError:
                reply = None
                os_errors += 1
            if cancel and cancel():
                return _result(CANCELLED, samples, received, errors)
            ms = None
            if reply is not None:
                took, usable = reply
                if took > MAX_VALID_MS:        # arrived after the allowed window = expired request
                    reply = None
                else:
                    received += 1
                    if usable:
                        ms = took
                    else:
                        errors += 1
            samples.append(ms)
            if on_sample:
                on_sample(i + 1, ms)
            if ms is None:
                consecutive += 1
                if consecutive >= MAX_CONSECUTIVE_FAILS:
                    stopped_early = True
                    break
            else:
                consecutive = 0
            if i < count - 1:
                _sleep(interval, cancel)
    finally:
        sock.close()

    res = _result(OK, samples, received, errors)
    if stopped_early and errors == 0 and count > res.sent:
        # Packet Loss = (requests planned - replies received) / requests planned.
        # The requests we never sent because the server was abandoned got no reply either.
        res.loss = (count - received) * 100.0 / count
    if res.success == 0:
        res.status = UNAVAILABLE if (received > 0 or (samples and os_errors == len(samples))) else TIMEOUT
    elif stopped_early:
        res.status = INCOMPLETE
    return res


def _result(status, samples, received, errors):
    st = compute_stats(samples, received)
    return BenchResult(status, sent=st["sent"], success=st["success"], last=st["last"], avg=st["avg"],
                       jitter=st["jitter"], loss=st["loss"], samples=list(samples), received=received,
                       timeouts=st["sent"] - received, errors=errors)


def grade(result):
    """Return 'good' | 'warn' | 'bad' | 'off' for colouring."""
    if not result:
        return "off"
    status = result.get("status")
    if status in (TIMEOUT, UNAVAILABLE, CANCELLED, None):
        return "off"
    if status == INCOMPLETE:
        return "bad"
    avg, jit, loss = result.get("avg"), result.get("jitter") or 0, result.get("loss") or 0
    if avg is None:
        return "off"
    if avg <= 80 and loss <= 2 and jit <= 20:
        return "good"
    if avg <= 160 and loss <= 10 and jit <= 50:
        return "warn"
    return "bad"
