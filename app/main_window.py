"""Frameless main window: title bar, pages, bottom navigation, tray, internet monitor."""
import logging
import time
from collections import deque
from datetime import datetime

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap, QRadialGradient
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QMenu, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import windows_dns as wd
from .dialogs import LogDialog
from .paths import resource_path
from .skin import col, skin, tr
from .widgets import IconButton, NavBar, Toast
from .workers import NetThread, reconcile_connection
from .pages.favorites import FavoritesPage
from .pages.home import HomePage
from .pages.settings import SettingsPage

log = logging.getLogger("dnschanger.window")
M = 8   # transparent margin = resize handles + shadow


class InternetMonitor(QObject):
    checked = Signal(object)
    went_online = Signal()
    went_offline = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status, self.last_ts, self._thread = None, 0.0, None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_now)

    @property
    def online(self):
        return bool(self.status and self.status.online)

    INTERVAL_MS = 15000

    def start(self):
        self.check_now()
        self._timer.start(self.INTERVAL_MS)

    def pause(self):
        """No background traffic while DNS benchmarks run (keeps their numbers clean)."""
        self._timer.stop()

    def resume(self):
        if not self._timer.isActive():
            self._timer.start(self.INTERVAL_MS)

    def check_now(self):
        if self._thread:
            return
        t = NetThread(self)
        t.result.connect(self._on_result)
        t.finished.connect(self._cleanup)
        self._thread = t
        t.start()

    def _cleanup(self):
        t, self._thread = self._thread, None
        if t:
            t.deleteLater()

    def _on_result(self, st):
        was = self.status.online if self.status else None
        self.status, self.last_ts = st, time.time()
        if was is not None and was != st.online:
            (self.went_online if st.online else self.went_offline).emit()
        self.checked.emit(st)

    def shutdown(self):
        self._timer.stop()
        if self._thread:
            self._thread.wait(4000)


class BlurOverlay(QWidget):
    """Frosted-glass backdrop shown behind pop-ups.

    No live graphics effect: the window is grabbed once, shrunk (averaging = blur) and painted
    scaled-up with a tint. While it is visible it costs nothing; the pixmap is freed on hide.
    """
    SHRINK = 7

    def __init__(self, host):
        super().__init__(host)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._small, self._radius = None, 0
        self.hide()

    def show_blur(self, rect, radius):
        host = self.parentWidget()
        pm = host.grab(rect)                                   # one render of the window
        w, h = max(1, pm.width() // self.SHRINK), max(1, pm.height() // self.SHRINK)
        self._small = pm.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._radius = radius
        self.setGeometry(rect)
        self.raise_()
        self.show()

    def hide_blur(self):
        self.hide()
        self._small = None                                     # give the memory back

    def paintEvent(self, e):
        if self._small is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
        p.setClipPath(path)
        p.drawPixmap(self.rect(), self._small)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120) if skin.theme == "dark" else QColor(20, 20, 40, 70))


class EdgeGrip(QWidget):
    CURSORS = {Qt.LeftEdge: Qt.SizeHorCursor, Qt.RightEdge: Qt.SizeHorCursor, Qt.TopEdge: Qt.SizeVerCursor,
               Qt.BottomEdge: Qt.SizeVerCursor}

    def __init__(self, edges, parent):
        super().__init__(parent)
        self.edges = edges
        e = set(Qt.Edge(x) for x in (Qt.LeftEdge, Qt.RightEdge, Qt.TopEdge, Qt.BottomEdge) if edges & x)
        if len(e) == 2:
            diag = (edges & Qt.LeftEdge and edges & Qt.TopEdge) or (edges & Qt.RightEdge and edges & Qt.BottomEdge)
            self.setCursor(Qt.SizeFDiagCursor if diag else Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.SizeHorCursor if edges & (Qt.LeftEdge | Qt.RightEdge) else Qt.SizeVerCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemResize(self.edges)


class TitleBar(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedHeight(40)
        self.setLayoutDirection(Qt.LeftToRight)       # window buttons always on the right
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 6, 10, 0)
        h.setSpacing(2)
        h.addStretch(1)
        self.b_min = IconButton("minus", "text", 16, "tip_min", object_name="winbtn", pad=14)
        self.b_max = IconButton("square", "text", 14, "tip_max", object_name="winbtn", pad=14)
        self.b_close = IconButton("x", "text", 16, "tip_close", object_name="winclose", pad=14)
        self.b_min.clicked.connect(win.showMinimized)
        self.b_max.clicked.connect(win.toggle_max)
        self.b_close.clicked.connect(win.close)
        for b in (self.b_min, self.b_max, self.b_close):
            h.addWidget(b)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.win.windowHandle():
            self.win.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, e):
        self.win.toggle_max()


class MainWindow(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.events = deque(maxlen=100)
        self.really_quit = False
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Nexus DNS")
        self.app_icon = QIcon(resource_path("assets/icon.png"))
        self.setWindowIcon(self.app_icon)
        self.setMinimumSize(440, 640)
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(450 + 2 * M, min(920, screen.height() - 60))

        self.monitor = InternetMonitor(self)
        self.monitor.went_online.connect(lambda: self.log_event(tr("ev_online"), "ok"))
        self.monitor.went_offline.connect(lambda: self.log_event(tr("ev_offline"), "error"))

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(M, M, M, M)
        self._outer.setSpacing(0)
        self.titlebar = TitleBar(self)
        self._outer.addWidget(self.titlebar)
        self.stack = QStackedWidget()
        self._outer.addWidget(self.stack, 1)
        self.home = HomePage(self)
        self.fav = FavoritesPage(self)
        self.settings = SettingsPage(self)
        for p in (self.home, self.fav, self.settings):
            self.stack.addWidget(p)
        nav_wrap = QHBoxLayout()
        nav_wrap.setContentsMargins(14, 4, 14, 14)
        self.nav = NavBar()
        self.nav.currentChanged.connect(self._tab_changed)
        self.nav.setMaximumWidth(1240)
        nav_wrap.addStretch(1)
        nav_wrap.addWidget(self.nav, 100)
        nav_wrap.addStretch(1)
        self._outer.addLayout(nav_wrap)

        self.blur = BlurOverlay(self)
        self._blur_users = 0
        self.toast_w = Toast(self)
        self._grips = [EdgeGrip(e, self) for e in (
            Qt.LeftEdge, Qt.RightEdge, Qt.TopEdge, Qt.BottomEdge,
            Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge, Qt.RightEdge | Qt.BottomEdge)]

        self._setup_tray()
        skin.changed.connect(self._skin_changed)
        self.home.set_connection(reconcile_connection(db))
        self.log_event(tr("ev_started"))
        self.monitor.start()

    def _tab_changed(self, idx):
        self.stack.setCurrentIndex(idx)
        if idx == 2:
            self.settings.on_shown()

    def blur_on(self):
        """Blur the window behind a pop-up (reference-counted so nested pop-ups are fine)."""
        self._blur_users += 1
        if self._blur_users == 1:
            m = 0 if self.isMaximized() else M
            rect = self.rect().adjusted(m, m, -m, -m)
            self.blur.show_blur(rect, 0 if self.isMaximized() else 22)

    def blur_off(self):
        self._blur_users = max(0, self._blur_users - 1)
        if self._blur_users == 0:
            self.blur.hide_blur()

    # ------------------------------------------------------------------ API used by pages
    @property
    def tray_available(self):
        return self.tray is not None

    def toast(self, text, kind="info"):
        self.toast_w.show_message(text, kind)

    def log_event(self, text, kind="info"):
        self.events.appendleft((datetime.now().strftime("%H:%M:%S"), text, kind))

    def show_events(self):
        LogDialog(self, list(self.events)).exec()

    def data_changed(self):
        self.home.reload()
        self.fav.reload()

    def use_dns(self, dns_id):
        self.home.select_dns(dns_id)
        self.nav.set_current(0)
        self.stack.setCurrentIndex(0)
        self.toast(tr("msg_selected"), "ok")

    def relaunch_admin(self):
        if wd.relaunch_as_admin():
            self.quit_app()
            return True
        return False

    def toggle_max(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ------------------------------------------------------------------ tray
    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.app_icon, self)
        self.tray.setToolTip("Nexus DNS")
        self.tray_menu = QMenu()
        self.act_open = self.tray_menu.addAction("")
        self.tray_menu.addSeparator()
        self.act_exit = self.tray_menu.addAction("")
        self.act_open.triggered.connect(self.restore_from_tray)
        self.act_exit.triggered.connect(self.quit_app)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(lambda r: self.restore_from_tray() if r in (
            QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self._retranslate_tray()
        self.tray.show()

    def _retranslate_tray(self):
        if self.tray:
            self.act_open.setText(tr("tray_open"))
            self.act_exit.setText(tr("tray_exit"))

    def hide_to_tray(self):
        if not self.tray:
            self.toast(tr("msg_no_tray"), "warn")
            return
        self.hide()
        self.tray.showMessage("Nexus DNS", tr("tray_hidden"), QSystemTrayIcon.Information, 2500)

    def restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        if not self.really_quit and self.tray and self.db.get_bool("minimize_tray"):
            e.ignore()
            self.hide_to_tray()
            return
        e.ignore()
        self.quit_app()

    def quit_app(self):
        self.really_quit = True
        self.home.shutdown()
        self.settings.shutdown()
        self.monitor.shutdown()
        if self.tray:
            self.tray.hide()
        self.hide()
        QApplication.instance().quit()

    # ------------------------------------------------------------------ look
    def _skin_changed(self):
        self._retranslate_tray()
        self.update()

    def changeEvent(self, e):
        super().changeEvent(e)
        if not hasattr(self, "_grips"):
            return
        self._outer.setContentsMargins(*(0, 0, 0, 0) if self.isMaximized() else (M, M, M, M))
        for g in self._grips:
            g.setVisible(not self.isMaximized())
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w, h, c = self.width(), self.height(), 14
        g = self._grips
        g[0].setGeometry(0, c, M, h - 2 * c)
        g[1].setGeometry(w - M, c, M, h - 2 * c)
        g[2].setGeometry(c, 0, w - 2 * c, M)
        g[3].setGeometry(c, h - M, w - 2 * c, M)
        g[4].setGeometry(0, 0, c, c)
        g[5].setGeometry(w - c, 0, c, c)
        g[6].setGeometry(0, h - c, c, c)
        g[7].setGeometry(w - c, h - c, c, c)
        for x in g:
            x.raise_()
        if self._blur_users:
            m = 0 if self.isMaximized() else M
            self.blur.setGeometry(self.rect().adjusted(m, m, -m, -m))

    def _render_bg(self, dpr, maxed):
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        m = 0 if maxed else M
        r = QRectF(self.rect()).adjusted(m, m, -m, -m)
        radius = 0 if maxed else 22
        if not maxed:                                       # soft shadow
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 14))
            for i in range(6):
                p.drawRoundedRect(r.adjusted(-i, -i + 1, i, i + 1), radius + i, radius + i)
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(col("bg2")))
        g.setColorAt(0.5, QColor(col("bg")))
        g.setColorAt(1, QColor(col("bg")))
        p.fillPath(path, g)
        glow = QRadialGradient(r.center().x(), r.top() + 40, r.width() * 0.8)
        c = QColor(col("glow"))
        c.setAlpha(90 if skin.theme == "dark" else 120)
        glow.setColorAt(0, c)
        c.setAlpha(0)
        glow.setColorAt(1, c)
        p.setClipPath(path)
        p.fillRect(r, glow)
        p.setClipping(False)
        p.setPen(QColor(col("border")))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()
        return pm

    def paintEvent(self, e):
        dpr, maxed = self.devicePixelRatioF(), self.isMaximized()
        key = (self.width(), self.height(), maxed, skin.theme, dpr)
        if getattr(self, "_bg_key", None) != key:
            self._bg, self._bg_key = self._render_bg(dpr, maxed), key
        p = QPainter(self)
        p.drawPixmap(0, 0, self._bg)
