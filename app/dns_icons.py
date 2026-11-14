"""One consistent icon language for DNS providers.

Every icon is the same glossy round badge: a brand-coloured gradient with a white glyph.
Unknown / user-added DNS get the default purple globe badge. Icons are identified by name
and by IP, and any file placed in assets/dns_icons/<key>.png|svg overrides the drawn one.
"""
import os

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .paths import resource_path

_CLOUD = '<path d="M7.2 18h9.6a3.6 3.6 0 0 0 .5-7.16A5.2 5.2 0 0 0 7.3 9.9 4.1 4.1 0 0 0 7.2 18z" fill="#fff"/>'
_UMBRELLA = ('<path d="M3 12.5a9 9 0 0 1 18 0z" fill="#fff"/>'
             '<path d="M12 12.5v6a2 2 0 0 1-4 0" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/>')
_SHIELD = '<path d="M12 3l7.5 2.8v5.7c0 4.2-3 7.5-7.5 9.2-4.5-1.7-7.5-5-7.5-9.2V5.8z" fill="#fff"/>'
_SHIELD_CHECK = _SHIELD + '<path d="M8.6 12l2.5 2.5 4.4-5" stroke="{bg}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
_BOLT = '<path d="M13.2 2.5 5.5 13.6H11l-1 7.9 8.5-11.6H13z" fill="#fff"/>'
_SIGNAL = ('<rect x="3.5" y="14" width="3.4" height="6" rx="1.2" fill="#fff"/><rect x="8.5" y="10.5" width="3.4" height="9.5" rx="1.2" fill="#fff"/>'
           '<rect x="13.5" y="7" width="3.4" height="13" rx="1.2" fill="#fff"/><rect x="18.5" y="3.5" width="3.4" height="16.5" rx="1.2" fill="#fff"/>')
_PHONE = '<path d="M6.8 3.6l3.1.8.9 3.7-2.1 1.6a11.2 11.2 0 0 0 5.2 5.2l1.6-2.1 3.7.9.8 3.1a2 2 0 0 1-2 2.5C10.7 19 5.1 13.3 4.3 5.6a2 2 0 0 1 2.5-2z" fill="#fff"/>'
_GLOBE = ('<circle cx="12" cy="12" r="8.2" stroke="#fff" stroke-width="1.8" fill="none"/>'
          '<path d="M3.8 12h16.4" stroke="#fff" stroke-width="1.6" fill="none"/>'
          '<path d="M12 3.8c2.3 2.4 3.4 5.1 3.4 8.2s-1.1 5.8-3.4 8.2c-2.3-2.4-3.4-5.1-3.4-8.2S9.7 6.2 12 3.8z" stroke="#fff" stroke-width="1.6" fill="none"/>')

# key: (gradient top, gradient bottom, kind, glyph, glyph colour)
BRANDS = {
    "cloudflare": ("#f9a23f", "#e8640c", "svg", _CLOUD, "#fff"),
    "google": ("#ffffff", "#e2e6ec", "text", "G", "#4285f4"),
    "quad9": ("#3d50c8", "#1b2878", "text", "9", "#fff"),
    "opendns": ("#f9961f", "#dd6a00", "svg", _UMBRELLA, "#fff"),
    "adguard": ("#6fc47d", "#389548", "svg", _SHIELD_CHECK, "#fff"),
    "cleanbrowsing": ("#2cc8b2", "#0d8877", "svg", _SHIELD, "#fff"),
    "controld": ("#7b8cff", "#4a55d6", "text", "CD", "#fff"),
    "yandex": ("#2b2b2b", "#000000", "text", "Y", "#ff3a3a"),
    "shecan": ("#4a95ff", "#1b5ccf", "text", "S", "#fff"),
    "electro": ("#fcc43a", "#ee8a00", "svg", _BOLT, "#fff"),
    "403": ("#f05252", "#9b1239", "text", "403", "#fff"),
    "begzar": ("#3ddc9b", "#0e9d68", "text", "B", "#fff"),
    "gozar": ("#22c7b8", "#0e7a72", "text", "G", "#fff"),
    "dnspro": ("#7a7dfa", "#4339c8", "text", "D", "#fff"),
    "mci": ("#2bc0f5", "#0a74c0", "svg", _SIGNAL, "#fff"),
    "tci": ("#3a78e8", "#143c96", "svg", _PHONE, "#fff"),
    "default": ("#9b72ff", "#5b30e6", "svg", _GLOBE, "#fff"),
}

# order matters ("بگذر" contains "گذر")
NAME_KEYS = [
    (("cloudflare",), "cloudflare"), (("google",), "google"), (("quad9",), "quad9"), (("opendns", "umbrella"), "opendns"),
    (("adguard",), "adguard"), (("cleanbrowsing",), "cleanbrowsing"), (("controld",), "controld"), (("yandex", "یاندکس"), "yandex"),
    (("shecan", "شکن"), "shecan"), (("electro", "الکترو"), "electro"), (("403",), "403"),
    (("begzar", "بگذر"), "begzar"), (("gozar", "گذر"), "gozar"), (("dnspro",), "dnspro"),
    (("mci", "همراهاول", "hamrah"), "mci"), (("tci", "مخابرات", "mokhaberat"), "tci"),
]
IP_KEYS = {
    "1.1.1.1": "cloudflare", "1.0.0.1": "cloudflare", "1.1.1.3": "cloudflare", "1.0.0.3": "cloudflare",
    "1.1.1.2": "cloudflare", "1.0.0.2": "cloudflare", "8.8.8.8": "google", "8.8.4.4": "google",
    "9.9.9.9": "quad9", "149.112.112.112": "quad9", "9.9.9.10": "quad9", "9.9.9.11": "quad9",
    "208.67.222.222": "opendns", "208.67.220.220": "opendns", "94.140.14.14": "adguard", "94.140.15.15": "adguard",
    "185.228.168.9": "cleanbrowsing", "185.228.169.9": "cleanbrowsing", "76.76.2.0": "controld", "76.76.10.0": "controld",
    "178.22.122.100": "shecan", "185.51.200.2": "shecan", "78.157.42.100": "electro", "78.157.42.101": "electro",
    "10.202.10.202": "403", "10.202.10.102": "403", "185.55.226.26": "begzar", "185.55.225.25": "begzar",
    "185.55.224.24": "begzar", "87.107.110.109": "dnspro", "87.107.110.110": "dnspro",
    "217.218.155.155": "tci", "217.218.127.127": "tci",
}


def identify(name: str, ip: str = "") -> str:
    n = (name or "").lower().replace(" ", "")
    for words, key in NAME_KEYS:
        if any(w in n for w in words):
            return key
    ip = (ip or "").strip()
    if ip in IP_KEYS:
        return IP_KEYS[ip]
    if ip.startswith("77.88.8."):
        return "yandex"
    return "default"


_cache = {}
_custom = {}


def _custom_file(key):
    if key not in _custom:
        _custom[key] = next((p for p in (resource_path(f"assets/dns_icons/{key}.png"), resource_path(f"assets/dns_icons/{key}.svg"))
                             if os.path.exists(p)), None)
    return _custom[key]


def badge(key: str, size: int, dpr: float = 2.0) -> QPixmap:
    k = (key, size, dpr)
    pm = _cache.get(k)
    if pm is not None:
        return pm
    top, bottom, kind, glyph, fg = BRANDS.get(key, BRANDS["default"])
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    circle = QPainterPath()
    circle.addEllipse(QRectF(0.5, 0.5, size - 1, size - 1))
    custom = _custom_file(key)
    g = QLinearGradient(0, 0, 0, size)
    g.setColorAt(0, QColor("#ffffff" if custom else top))
    g.setColorAt(1, QColor("#e9ecf2" if custom else bottom))
    p.fillPath(circle, g)
    box = QRectF(size * 0.2, size * 0.2, size * 0.6, size * 0.6)
    if custom:                                           # user-supplied official logo
        if custom.endswith(".svg"):
            QSvgRenderer(custom).render(p, box)
        else:
            src = QPixmap(custom)
            if not src.isNull():
                s = src.scaled(int(box.width() * dpr), int(box.height() * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                p.drawPixmap(int(box.x() + (box.width() - s.width() / dpr) / 2), int(box.y() + (box.height() - s.height() / dpr) / 2), s)
    elif kind == "svg":
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
               + glyph.replace("{bg}", bottom) + "</svg>")
        QSvgRenderer(QByteArray(svg.encode())).render(p, box)
    else:
        f = QFont()
        f.setBold(True)
        f.setPixelSize(int(size * (0.34 if len(glyph) > 2 else 0.30 if len(glyph) == 2 else 0.52)))
        p.setFont(f)
        p.setPen(QColor(fg))
        p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, glyph)
    p.setClipPath(circle)                                # soft top gloss = the "glass" look shared by all icons
    gloss = QLinearGradient(0, 0, 0, size * 0.55)
    gloss.setColorAt(0, QColor(255, 255, 255, 70))
    gloss.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(0, 0, size, size * 0.55), gloss)
    p.setClipping(False)
    p.setPen(QColor(0, 0, 0, 40))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(0.5, 0.5, size - 1, size - 1))
    p.end()
    _cache[k] = pm
    return pm
