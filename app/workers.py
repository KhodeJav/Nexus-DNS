"""Background threads. Nothing in here touches widgets; results travel via signals."""
import logging

from PySide6.QtCore import QThread, Signal

from . import dns_bench, netcheck
from . import windows_dns as wd
from .validators import parse_ipv4

log = logging.getLogger("dnschanger.workers")


class NetThread(QThread):
    result = Signal(object)          # NetStatus

    def run(self):
        try:
            self.result.emit(netcheck.check_internet())
        except Exception:
            log.exception("internet check crashed")
            self.result.emit(netcheck.NetStatus(False, "none"))


class BenchmarkThread(QThread):
    dns_started = Signal(int, int, int, str, str, str)   # index, total, dns_id, role, name, ip
    sample = Signal(int, int, float)                # dns_id, seq, ms (-1 = failed)
    dns_done = Signal(int, str, object)             # dns_id, role, result dict
    finished_all = Signal(str)                      # done | cancelled | offline

    def __init__(self, items, count, timeout_ms, parent=None):
        super().__init__(parent)
        self.items = items            # [(dns_id, role, name, ip)] - one entry per server to test
        self.count = max(1, int(count))
        self.timeout = max(0.2, min(1.0, timeout_ms / 1000.0))

    def run(self):
        try:
            self._run()
        except Exception:
            log.exception("benchmark crashed")
            self.finished_all.emit("cancelled")

    def _run(self):
        cancel = self.isInterruptionRequested
        if not netcheck.check_internet().online:
            self.finished_all.emit("offline")
            return
        total = len(self.items)
        for idx, (dns_id, role, name, ip) in enumerate(self.items):
            if cancel():
                self.finished_all.emit("cancelled")
                return
            self.dns_started.emit(idx, total, dns_id, role, name, ip)
            res = dns_bench.run_benchmark(
                ip, self.count, self.timeout, cancel=cancel,
                on_sample=lambda seq, ms, d=dns_id: self.sample.emit(d, seq, -1.0 if ms is None else ms))
            if res.status == dns_bench.CANCELLED:
                self.finished_all.emit("cancelled")
                return
            if res.status != dns_bench.OK and not netcheck.check_internet().online:
                # the failure is the user's connection, not this DNS: drop it and stop
                self.finished_all.emit("offline")
                return
            self.dns_done.emit(dns_id, role, res.to_dict())
        self.finished_all.emit("done")


class ApplyThread(QThread):
    """connect / disconnect the Windows DNS. Emits (ok, message_or_code, info)."""
    done = Signal(bool, str, object)

    def __init__(self, db, mode, dns=None, parent=None):
        super().__init__(parent)
        self.db, self.mode, self.dns = db, mode, dns

    def run(self):
        try:
            info = {"connect": self._connect, "disconnect": self._disconnect, "flush": self._flush}[self.mode]()
            self.done.emit(True, "", info)
        except wd.DnsError as e:
            self.done.emit(False, str(e), None)
        except Exception as e:      # never let the thread die silently
            log.exception("apply thread crashed")
            self.done.emit(False, f"unexpected:{e}", None)

    def _connect(self):
        if not wd.supported():
            raise wd.DnsError("not_windows")
        if not netcheck.check_internet().online:
            raise wd.DnsError("offline")                     # never touch DNS while offline
        servers = []
        for raw in (self.dns["primary_ip"], self.dns.get("secondary_ip") or ""):
            if raw:
                ip = parse_ipv4(raw)
                if not ip:
                    raise wd.DnsError("bad_servers")
                servers.append(ip)
        if not servers:
            raise wd.DnsError("bad_servers")

        adapter = wd.detect_active_adapter()
        existing = self.db.get_json("dns_backup")
        if existing and existing.get("guid") == adapter.guid:
            prev_static, prev_servers = existing["prev_static"], existing["prev_servers"]
            prev_dhcp = existing.get("prev_dhcp", True)
        else:
            if existing:                                      # connected on another adapter earlier
                try:
                    wd.restore_dns(wd.Adapter(existing["index"], existing["name"], existing["guid"], ""),
                                   existing["prev_static"], existing["prev_servers"], existing.get("prev_dhcp", True))
                except Exception:
                    log.warning("could not restore previous adapter", exc_info=True)
            prev_static, prev_servers = wd.read_dns_config(adapter.guid)
            prev_dhcp = wd.dhcp_enabled(adapter.guid)

        backup = dict(index=adapter.index, name=adapter.name, guid=adapter.guid,
                      prev_static=prev_static, prev_servers=prev_servers, prev_dhcp=prev_dhcp,
                      applied=servers, dns_id=self.dns["id"])
        self.db.set_json("dns_backup", backup)               # saved BEFORE changing anything
        try:
            wd.apply_dns(adapter, servers)
        except wd.DnsError:
            try:
                wd.restore_dns(adapter, prev_static, prev_servers, prev_dhcp)
            except wd.DnsError:
                log.error("rollback failed", exc_info=True)
            self.db.delete_setting("dns_backup")
            raise
        return backup

    def _flush(self):
        """Turn the app's DNS off (restore the previous one) and clear the resolver cache."""
        if not wd.supported():
            raise wd.DnsError("not_windows")
        restored = self._disconnect() if self.db.get_json("dns_backup") else None
        wd.flush_dns()
        return dict(flushed=True, restored=restored)

    def _disconnect(self):
        b = self.db.get_json("dns_backup")
        if not b:
            return None
        adapter = wd.Adapter(b["index"], b["name"], b["guid"], "")
        try:
            wd.read_dns_config(adapter.guid)
        except OSError:                                       # adapter no longer exists
            self.db.delete_setting("dns_backup")
            return dict(b, gone=True)
        wd.restore_dns(adapter, b["prev_static"], b["prev_servers"], b.get("prev_dhcp", True))
        self.db.delete_setting("dns_backup")
        return b


class AdapterThread(QThread):
    done = Signal(bool, object)       # ok, Adapter | error code

    def run(self):
        try:
            self.done.emit(True, wd.detect_active_adapter())
        except wd.DnsError as e:
            self.done.emit(False, str(e))
        except Exception as e:
            self.done.emit(False, f"unexpected:{e}")


def reconcile_connection(db):
    """At start-up: is the DNS we applied last time still the one active in Windows?"""
    b = db.get_json("dns_backup")
    if not b:
        return None
    if not wd.supported():
        db.delete_setting("dns_backup")
        return None
    try:
        static, servers = wd.read_dns_config(b["guid"])
    except Exception:
        db.delete_setting("dns_backup")
        return None
    if static and servers[:len(b["applied"])] == b["applied"]:
        return b
    db.delete_setting("dns_backup")       # user (or Windows) changed it meanwhile
    return None
