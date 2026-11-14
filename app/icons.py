"""Consistent stroke icon set (24x24 grid), rendered from inline SVG in any colour."""
import math

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def _gear():
    cx = cy = 12
    teeth, ro, ri, pts = 8, 9.6, 7.3, []
    w = math.pi / teeth
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        for ang, r in ((a - w * 0.58, ri), (a - w * 0.34, ro), (a + w * 0.34, ro), (a + w * 0.58, ri)):
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    d = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + "Z"
    return f'<path d="{d}"/><circle cx="12" cy="12" r="3"/>'


BODY = {
    "home": '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M10 20v-5.5h4V20"/>',
    "heart": '<path d="M12 20.5s-8-4.8-8-11A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8 2.5c0 6.2-8 11-8 11z"/>',
    "settings": _gear(),
    "bell": '<path d="M6 16v-5a6 6 0 1 1 12 0v5l1.6 2.2H4.4z"/><path d="M10 21a2 2 0 0 0 4 0"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "check_circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "wifi": '<path d="M2.5 9a15 15 0 0 1 19 0"/><path d="M5.5 12.5a10.5 10.5 0 0 1 13 0"/><path d="M8.7 16a6 6 0 0 1 6.6 0"/><circle cx="12" cy="19.5" r="1.1" fill="{c}"/>',
    "wifi_off": '<path d="M3 3l18 18"/><path d="M2.5 9a15 15 0 0 1 4.6-2.8"/><path d="M10 5.2A15 15 0 0 1 21.5 9"/><path d="M5.5 12.5a10.5 10.5 0 0 1 3.6-2.2"/><path d="M13.8 10a10.5 10.5 0 0 1 4.7 2.5"/><path d="M8.7 16a6 6 0 0 1 6.6 0"/><circle cx="12" cy="19.5" r="1.1" fill="{c}"/>',
    "layers": '<path d="M12 3 3 8l9 5 9-5z"/><path d="M3 12.5l9 5 9-5"/><path d="M3 17l9 5 9-5"/>',
    "server": '<rect x="3" y="4" width="18" height="7" rx="2.2"/><rect x="3" y="13" width="18" height="7" rx="2.2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
    "zap": '<path d="M13 2.5 4.5 14H11l-1 7.5L19.5 10H13z"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><circle cx="17.5" cy="9" r="2.5"/><path d="M17 14c2.7 0 4.5 1.9 4.5 4.5"/>',
    "play": '<path d="M7 5v14l12-7z" fill="{c}"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2.5" fill="{c}"/>',
    "star": '<path d="M12 3l2.8 5.8 6.2.9-4.5 4.4 1.1 6.2L12 17.4 6.4 20.3l1.1-6.2L3 9.7l6.2-.9z"/>',
    "star_fill": '<path d="M12 3l2.8 5.8 6.2.9-4.5 4.4 1.1 6.2L12 17.4 6.4 20.3l1.1-6.2L3 9.7l6.2-.9z" fill="{c}"/>',
    "pin": '<path d="M9 3.5h6l-1 5.5 3 3.2V14.5H7v-2.3L10 9z"/><path d="M12 14.5V21"/>',
    "pin_fill": '<path d="M9 3.5h6l-1 5.5 3 3.2V14.5H7v-2.3L10 9z" fill="{c}"/><path d="M12 14.5V21"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>',
    "pencil": '<path d="M4 20l1-4.2L16 4.8a1.6 1.6 0 0 1 2.2 0l1 1a1.6 1.6 0 0 1 0 2.2L8.2 19z"/><path d="M14 7l3 3"/>',
    "chevron_down": '<path d="M6 9l6 6 6-6"/>',
    "chevron_right": '<path d="M9 6l6 6-6 6"/>',
    "chevron_left": '<path d="M15 6l-6 6 6 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M12 7.6v.01"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "timer": '<circle cx="12" cy="14" r="7"/><path d="M12 14V10.5"/><path d="M9.5 3h5"/><path d="M12 3v4"/>',
    "pie": '<circle cx="12" cy="12" r="9"/><path d="M12 3v9h9"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.6 2.6 3.9 5.6 3.9 9s-1.3 6.4-3.9 9c-2.6-2.6-3.9-5.6-3.9-9S9.4 5.6 12 3z"/>',
    "shield_check": '<path d="M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "folder": '<path d="M3 6.5a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "folder_plus": '<path d="M3 6.5a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10.5v5M9.5 13h5"/>',
    "power": '<path d="M12 3v9"/><path d="M6.6 6.6a8 8 0 1 0 10.8 0"/>',
    "more": '<circle cx="5" cy="12" r="1.4" fill="{c}"/><circle cx="12" cy="12" r="1.4" fill="{c}"/><circle cx="19" cy="12" r="1.4" fill="{c}"/>',
    "square": '<rect x="5" y="5" width="14" height="14" rx="2.5"/>',
    "restore": '<rect x="4" y="8" width="12" height="12" rx="2.2"/><path d="M8 8V6.2A2.2 2.2 0 0 1 10.2 4h7.6A2.2 2.2 0 0 1 20 6.2v7.6a2.2 2.2 0 0 1-2.2 2.2H16"/>',
    "tray": '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5.5 5h13L21 13v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5z"/>',
    "sort": '<path d="M8 4v16M4.5 7.5 8 4l3.5 3.5"/><path d="M16 20V4M12.5 16.5 16 20l3.5-3.5"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.5-3.5L4 9"/><path d="M4 4v5h5"/><path d="M4 13a8 8 0 0 0 14.5 3.5L20 15"/><path d="M20 20v-5h-5"/>',
    "alert": '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5"/><path d="M12 17.4v.01"/>',
    "moon": '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4 7 7 0 0 0 20 14.5z"/>',
    "folder_open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1H3z"/><path d="M3 10h19l-2 8a2 2 0 0 1-2 1.5H5a2 2 0 0 1-2-2z"/>',
    "github": '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M13.5 5l-3 14"/>',
    "send": '<path d="M21 3 3 10.5l7 2.5 2.5 7z"/><path d="M10 13l11-10"/>',
    "megaphone": '<path d="M4 10v4a1 1 0 0 0 1 1h3l8 4V5L8 9H5a1 1 0 0 0-1 1z"/><path d="M19.5 9.5a4 4 0 0 1 0 5"/>',
    "broom": '<path d="M20 4l-7 7"/><path d="M11.16 9.16l3.68 3.68L10.52 19.84 4.16 13.48z"/><path d="M12.4 10.4 6.3 15.6M13.6 11.6l-5.2 6.1"/>',
    "droplet": '<path d="M12 3s6.5 6.6 6.5 11.2a6.5 6.5 0 0 1-13 0C5.5 9.6 12 3 12 3z"/><path d="M9 14.5a3 3 0 0 0 3 3"/>',
    "trophy": '<path d="M8 4h8v5a4 4 0 0 1-8 0z"/><path d="M8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4"/><path d="M12 13v4M8.5 20h7"/>',
}

_cache = {}


def pixmap(name: str, color: str, size: int = 22, stroke: float = 2.0, dpr: float = 2.0) -> QPixmap:
    key = (name, color, size, stroke, dpr)
    pm = _cache.get(key)
    if pm is not None:
        return pm
    body = BODY[name].replace("{c}", color)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    _cache[key] = pm
    return pm


def icon(name: str, color: str, size: int = 22, stroke: float = 2.0) -> QIcon:
    return QIcon(pixmap(name, color, size, stroke))


# ----------------------------------------------------------------------------- 3D (iOS-style) nav icons
def _gear_poly(cx=12.0, cy=12.0, teeth=8, ro=10.0, ri=7.7):
    pts, w = [], math.pi / teeth
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        for ang, r in ((a - w * 0.62, ri), (a - w * 0.36, ro), (a + w * 0.36, ro), (a + w * 0.62, ri)):
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + "Z"


# shapes use {P} for the paint (gradient or shadow black); details are drawn only on the main layer
_NAV_SHAPES = {
    "home": ('<path d="M12 3.3 21 11.1V19a2.2 2.2 0 0 1-2.2 2.2H5.2A2.2 2.2 0 0 1 3 19v-7.9z" fill="{P}" stroke="{P}" stroke-width="1.4" stroke-linejoin="round"/>'
             '<rect x="16.1" y="4.6" width="2.4" height="4.6" rx="0.8" fill="{P}"/>'),
    "heart": '<path d="M12 21s-9-5.2-9-11.6A5 5 0 0 1 12 6.6a5 5 0 0 1 9 2.8C21 15.8 12 21 12 21z" fill="{P}" stroke="{P}" stroke-width="0.8" stroke-linejoin="round"/>',
    "settings": f'<path d="{_gear_poly()}" fill="{{P}}" stroke="{{P}}" stroke-width="1.1" stroke-linejoin="round"/>',
}
_NAV_DETAILS = {
    "home": ('<path d="M12 4.1 19.7 10.9H4.3z" fill="#fff" fill-opacity="{lo}"/>'
             '<path d="M4.5 10.9 11.6 4.6" stroke="#fff" stroke-opacity="{hi}" stroke-width="1.1" stroke-linecap="round" fill="none"/>'
             '<path d="M3.6 11.5h16.8" stroke="#000" stroke-opacity="0.14" stroke-width="0.9" fill="none"/>'
             '<rect x="9.6" y="14.2" width="4.8" height="8" rx="1.6" fill="{cut}"/>'),
    "heart": ('<ellipse cx="7.7" cy="9.3" rx="2.5" ry="1.5" transform="rotate(-38 7.7 9.3)" fill="#fff" fill-opacity="{hi}"/>'
              '<path d="M12 19c-3.6-2.4-6.6-5.2-7.4-8.2" stroke="#000" stroke-opacity="0.10" stroke-width="1.4" fill="none" stroke-linecap="round"/>'),
    "settings": ('<circle cx="12" cy="12" r="3.5" fill="{cut}"/>'
                 '<circle cx="12" cy="12" r="3.5" fill="none" stroke="#000" stroke-opacity="0.18" stroke-width="0.8"/>'
                 '<path d="M5.6 8.3A7.2 7.2 0 0 1 11.2 4.9" stroke="#fff" stroke-opacity="{hi}" stroke-width="1.2" fill="none" stroke-linecap="round"/>'),
}
_nav_cache = {}


def nav_pixmap(name: str, active: bool, top: str, bottom: str, cut: str, size: int = 30, dpr: float = 2.0) -> QPixmap:
    key = (name, active, top, bottom, cut, size, dpr)
    pm = _nav_cache.get(key)
    if pm is not None:
        return pm
    shape = _NAV_SHAPES[name]
    hi, lo = ("0.55", "0.20") if active else ("0.28", "0.10")
    shadow = ""
    if active:        # soft drop shadow under the glyph gives the 3D lift
        shadow = f'<g transform="translate(0 1)" opacity="0.30">{shape.replace("{P}", "#000")}</g>'
    details = _NAV_DETAILS[name].replace("{cut}", cut).replace("{hi}", hi).replace("{lo}", lo)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/>'
           f'<stop offset="1" stop-color="{bottom}"/></linearGradient></defs>'
           f'{shadow}{shape.replace("{P}", "url(#g)")}{details}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    _nav_cache[key] = pm
    return pm
