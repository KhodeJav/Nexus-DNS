"""DNS Explorer data layer: download, validate and cache the public DNS list.

No widgets in here. The source of truth is the JSON file in the Nexus-DNS GitHub repository;
nothing about the servers is hard-coded. Everything that reaches the UI has been validated first.
"""
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .validators import parse_ipv4

SOURCE_URL = "https://raw.githubusercontent.com/KhodeJav/Nexus-DNS/main/dns_explorer.json"
HTTP_TIMEOUT = 8.0                 # seconds, for connect and for every read
MAX_BYTES = 2 * 1024 * 1024        # a DNS list is tiny; anything bigger is not what we expect
CACHE_KEY = "explorer_cache"
SUPPORTED_SCHEMA = 1


class ExplorerError(Exception):
    """code: network | http | invalid"""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class ExplorerDns:
    id: str
    name: str
    country_code: str          # "" when missing / not a valid ISO 3166-1 alpha-2 code
    primary_dns: str
    secondary_dns: str         # kept in the model, never used by the ping test

    def to_dict(self):
        return dict(id=self.id, name=self.name, country_code=self.country_code,
                    primary_dns=self.primary_dns, secondary_dns=self.secondary_dns)


# ----------------------------------------------------------------------------- helpers
def flag_emoji(country_code: str) -> str:
    """ISO 3166-1 alpha-2 -> flag emoji (two regional-indicator letters). '' when the code is not valid."""
    code = (country_code or "").strip().upper()
    if len(code) != 2 or not all("A" <= c <= "Z" for c in code):
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


def _clean_country(value) -> str:
    code = value.strip().upper() if isinstance(value, str) else ""
    return code if len(code) == 2 and all("A" <= c <= "Z" for c in code) else ""


# ----------------------------------------------------------------------------- validation
def parse_servers(data):
    """Validate the decoded JSON. Returns (updated_at, [ExplorerDns]).

    A broken record is skipped (it never takes the page down). The whole payload is rejected
    (ValueError) when it is not the expected structure at all."""
    if not isinstance(data, dict):
        raise ValueError("root is not an object")
    schema = data.get("schema_version", SUPPORTED_SCHEMA)
    if not isinstance(schema, int) or isinstance(schema, bool) or schema > SUPPORTED_SCHEMA:
        raise ValueError("unsupported schema_version")
    records = data.get("dns_servers")
    if not isinstance(records, list):
        raise ValueError("dns_servers is not a list")
    out, seen = [], set()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        rid, name = rec.get("id"), rec.get("name")
        if not isinstance(rid, str) or not rid.strip() or not isinstance(name, str) or not name.strip():
            continue
        rid = rid.strip()
        primary = parse_ipv4(rec.get("primary_dns") if isinstance(rec.get("primary_dns"), str) else "")
        if not primary or rid in seen:                      # id is the identity of a record
            continue
        sec_raw = rec.get("secondary_dns")
        secondary = parse_ipv4(sec_raw) if isinstance(sec_raw, str) else None
        seen.add(rid)
        out.append(ExplorerDns(rid, " ".join(name.split())[:60], _clean_country(rec.get("country_code")),
                               primary, secondary or ""))
    if records and not out:
        raise ValueError("no valid record")
    updated = data.get("updated_at")
    return (updated if isinstance(updated, str) else ""), out


def servers_from_cache(cache):
    """Re-validate a stored cache. Returns (updated_at, [ExplorerDns]) or None when it is unusable."""
    if not isinstance(cache, dict) or not isinstance(cache.get("servers"), list):
        return None
    try:
        return parse_servers({"schema_version": SUPPORTED_SCHEMA, "updated_at": cache.get("updated_at", ""),
                              "dns_servers": cache["servers"]})
    except ValueError:
        return None


# ----------------------------------------------------------------------------- download
def fetch(cache=None, url=SOURCE_URL, timeout=HTTP_TIMEOUT):
    """Download and validate the list. Blocking: call it from a worker thread.

    Uses ETag / Last-Modified from `cache` so an unchanged file is not downloaded again.
    Returns (changed, new_cache). `changed` is False when GitHub answered 304 (cache is still current).
    Raises ExplorerError."""
    headers = {"User-Agent": "NexusDNS-Explorer", "Accept": "application/json", "Cache-Control": "no-cache"}
    usable = servers_from_cache(cache) is not None
    if usable and cache.get("etag"):
        headers["If-None-Match"] = cache["etag"]
    if usable and cache.get("last_modified"):
        headers["If-Modified-Since"] = cache["last_modified"]
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BYTES + 1)
            etag, last_mod = resp.headers.get("ETag", ""), resp.headers.get("Last-Modified", "")
    except urllib.error.HTTPError as e:
        if e.code == 304 and usable:
            fresh = dict(cache)
            fresh["fetched_at"] = int(time.time())
            return False, fresh
        raise ExplorerError("http", str(e.code))
    except (urllib.error.URLError, OSError, ValueError) as e:      # offline, DNS failure, timeout, TLS...
        raise ExplorerError("network", str(e))
    if len(raw) > MAX_BYTES:
        raise ExplorerError("invalid", "response too large")
    try:
        updated, servers = parse_servers(json.loads(raw.decode("utf-8-sig")))
    except (ValueError, UnicodeDecodeError) as e:
        raise ExplorerError("invalid", str(e))
    return True, dict(etag=etag, last_modified=last_mod, updated_at=updated, fetched_at=int(time.time()),
                      servers=[s.to_dict() for s in servers])
