"""Forced-update window + the gate that decides when to show it. All logic lives in app.updater."""
from PySide6.QtCore import QEventLoop, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QProgressBar, QPushButton, QScrollArea, QWidget)

from . import __version__, update_config as cfg, updater
from .dialogs import BaseDialog
from .skin import col, tr
from .widgets import label
from .workers import UpdateCheckThread, UpdateDownloadThread


class UpdateDialog(BaseDialog):
    """Cannot be closed, skipped or dismissed: the only ways out are installing the update or quitting the app."""

    def __init__(self, parent, info, db):
        super().__init__(parent, "upd_title", width=400)
        self.info, self.db = info, db
        self.installing = False
        self.exit_requested = False
        self._thread = None
        self.close_btn.hide()
        self.body.addWidget(label(tr("upd_msg", new=info.get("latest", ""), cur=__version__), wrap=True))
        notes = (info.get("notes") or "").strip()
        if notes:
            box = QScrollArea()
            box.setWidgetResizable(True)
            box.setFrameShape(QScrollArea.NoFrame)
            box.setMaximumHeight(120)
            box.setStyleSheet("background: transparent;")
            inner = label(notes, "sub", wrap=True)
            inner.setAlignment(Qt.AlignTop | Qt.AlignLeading)
            box.setWidget(inner)
            self.body.addWidget(box)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.hide()
        self.status = label("", "sub", wrap=True)
        self.status.hide()
        self.body.addWidget(self.bar)
        self.body.addWidget(self.status)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn = QPushButton(tr("upd_btn"))
        self.btn.setObjectName("primary")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setStyleSheet("padding: 11px 18px; border-radius: 16px; font-size: 10.5pt;")
        self.btn.clicked.connect(self.start)
        self.btn_exit = QPushButton(tr("upd_exit"))
        self.btn_exit.setObjectName("secondary")
        self.btn_exit.setCursor(Qt.PointingHandCursor)
        self.btn_exit.clicked.connect(self._exit)
        row.addWidget(self.btn, 1)
        row.addWidget(self.btn_exit, 1)
        self.body.addLayout(row)

    # ---- not dismissable
    def reject(self):
        pass

    def closeEvent(self, e):
        e.ignore()

    def showEvent(self, e):
        super().showEvent(e)
        if self.parentWidget() is None:                          # start-up: no window behind us, centre on the screen
            c = QApplication.primaryScreen().availableGeometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)

    def _exit(self):
        self.exit_requested = True
        self.done(self.Rejected)

    def _show_status(self, text, bad=False):
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {col('bad')};" if bad else "")
        self.status.show()

    # ---- download + install
    def start(self):
        self.btn.setEnabled(False)
        self.btn_exit.setEnabled(False)
        self.bar.setValue(0)
        self.bar.show()
        self._show_status(tr("upd_downloading", p=0))
        t = UpdateDownloadThread(self.info.get("url", ""), self)
        t.progress.connect(self._progress)
        t.finished_ok.connect(self._downloaded)
        self._thread = t
        t.start()

    def _progress(self, got, total):
        if total > 0:
            p = int(got * 100 / total)
            self.bar.setValue(p)
            self._show_status(tr("upd_downloading", p=p))

    def _downloaded(self, ok, payload):
        if not ok:
            self._failed(tr("upd_nolink") if payload == "nolink" else tr("upd_err"))
            return
        self.bar.setValue(100)
        self._show_status(tr("upd_installing"))
        updater.clear_caches(self.db)                            # the new version starts without old cached data
        try:
            updater.launch_installer(payload)
        except updater.UpdateError:
            self._failed(tr("upd_err"))
            return
        self.installing = True
        self.done(self.Accepted)

    def _failed(self, text):
        self.bar.hide()
        self._show_status(text, bad=True)
        self.btn.setText(tr("upd_retry"))
        self.btn.setEnabled(True)
        self.btn_exit.setEnabled(True)


class UpdateGate(QObject):
    """Checks GitHub (start-up and then every few hours) and puts up the UpdateDialog when the version is too old."""
    settled = Signal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db, self.win = db, None
        self.must_quit = False
        self._thread = None
        self._open = False
        self._timer = QTimer(self)
        self._timer.setInterval(int(cfg.RECHECK_HOURS * 3600 * 1000))
        self._timer.timeout.connect(self.check)

    def start_timer(self):
        self._timer.start()

    def check(self):
        if not updater.configured() or self._thread is not None:
            self.settled.emit()
            return
        t = UpdateCheckThread(self)
        t.done.connect(self._result)
        self._thread = t
        t.start()

    def wait(self, ms=None):
        """Let start-up wait (briefly) for the first answer without freezing the event loop."""
        if self._thread is None:
            return
        loop = QEventLoop()
        self.settled.connect(loop.quit)
        QTimer.singleShot(ms or cfg.STARTUP_WAIT_MS, loop.quit)
        loop.exec()
        try:
            self.settled.disconnect(loop.quit)
        except (RuntimeError, TypeError):
            pass

    def _result(self, ok, payload):
        t, self._thread = self._thread, None
        if t:
            t.deleteLater()
        if ok:
            info = payload
            self.db.set_json(updater.CACHE_KEY, info)
        else:                                                    # offline / GitHub unreachable: trust what we last saw
            info = updater.load_cache(self.db)
        if info and updater.update_required(info):
            self._enforce(info)
        self.settled.emit()

    def _enforce(self, info):
        if self._open:
            return
        self._open = True
        dlg = UpdateDialog(self.win, info, self.db)
        dlg.exec()
        self._open = False
        if dlg.installing or dlg.exit_requested:
            self.must_quit = True
            QApplication.instance().quit()
