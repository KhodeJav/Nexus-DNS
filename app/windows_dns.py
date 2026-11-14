"""Windows DNS control: adapter detection, apply, verify, restore.

Everything runs through argument lists (never a shell string) and only with
addresses that were validated beforehand.
"""
import logging
import os
import re
import subprocess
import sys
from collections import namedtuple

log = logging.getLogger("dnschanger.windns")
CREATE_NO_WINDOW = 0x08000000

Adapter = namedtuple("Adapter", "index name guid description")


class DnsError(Exception):
    """Raised with a message that is safe to show to the user."""


def supported() -> bool:
    return os.name == "nt"


def is_admin() -> bool:
    if not supported():
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Start a new elevated copy of this program (UAC prompt). True when the request was accepted."""
    if not supported():
        return False
    import ctypes
    exe = sys.executable
    if getattr(sys, "frozen", False):
        args = sys.argv[1:]
    else:
        pyw = exe.replace("python.exe", "pythonw.exe")
        exe = pyw if os.path.exists(pyw) else exe
        args = sys.argv
    params = subprocess.list2cmdline(args)
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1) > 32


# ----------------------------------------------------------------------------- process helper
def _decode(data: bytes) -> str:
    for enc in ("oem", "utf-8", "latin-1"):
        try:
            return data.decode(enc, errors="replace")
        except LookupError:
            continue
    return ""


def _run(cmd, timeout=25):
    flags = CREATE_NO_WINDOW if supported() else 0
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=flags, shell=False)
    except subprocess.TimeoutExpired:
        raise DnsError("Windows did not answer in time.")
    except OSError as e:
        raise DnsError(f"Could not run a Windows command: {e}")
    return p.returncode, _decode(p.stdout).strip(), _decode(p.stderr).strip()


# ----------------------------------------------------------------------------- adapter
_PS_ADAPTER = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$items = foreach ($r in (Get-NetRoute -DestinationPrefix '0.0.0.0/0' -AddressFamily IPv4)) {
  $a = Get-NetAdapter -InterfaceIndex $r.ifIndex -ErrorAction SilentlyContinue
  if ($a -and $a.Status -eq 'Up') {
    $m = (Get-NetIPInterface -InterfaceIndex $r.ifIndex -AddressFamily IPv4).InterfaceMetric
    [pscustomobject]@{Index=[int]$r.ifIndex; Name=[string]$a.Name; Guid=[string]$a.InterfaceGuid;
      Desc=[string]$a.InterfaceDescription; Hw=[bool]$a.HardwareInterface; Metric=[int]($r.RouteMetric+$m)}
  }
}
$items | Sort-Object @{Expression='Hw';Descending=$true}, Metric | Select-Object -First 1 | ConvertTo-Json -Compress
"""


def detect_active_adapter() -> Adapter:
    """The adapter that owns the default route (physical adapters are preferred over VPN/virtual)."""
    if not supported():
        raise DnsError("not_windows")
    import json
    rc, out, err = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                         "-Command", _PS_ADAPTER], timeout=30)
    if rc != 0 or not out:
        log.error("adapter detection failed rc=%s err=%s", rc, err)
        raise DnsError("no_adapter")
    try:
        d = json.loads(out)
        return Adapter(int(d["Index"]), str(d["Name"]), _braced(str(d["Guid"])), str(d["Desc"]))
    except (ValueError, KeyError, TypeError):
        raise DnsError("no_adapter")


def _braced(guid: str) -> str:
    guid = guid.strip()
    return guid if guid.startswith("{") else "{" + guid + "}"


# ----------------------------------------------------------------------------- read / write
def read_dns_config(guid: str):
    """Return (is_static, servers) for the adapter, straight from the registry."""
    if not supported():
        return False, []
    import winreg
    path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\\" + _braced(guid)
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
        try:
            value, _ = winreg.QueryValueEx(k, "NameServer")
        except FileNotFoundError:
            value = ""
    servers = [s for s in re.split(r"[,\s;]+", value or "") if s]
    return bool(servers), servers


def dhcp_enabled(guid: str) -> bool:
    """True when the adapter takes its IP (and so its automatic DNS) from DHCP."""
    if not supported():
        return True
    import winreg
    path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\\" + _braced(guid)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            return bool(winreg.QueryValueEx(k, "EnableDHCP")[0])
    except OSError:
        return True


def _netsh(args, adapter: Adapter, what: str):
    """Try the adapter alias first, then its numeric index."""
    last = ""
    for ident in (adapter.name, str(adapter.index)):
        rc, out, err = _run(["netsh", "interface", "ipv4"] + [a.replace("{N}", ident) for a in args])
        if rc == 0:
            return
        last = out or err
    log.error("netsh %s failed: %s", what, last)
    raise DnsError(last or what)


def _flush():
    try:
        _run(["ipconfig", "/flushdns"], timeout=15)
    except DnsError:
        pass


def flush_dns():
    """Clear the Windows DNS resolver cache (needs Administrator)."""
    if not supported():
        raise DnsError("not_windows")
    rc, out, err = _run(["ipconfig", "/flushdns"], timeout=15)
    if rc != 0:
        log.error("flushdns failed rc=%s %s %s", rc, out, err)
        raise DnsError("flush_failed")


def apply_dns(adapter: Adapter, servers):
    servers = list(servers)
    if not 1 <= len(servers) <= 8:
        raise DnsError("bad_servers")
    _netsh(["set", "dnsservers", "{N}", "static", servers[0], "primary", "no"], adapter, "set primary")
    for i, extra in enumerate(servers[1:], start=2):
        _netsh(["add", "dnsservers", "{N}", extra, f"index={i}", "validate=no"], adapter, "add secondary")
    _flush()
    static, current = read_dns_config(adapter.guid)
    if not static or current[:len(servers)] != list(servers):
        raise DnsError("verify_failed")


def restore_dns(adapter: Adapter, was_static: bool, servers, dhcp: bool = True):
    if was_static and servers:
        apply_dns(adapter, list(servers))
        return
    if not dhcp:
        # the adapter had NO DNS at all (static IP, empty DNS list): leave it empty, do not invent one
        _netsh(["set", "dnsservers", "{N}", "static", "none"], adapter, "clear dns")
        _flush()
        return
    _netsh(["set", "dnsservers", "{N}", "dhcp"], adapter, "restore dhcp")
    _flush()
