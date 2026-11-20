"""Forced-update logic (no widgets): ask GitHub for the newest Release, compare versions, download, install.

Rules
  * latest_version  = tag of the newest GitHub Release (e.g. v1.2.0)
  * minimum_supported_version = optional line in the Release notes:   minimum_supported_version: 1.2.0
    (without that line every version older than the latest one is blocked, i.e. exactly one version may run)
  * the installed version is app.__version__
If the installed version is below the minimum the app must update before it can be used.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from . import __version__, update_config as cfg
from .paths import data_dir

CACHE_KEY = "update_info"
PLACEHOLDER = "Null_Link"
ALLOWED_HOSTS = ("github.com", "api.github.com", "githubusercontent.com")   # + any subdomain of these
MAX_NOTES = 1500


class UpdateError(Exception):
    """code: network | invalid | nolink | download | install"""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class ReleaseInfo:
    latest: str
    minimum: str
    url: str
    notes: str

    def to_dict(self):
        return dict(latest=self.latest, minimum=self.minimum, url=self.url, notes=self.notes)


# ----------------------------------------------------------------------------- versions
def parse_version(text):
    """'v1.2.0' -> (1, 2, 0); None when it is not a plain dotted number."""
    m = re.fullmatch(r"\s*[vV]?(\d+(?:\.\d+){0,3})\s*", text if isinstance(text, str) else "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _pad(v, n=4):
    return tuple(v) + (0,) * (n - len(v))


def is_older(installed, other):
    a, b = parse_version(installed), parse_version(other)
    return bool(a and b and _pad(a) < _pad(b))


def update_required(info, installed=__version__):
    """True when the installed version is below the minimum supported version."""
    return bool(info) and is_older(installed, info.get("minimum") or info.get("latest"))


def configured():
    return PLACEHOLDER not in (cfg.REPO_OWNER, cfg.REPO_NAME)


def trusted_url(url):
    p = urlparse(url if isinstance(url, str) else "")
    host = (p.hostname or "").lower()
    return p.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


# ----------------------------------------------------------------------------- check
def parse_release(data):
    """Validate the GitHub 'latest release' JSON -> ReleaseInfo (ValueError when it is not usable)."""
    if not isinstance(data, dict):
        raise ValueError("not an object")
    tag = data.get("tag_name")
    if not parse_version(tag):
        raise ValueError("bad tag_name")
    latest = ".".join(str(x) for x in parse_version(tag))
    body = data.get("body") if isinstance(data.get("body"), str) else ""
    m = re.search(r"minimum_supported_version\s*[:=]\s*[\"']?[vV]?(\d+(?:\.\d+){0,3})", body)
    minimum = m.group(1) if m else latest
    if is_older(latest, minimum):                       # a minimum above the latest makes no sense
        minimum = latest
    url = ""
    assets = [a for a in data.get("assets") or [] if isinstance(a, dict)]
    pick = next((a for a in assets if a.get("name") == cfg.INSTALLER_ASSET), None) \
        or next((a for a in assets if str(a.get("name", "")).lower().endswith(".exe")), None)
    if pick and isinstance(pick.get("browser_download_url"), str):
        url = pick["browser_download_url"]
    elif cfg.FALLBACK_DOWNLOAD_URL != PLACEHOLDER:
        url = cfg.FALLBACK_DOWNLOAD_URL
    notes = re.sub(r"minimum_supported_version[^\n]*\n?", "", body).strip()[:MAX_NOTES]
    return ReleaseInfo(latest, minimum, url, notes)


def check(timeout=None):
    """Ask GitHub for the newest Release. Blocking - worker thread only. Raises UpdateError."""
    url = f"https://api.github.com/repos/{cfg.REPO_OWNER}/{cfg.REPO_NAME}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "DNSChanger-Updater", "Accept": "application/vnd.github+json",
                                               "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=timeout or cfg.CHECK_TIMEOUT) as resp:
            raw = resp.read(1024 * 1024)
        return parse_release(json.loads(raw.decode("utf-8")))
    except urllib.error.HTTPError as e:
        raise UpdateError("network", f"http {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError("network", str(e))
    except (ValueError, UnicodeDecodeError) as e:
        raise UpdateError("invalid", str(e))


# ----------------------------------------------------------------------------- download + install
def update_dir():
    d = data_dir() / "update"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download(url, progress=None, cancel=None):
    """Download the installer into the update folder; returns its path. Blocking - worker thread only."""
    if not url or url == PLACEHOLDER:
        raise UpdateError("nolink")
    if not trusted_url(url):
        raise UpdateError("download", "untrusted download address")
    dest = update_dir() / "installer.exe"
    part = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "DNSChanger-Updater"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if not trusted_url(resp.geturl()):                       # a redirect must stay on GitHub's hosts
                raise UpdateError("download", "untrusted redirect")
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            with open(part, "wb") as f:
                while True:
                    if cancel and cancel():
                        raise UpdateError("download", "cancelled")
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if progress:
                        progress(got, total)
        if total and got != total:
            raise UpdateError("download", "incomplete file")
        with open(part, "rb") as f:
            if f.read(2) != b"MZ":                                   # not a Windows executable
                raise UpdateError("download", "not an installer")
        os.replace(part, dest)
        return str(dest)
    except UpdateError:
        _silent_remove(part)
        raise
    except (urllib.error.URLError, OSError, ValueError) as e:
        _silent_remove(part)
        raise UpdateError("download", str(e))


def _silent_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def clear_caches(db):
    """Throw away everything cached by the old version, so the new one starts clean."""
    for key in ("explorer_cache",):
        try:
            db.delete_setting(key)
        except Exception:
            pass
    try:
        for f in update_dir().iterdir():
            if f.name != "installer.exe":
                _silent_remove(f)
    except OSError:
        pass


def launch_installer(installer):
    """Start a detached helper that waits for this process to exit, runs the installer silently, then starts the
    app again. The caller must quit the application right after this returns."""
    if os.name != "nt":
        raise UpdateError("install", "automatic install is Windows only")
    app_cmd = f'"{sys.executable}"' if getattr(sys, "frozen", False) else \
        f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
    bat = update_dir() / "apply_update.bat"
    script = (
        "@echo off\r\n"
        f":wait\r\ntasklist /FI \"PID eq {os.getpid()}\" 2>nul | find \"{os.getpid()}\" >nul\r\n"
        "if not errorlevel 1 ( ping -n 2 127.0.0.1 >nul & goto wait )\r\n"
        f'start /wait "" "{installer}" {cfg.INSTALLER_ARGS}\r\n'
        f'del /f /q "{installer}" >nul 2>nul\r\n'
        f"start \"\" {app_cmd}\r\n"
        "del /f /q \"%~f0\" >nul 2>nul\r\n")
    try:
        bat.write_text(script, encoding="utf-8")
        subprocess.Popen(["cmd", "/c", str(bat)], creationflags=0x00000008 | 0x08000000, close_fds=True)
    except OSError as e:
        raise UpdateError("install", str(e))


def save_cache(db, info):
    db.set_json(CACHE_KEY, dict(info.to_dict(), checked_at=int(time.time())))


def load_cache(db):
    c = db.get_json(CACHE_KEY)
    return c if isinstance(c, dict) and parse_version(c.get("latest")) else None
