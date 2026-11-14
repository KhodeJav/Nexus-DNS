"""Reusable custom widgets."""
import math

from PySide6.QtCore import (QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Property, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QIntValidator, QLinearGradient, QPainter, QPainterPath,
                           QPalette, QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QPushButton, QSizePolicy, QStyle, QStyledItemDelegate, QWidget)

from .dns_icons import badge, identify
from .icons import nav_pixmap, pixmap
from .skin import col, qcol, skin, tr


# ------------------------------------------------------------------------------ icons
class IconLabel(QLabel):
    def __init__(self, name, color="sub", size=20, parent=None):
        super().__init__(parent)
        self._name, self._color, self._size = name, color, size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        skin.changed.connect(self.refresh)
        self.refresh()

    def set_icon(self, name, color=None):
        self._name = name
        if color:
            self._color = color
        self.refresh()

    def refresh(self):
        self.setPixmap(pixmap(self._name, col(self._color), self._size))


class IconChip(QLabel):
    """Rounded square with a coloured icon (the little badges next to titles)."""

    def __init__(self, name, color="accent2", size=42, icon_size=21, parent=None):
        super().__init__(parent)
        self.setObjectName("chip")
        self._name, self._color, self._isz = name, color, icon_size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        skin.changed.connect(self.refresh)
        self.refresh()

    def set_icon(self, name, color=None):
        self._name = name
        if color:
            self._color = color
        self.refresh()

    def refresh(self):
        self.setPixmap(pixmap(self._name, col(self._color), self._isz))


class IconButton(QPushButton):
    def __init__(self, name, color="sub", size=20, tooltip=None, parent=None, object_name="iconbtn", pad=14):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._name, self._color, self._size, self._tip = name, color, size, tooltip
        self.setFixedSize(size + pad, size + pad)
        self.setIconSize(QSize(size, size))
        skin.changed.connect(self.refresh)
        self.refresh()

    def set_icon(self, name, color=None):
        self._name = name
        if color:
            self._color = color
        self.refresh()

    def set_tooltip_key(self, key):
        self._tip = key
        self.refresh()

    def refresh(self):
        from .icons import icon
        self.setIcon(icon(self._name, col(self._color), self._size))
        if self._tip:
            self.setToolTip(tr(self._tip))


# ------------------------------------------------------------------------------ containers
class Card(QFrame):
    def __init__(self, object_name="card", parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)


class ClickableCard(Card):
    clicked = Signal()

    def __init__(self, object_name="card", parent=None):
        super().__init__(object_name, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._pressed = False

    def mousePressEvent(self, e):
        self._pressed = e.button() == Qt.LeftButton
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        was, self._pressed = self._pressed, False
        if was and e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


def hline():
    f = QFrame()
    f.setObjectName("sep")
    f.setFrameShape(QFrame.NoFrame)
    return f


def vline():
    f = QFrame()
    f.setObjectName("vsep")
    f.setFrameShape(QFrame.NoFrame)
    return f


def label(text="", role=None, wrap=False, align=None):
    l = QLabel(text)
    if role:
        l.setProperty("role", role)
    l.setWordWrap(wrap)
    if align:
        l.setAlignment(align)
    return l


class FitLabel(QLabel):
    """Single-line label that never forces the layout wider: when the text does not fit it
    shrinks its own font (numbers such as IP addresses stay fully visible)."""
    MIN_SCALE = 0.5

    def __init__(self, text="", role=None, align=None, parent=None):
        super().__init__(parent)
        if role:
            self.setProperty("role", role)
        if align is not None:
            self.setAlignment(align)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        super().setText(text)

    def setText(self, text):
        super().setText(text)
        self.updateGeometry()
        self.update()

    def changeEvent(self, e):
        if e.type() in (QEvent.FontChange, QEvent.StyleChange):
            self.updateGeometry()
        super().changeEvent(e)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text()) + 4, fm.height() + 2)

    def minimumSizeHint(self):
        return QSize(12, self.sizeHint().height())

    def paintEvent(self, e):
        text, w = self.text(), max(1, self.width() - 4)
        f = QFont(self.font())
        base = f.pointSizeF() if f.pointSizeF() > 0 else float(f.pixelSize())
        size = base
        # shrink step by step until the text really fits (font sizes are rounded, so measure the result)
        while QFontMetrics(f).horizontalAdvance(text) > w and size > base * self.MIN_SCALE:
            size *= 0.95
            if f.pointSizeF() > 0:
                f.setPointSizeF(size)
            else:
                f.setPixelSize(max(6, int(size)))
        p = QPainter(self)
        p.setFont(f)
        p.setPen(self.palette().color(QPalette.WindowText))
        text = QFontMetrics(f).elidedText(text, Qt.ElideRight, w)
        has_rtl = any("\u0590" <= ch <= "\u08ff" for ch in text)      # Persian/Arabic -> RTL, otherwise LTR
        p.setLayoutDirection(Qt.RightToLeft if has_rtl else Qt.LeftToRight)
        p.drawText(self.rect().adjusted(2, 0, -2, 0), int(QStyle.visualAlignment(self.layoutDirection(), self.alignment())), text)


class ElidedLabel(QLabel):
    """Single-line label that elides instead of stretching the layout."""

    def __init__(self, text="", role=None, parent=None):
        super().__init__(parent)
        if role:
            self.setProperty("role", role)
        self._full = ""
        self.setMinimumWidth(10)
        self.setText(text)

    def setText(self, text):
        self._full = text or ""
        self.setToolTip("")
        self._apply()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()

    def _apply(self):
        w = max(10, self.width())
        el = self.fontMetrics().elidedText(self._full, Qt.ElideRight, w)
        super().setText(el)
        self.setToolTip(self._full if el != self._full else "")


# ------------------------------------------------------------------------------ inputs
class _ComboRowDelegate(QStyledItemDelegate):
    """One flat row of the themed combo list: no OS highlight, only our colours."""

    def __init__(self, height, parent=None):
        super().__init__(parent)
        self._h = height

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self._h)

    def paint(self, p, option, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(2, 2, -2, -2)
        combo = self.parent()                                # the popup's highlight follows the mouse; "current" is the real choice
        current = index.row() == combo.currentIndex()
        hover = bool(option.state & (QStyle.State_MouseOver | QStyle.State_Selected)) and not current
        if hover or current:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col("hover" if hover else "chip")))
            p.drawRoundedRect(r, 10, 10)
        f = QFont(option.font)
        f.setBold(current)
        p.setFont(f)
        p.setPen(QColor(col("accent2" if current else "text")))
        p.drawText(r, Qt.AlignCenter, index.data(Qt.DisplayRole) or "")
        p.restore()


class Combo(QComboBox):
    """Combo box with our own chevron (QSS can't draw SVG arrows)."""

    ROW_H, PAD = 38, 6

    def use_styled_popup(self):
        """Opt-in: minimal themed drop-down - rounded panel, centred rows, soft hover, current item tinted."""
        self._styled = True
        self.setView(QListView())
        self.setMaxVisibleItems(8)
        self.setItemDelegate(_ComboRowDelegate(self.ROW_H, self))
        box = self.view().parentWidget()                     # the popup frame that holds the list
        box.setWindowFlags(box.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        box.setAttribute(Qt.WA_TranslucentBackground, True)
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view().setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view().setMouseTracking(True)
        self._style_popup()
        skin.changed.connect(self._style_popup)

    def _style_popup(self):
        self.view().parentWidget().setStyleSheet("QFrame { background: transparent; border: none; }")
        self.view().setStyleSheet(
            f"QListView {{ background: {col('panel')}; border: 1px solid {col('border')}; border-radius: 14px;"
            f" padding: {self.PAD}px; outline: 0; }}")

    def showPopup(self):
        super().showPopup()
        if getattr(self, "_styled", False):                  # exact size, placed right under the combo
            box = self.view().parentWidget()
            rows = max(1, min(self.count(), self.maxVisibleItems()))
            box.setFixedSize(self.width(), rows * self.ROW_H + 2 * self.PAD + 2)
            box.move(self.mapToGlobal(QPoint(0, self.height() + 6)))

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        pm = pixmap("chevron_down", col("sub"), 16)
        x = 10 if self.isRightToLeft() else self.width() - 26
        p.drawPixmap(x, (self.height() - 16) // 2, pm)


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(52, 30)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._on_toggled)

    def _get(self):
        return self._pos

    def _set(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def set_checked_silent(self, value):
        self.blockSignals(True)
        self.setChecked(bool(value))
        self.blockSignals(False)
        self._pos = 1.0 if value else 0.0
        self.update()

    def _on_toggled(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on = QColor(col("border")), QColor(col("accent"))
        t = self._pos
        c = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                   int(off.blue() + (on.blue() - off.blue()) * t))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        k = r.height() - 6
        frac = (1 - t) if self.isRightToLeft() else t
        x = r.left() + 3 + (r.width() - k - 6) * frac
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, r.top() + 3, k, k))


class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, items, parent=None):
        """items: [(key, text, translate?)]"""
        super().__init__(parent)
        self.setObjectName("seg")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._btns = {}
        self._items = items
        for key, text, translate in items:
            b = QPushButton()
            b.setObjectName("segbtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self._group.addButton(b)
            lay.addWidget(b)
            self._btns[key] = b
        skin.changed.connect(self.refresh)
        self.refresh()

    def set_current(self, key):
        if key in self._btns:
            self._btns[key].setChecked(True)

    def refresh(self):
        for key, text, translate in self._items:
            self._btns[key].setText(tr(text) if translate else text)


class Stepper(QFrame):
    """[-]  value  [+]  - clearer than the tiny native spin arrows."""
    valueChanged = Signal(int)

    def __init__(self, lo, hi, step=1, parent=None):
        super().__init__(parent)
        self._lo, self._hi, self._step, self._val = lo, hi, step, lo
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.minus = IconButton("minus", "text", 14, object_name="iconbox", pad=16)
        self.plus = IconButton("plus", "text", 14, object_name="iconbox", pad=16)
        self.edit = QLineEdit(str(lo))
        self.edit.setValidator(QIntValidator(0, 99999, self))
        self.edit.setAlignment(Qt.AlignCenter)
        self.edit.setFixedSize(60, 40)
        self.edit.setStyleSheet("padding: 0px; font-weight: 700; font-size: 11pt;")
        self.edit.setLayoutDirection(Qt.LeftToRight)
        lay.addWidget(self.minus)
        lay.addWidget(self.edit)
        lay.addWidget(self.plus)
        self.minus.clicked.connect(lambda: self._commit(self._val - self._step))
        self.plus.clicked.connect(lambda: self._commit(self._val + self._step))
        self.edit.editingFinished.connect(self._typed)

    def _typed(self):
        try:
            self._commit(int(self.edit.text()))
        except ValueError:
            self._commit(self._val)

    def _commit(self, v):
        v = max(self._lo, min(self._hi, v))
        changed = v != self._val
        self._val = v
        self.edit.setText(str(v))
        if changed:
            self.valueChanged.emit(v)

    def value(self):
        return self._val

    def set_value(self, v):
        self._val = max(self._lo, min(self._hi, v))
        self.edit.setText(str(self._val))


# ------------------------------------------------------------------------------ avatar
class Avatar(QWidget):
    """DNS provider badge (see dns_icons). Identified by name and IP; unknown -> default globe badge."""

    def __init__(self, name="", size=40, ip=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size = size
        self._key = identify(name, ip or "")

    def set_name(self, name, ip=None):
        self._key = identify(name, ip or "")
        self.update()

    def paintEvent(self, e):
        QPainter(self).drawPixmap(0, 0, badge(self._key, self._size))


class StatusBadge(QWidget):
    """Big round status icon in the connection card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 46)
        self._state = "checking"

    def set_state(self, state):
        self._state = state
        self.update()

    def paintEvent(self, e):
        color = {"online": "good", "domestic": "warn", "offline": "bad"}.get(self._state, "off")
        icon = {"online": "check", "domestic": "alert", "offline": "x"}.get(self._state, "refresh")
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(col(color)))
        p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        pm = pixmap(icon, "#ffffff", 24, 2.6)
        p.drawPixmap((self.width() - 24) // 2, (self.height() - 24) // 2, pm)


# ------------------------------------------------------------------------------ chart
class PingChart(QWidget):
    """Ping history: ONE continuous line + filled area attached to the bottom.

    - the line changes colour with the value (green -> yellow -> red), smoothly, without ever breaking
    - a lost packet is part of the line too: it jumps to the top (worst level) in red, so the chart
      stays connected however many packets were lost
    - long histories are reduced to a fixed number of points, and the picture is cached: it is only
      redrawn when the data, size or theme changes
    """
    MAX_POINTS = 160
    GOOD_MS, WARN_MS, BAD_MS = 80.0, 160.0, 220.0       # same thresholds as the result grades

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(96)
        self._vals = []
        self._cache = None
        self._cache_key = None
        skin.changed.connect(self._invalidate)

    def set_values(self, vals, color=None):
        self._vals = list(vals or [])
        self._invalidate()

    def _invalidate(self):
        self._cache_key = None
        self.update()

    # ---- helpers
    @classmethod
    def _reduce(cls, vals):
        n = len(vals)
        if n <= cls.MAX_POINTS:
            return vals
        step = -(-n // cls.MAX_POINTS)
        out = []
        for i in range(0, n, step):
            chunk = vals[i:i + step]
            good = [v for v in chunk if v is not None]
            # keep spikes (max); a group only counts as "lost" when at least half of it was lost
            out.append(None if not good or len(good) * 2 <= len(chunk) else max(good))
        return out

    @classmethod
    def _colour(cls, v):
        good, warn, bad = QColor(col("good")), QColor(col("warn")), QColor(col("bad"))
        if v is None or v >= cls.BAD_MS:
            return bad
        if v <= cls.GOOD_MS:
            return good

        def mix(a, b, t):
            return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                          int(a.blue() + (b.blue() - a.blue()) * t))
        if v <= (cls.GOOD_MS + cls.WARN_MS) / 2:                       # green -> yellow
            return mix(good, warn, (v - cls.GOOD_MS) / ((cls.WARN_MS - cls.GOOD_MS) / 2))
        if v <= cls.WARN_MS:
            return warn
        return mix(warn, bad, (v - cls.WARN_MS) / (cls.BAD_MS - cls.WARN_MS))   # yellow -> red

    @staticmethod
    def _smooth(pts, y0, y1):
        path = QPainterPath(pts[0])
        n = len(pts)
        for i in range(n - 1):
            p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n - 1)]
            c1y = min(max(p1.y() + (p2.y() - p0.y()) / 6, y0), y1)
            c2y = min(max(p2.y() - (p3.y() - p1.y()) / 6, y0), y1)
            path.cubicTo(QPointF(p1.x() + (p2.x() - p0.x()) / 6, c1y), QPointF(p2.x() - (p3.x() - p1.x()) / 6, c2y), p2)
        return path

    # ---- rendering (cached)
    def _render(self, dpr):
        w, h = self.width(), self.height()
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()                                  # follow the card's rounded top corners
        clip.addRoundedRect(QRectF(0, 0, w, h + 30), 21, 21)
        p.setClipPath(clip)
        top, bottom = 10.0, float(h)
        height = bottom - top
        vals = self._reduce(self._vals)
        ok = [v for v in vals if v is not None]

        if len(vals) < 2 or not ok:                            # gentle placeholder wave
            pts = [QPointF(w * i / 24, top + height * 0.5 + math.sin(i / 3.2) * height * 0.22) for i in range(25)]
            c = QColor(col("accent"))
            c.setAlpha(60)
            p.setPen(QPen(c, 2.2))
            p.drawPath(self._smooth(pts, top, bottom))
            p.end()
            return pm

        lo, hi = min(ok), max(ok)
        span = max(hi - lo, 12.0)
        has_lost = len(ok) != len(vals)
        y_low = bottom - height * 0.10                         # best value sits near the bottom
        y_high = top + height * (0.30 if has_lost else 0.10)   # worst real value (room above for losses)
        y_lost = top + height * 0.06                           # a lost packet = the top of the chart
        step = w / (len(vals) - 1)
        pts, stops = [], []
        for i, v in enumerate(vals):
            y = y_lost if v is None else y_low - (v - lo) / span * (y_low - y_high)
            pts.append(QPointF(i * step, y))
            stops.append((i / (len(vals) - 1), self._colour(v)))

        line = self._smooth(pts, top, bottom)

        def horizontal(alpha):
            g = QLinearGradient(0, 0, w, 0)
            for pos, c in stops:
                cc = QColor(c)
                cc.setAlpha(alpha)
                g.setColorAt(min(max(pos, 0.0), 1.0), cc)
            return g

        # area: colour follows the line, fades towards the bottom, stays attached to the bottom edge
        area = QPainterPath(line)
        area.lineTo(pts[-1].x(), bottom + 2)
        area.lineTo(pts[0].x(), bottom + 2)
        area.closeSubpath()
        layer = QPixmap(int(w * dpr), int(h * dpr))
        layer.setDevicePixelRatio(dpr)
        layer.fill(Qt.transparent)
        lp = QPainter(layer)
        lp.setRenderHint(QPainter.Antialiasing)
        lp.fillPath(area, QBrush(horizontal(255)))
        lp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        fade = QLinearGradient(0, top, 0, bottom)
        fade.setColorAt(0, QColor(0, 0, 0, 105))
        fade.setColorAt(1, QColor(0, 0, 0, 0))
        lp.fillRect(QRectF(0, 0, w, h), fade)
        lp.end()
        p.drawPixmap(0, 0, layer)

        pen = QPen(QBrush(horizontal(255)), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(line)
        if len(vals) <= 60:                                    # mark lost packets on the line
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col("bad")))
            for pt, v in zip(pts, vals):
                if v is None:
                    p.drawEllipse(pt, 3.0, 3.0)
        p.end()
        return pm

    def paintEvent(self, e):
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr)
        if self._cache is None or self._cache_key != key:
            self._cache, self._cache_key = self._render(dpr), key
        QPainter(self).drawPixmap(0, 0, self._cache)


# ------------------------------------------------------------------------------ navigation
class NavButton(QAbstractButton):
    def __init__(self, icon_name, text_key, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._icon, self._key = icon_name, text_key
        self.setMinimumHeight(64)
        skin.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.setText(tr(self._key))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        c = col("accent2") if on else col("sub")
        top, bottom = (col("accent2"), col("accent")) if on else (col("off"), QColor(col("off")).darker(150).name())
        pm = nav_pixmap(self._icon, on, top, bottom, col("card"), 30)
        p.drawPixmap((self.width() - 30) // 2, 6, pm)
        f = QFont(self.font())
        f.setPointSizeF(9)
        f.setBold(on)
        p.setFont(f)
        p.setPen(QColor(c))
        p.drawText(QRectF(0, 36, self.width(), 20), Qt.AlignCenter, self.text())
        if on:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col("accent2")))
            w = self.width() * 0.62
            p.drawRoundedRect(QRectF((self.width() - w) / 2, self.height() - 6, w, 3.5), 1.7, 1.7)


class NavBar(QFrame):
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navbar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(0)
        self._btns = []
        for i, (ic, key) in enumerate((("home", "nav_home"), ("heart", "nav_fav"), ("settings", "nav_settings"))):
            b = NavButton(ic, key)
            b.clicked.connect(lambda _=False, idx=i: self.set_current(idx, True))
            lay.addWidget(b, 1)
            self._btns.append(b)
        self.set_current(0)

    def set_current(self, idx, emit=False):
        for i, b in enumerate(self._btns):
            b.setChecked(i == idx)
            b.update()
        if emit:
            self.currentChanged.emit(idx)


# ------------------------------------------------------------------------------ toast
class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def show_message(self, text, kind="info", ms=3200):
        bg = {"ok": col("good"), "error": col("bad"), "warn": "#b8860b"}.get(kind, col("accent"))
        self.setStyleSheet(f"QLabel#toast {{ background: {bg}; color: white; border-radius: 16px; "
                           f"padding: 12px 18px; font-weight: 600; }}")
        self.setText(text)
        host = self.parentWidget()
        w = min(host.width() - 60, 380)
        self.setFixedWidth(max(w, 200))
        self.adjustSize()
        self.move((host.width() - self.width()) // 2, host.height() - self.height() - 110)
        self.show()
        self.raise_()
        self._timer.start(ms)


def centered(body, max_width):
    """Wrap a page body so it never stretches past max_width (full-screen windows stay tidy)."""
    body.setMaximumWidth(max_width)
    outer = QWidget()
    lay = QHBoxLayout(outer)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addStretch(1)
    lay.addWidget(body, 100)
    lay.addStretch(1)
    return outer
