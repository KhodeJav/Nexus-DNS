"""SQLite storage (auto-created, thread-safe)."""
import json
import sqlite3
import threading
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS dns(
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, primary_ip TEXT NOT NULL,
    secondary_ip TEXT NOT NULL DEFAULT '', group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    is_favorite INTEGER NOT NULL DEFAULT 0, is_pinned INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS results(
    dns_id INTEGER NOT NULL REFERENCES dns(id) ON DELETE CASCADE, role TEXT NOT NULL DEFAULT 'primary',
    status TEXT, sent INTEGER, success INTEGER, last_ping REAL, avg_ping REAL, jitter REAL, loss REAL,
    samples TEXT, tested_at TEXT, PRIMARY KEY(dns_id, role));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""

DEFAULTS = {"theme": "dark", "lang": "fa", "minimize_tray": "0", "test_count": "20", "timeout_ms": "1000"}

CATALOG_VERSION = 2
CATALOG = [
    ("Russian DNS", [
        ("Yandex Basic", "77.88.8.8", "77.88.8.1"),
        ("Yandex Safe", "77.88.8.88", "77.88.8.2"),
        ("Yandex Family", "77.88.8.7", "77.88.8.3"),
    ]),
    ("Gaming DNS", [
        ("Cloudflare", "1.1.1.1", "1.0.0.1"),
        ("Google", "8.8.8.8", "8.8.4.4"),
        ("Quad9", "9.9.9.9", "149.112.112.112"),
    ]),
    ("Cloud DNS", [
        ("OpenDNS", "208.67.222.222", "208.67.220.220"),
        ("AdGuard", "94.140.14.14", "94.140.15.15"),
        ("CleanBrowsing", "185.228.168.9", "185.228.169.9"),
        ("Cloudflare Family", "1.1.1.3", "1.0.0.3"),
        ("Control D", "76.76.2.0", "76.76.10.0"),
    ]),
    ("Iranian DNS", [
        ("Shecan", "178.22.122.100", "185.51.200.2"),
        ("Electro", "78.157.42.100", "78.157.42.101"),
        ("403 Online", "10.202.10.202", "10.202.10.102"),
        ("Begzar", "185.55.226.26", "185.55.225.25"),
        ("DNSPro", "87.107.110.109", "87.107.110.110"),
        ("MCI (همراه اول)", "208.67.220.200", "208.67.222.222"),
        ("TCI (مخابرات)", "217.218.155.155", "217.218.127.127"),
    ]),
]


class Database:
    def __init__(self, path):
        self._lock = threading.RLock()
        self._c = sqlite3.connect(str(path), check_same_thread=False)
        self._c.row_factory = sqlite3.Row
        with self._lock:
            self._c.execute("PRAGMA foreign_keys=ON")
            cols = [r[1] for r in self._c.execute("PRAGMA table_info(results)").fetchall()]
            if cols and "role" not in cols:          # older version: results are disposable, rebuild
                self._c.execute("DROP TABLE results")
            self._c.executescript(SCHEMA)
            self._c.commit()
        if self.get("catalog_version") != str(CATALOG_VERSION):
            self.ensure_defaults()
            self.set("catalog_version", CATALOG_VERSION)

    # ------------------------------------------------------------------ helpers
    def _q(self, sql, params=(), commit=False):
        with self._lock:
            cur = self._c.execute(sql, params)
            if commit:
                self._c.commit()
            return cur

    def _all(self, sql, params=()):
        with self._lock:
            return [dict(r) for r in self._c.execute(sql, params).fetchall()]

    def ensure_defaults(self):
        """Add every catalog DNS that is not in the database yet (matched by primary IP).
        Runs once per catalog version; the user's own entries and edits are never touched."""
        have = {r["primary_ip"] for r in self._all("SELECT primary_ip FROM dns")}
        groups = {g["name"].lower(): g["id"] for g in self.list_groups()}
        for gname, items in CATALOG:
            for name, p, s in items:
                if p in have:
                    continue
                gid = groups.get(gname.lower())
                if gid is None:
                    gid = groups[gname.lower()] = self.add_group(gname)
                self.add_dns(name, p, s, gid)
                have.add(p)

    def close(self):
        with self._lock:
            self._c.close()

    # ------------------------------------------------------------------ settings
    def get(self, key, default=None):
        row = self._q("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return DEFAULTS.get(key, default)
        return row["value"]

    def set(self, key, value):
        self._q("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)), commit=True)

    def delete_setting(self, key):
        self._q("DELETE FROM settings WHERE key=?", (key,), commit=True)

    def get_int(self, key, default=0):
        try:
            return int(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_bool(self, key):
        return str(self.get(key, "0")) in ("1", "true", "True")

    def get_json(self, key):
        raw = self.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def set_json(self, key, obj):
        self.set(key, json.dumps(obj))

    # ------------------------------------------------------------------ groups
    def list_groups(self):
        return self._all("""SELECT g.id, g.name, g.sort_order,
                            (SELECT COUNT(*) FROM dns d WHERE d.group_id=g.id) AS count
                            FROM groups g ORDER BY g.sort_order, g.id""")

    def add_group(self, name):
        nxt = (self._q("SELECT COALESCE(MAX(sort_order),0)+1 FROM groups").fetchone()[0])
        cur = self._q("INSERT INTO groups(name,sort_order) VALUES(?,?)", (name, nxt), commit=True)
        return cur.lastrowid

    def rename_group(self, gid, name):
        self._q("UPDATE groups SET name=? WHERE id=?", (name, gid), commit=True)

    def delete_group(self, gid):
        self._q("DELETE FROM groups WHERE id=?", (gid,), commit=True)

    # ------------------------------------------------------------------ dns
    def list_dns(self, group_id=None, favorites_only=False):
        where, params = [], []
        if group_id is not None:
            where.append("d.group_id=?")
            params.append(group_id)
        if favorites_only:
            where.append("d.is_favorite=1")
        sql = ("SELECT d.*, g.name AS group_name FROM dns d JOIN groups g ON g.id=d.group_id"
               + (" WHERE " + " AND ".join(where) if where else "")
               + " ORDER BY d.is_pinned DESC, d.sort_order, d.id")
        return self._all(sql, params)

    def get_dns(self, dns_id):
        rows = self._all("SELECT d.*, g.name AS group_name FROM dns d JOIN groups g ON g.id=d.group_id WHERE d.id=?",
                         (dns_id,))
        return rows[0] if rows else None

    def add_dns(self, name, primary_ip, secondary_ip, group_id):
        nxt = self._q("SELECT COALESCE(MAX(sort_order),0)+1 FROM dns WHERE group_id=?", (group_id,)).fetchone()[0]
        cur = self._q("INSERT INTO dns(name,primary_ip,secondary_ip,group_id,sort_order) VALUES(?,?,?,?,?)",
                      (name, primary_ip, secondary_ip or "", group_id, nxt), commit=True)
        return cur.lastrowid

    def update_dns(self, dns_id, name, primary_ip, secondary_ip, group_id):
        old = self.get_dns(dns_id)
        self._q("UPDATE dns SET name=?,primary_ip=?,secondary_ip=?,group_id=? WHERE id=?",
                (name, primary_ip, secondary_ip or "", group_id, dns_id), commit=True)
        if old and old["primary_ip"] != primary_ip:
            self.delete_result(dns_id)      # old numbers belong to another server

    def delete_dns(self, dns_id):
        self._q("DELETE FROM dns WHERE id=?", (dns_id,), commit=True)

    def set_favorite(self, dns_id, value):
        self._q("UPDATE dns SET is_favorite=? WHERE id=?", (1 if value else 0, dns_id), commit=True)

    def set_pinned(self, dns_id, value):
        self._q("UPDATE dns SET is_pinned=? WHERE id=?", (1 if value else 0, dns_id), commit=True)

    def move_dns(self, dns_id, group_id):
        self._q("UPDATE dns SET group_id=? WHERE id=?", (group_id, dns_id), commit=True)

    # ------------------------------------------------------------------ results
    def save_result(self, dns_id, res, role="primary"):
        self._q("""INSERT INTO results(dns_id,role,status,sent,success,last_ping,avg_ping,jitter,loss,samples,tested_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(dns_id,role) DO UPDATE SET
                   status=excluded.status, sent=excluded.sent, success=excluded.success,
                   last_ping=excluded.last_ping, avg_ping=excluded.avg_ping, jitter=excluded.jitter,
                   loss=excluded.loss, samples=excluded.samples, tested_at=excluded.tested_at""",
                (dns_id, role, res["status"], res["sent"], res["success"], res["last"], res["avg"], res["jitter"],
                 res["loss"], json.dumps(res["samples"]), datetime.now().isoformat(timespec="seconds")),
                commit=True)

    @staticmethod
    def _result_row(r):
        try:
            samples = json.loads(r["samples"] or "[]")
        except ValueError:
            samples = []
        return dict(dns_id=r["dns_id"], role=r["role"], status=r["status"], sent=r["sent"], success=r["success"],
                    last=r["last_ping"], avg=r["avg_ping"], jitter=r["jitter"], loss=r["loss"],
                    samples=samples, tested_at=r["tested_at"])

    def get_result(self, dns_id, role="primary"):
        rows = self._all("SELECT * FROM results WHERE dns_id=? AND role=?", (dns_id, role))
        return self._result_row(rows[0]) if rows else None

    def results_map(self, dns_ids, role="primary"):
        out = {}
        for i in dns_ids:
            r = self.get_result(i, role)
            if r:
                out[i] = r
        return out

    def delete_result(self, dns_id):
        self._q("DELETE FROM results WHERE dns_id=?", (dns_id,), commit=True)

    def clear_results(self):
        self._q("DELETE FROM results", commit=True)
