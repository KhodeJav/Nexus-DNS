"""Settings page."""
import os
import sys

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .. import __version__
from .. import windows_dns as wd
from .. import links
from ..paths import data_dir
from ..skin import col, skin, tr
from ..widgets import (centered, Card, ClickableCard, ElidedLabel, IconLabel, IconButton, IconChip, Segmented, Stepper, ToggleSwitch, hline, label)
from ..workers import AdapterThread


class SettingsPage(QScrollArea):
    def __init__(self, win):
        super().__init__()
        self.w, self.db = win, win.db
        self._adapter_thread = None
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        body = QWidget()
        outer = centered(body, 760)
        self.setWidget(outer)
        outer.setAutoFillBackground(False)
        body.setAutoFillBackground(False)
        root = QVBoxLayout(body)
        root.setContentsMargins(18, 4, 18, 14)
        root.setSpacing(14)
        self.title = label("", "h1")
        root.addWidget(self.title)

        # ---- appearance
        self.sec_appearance = label("", "accent")
        root.addWidget(self.sec_appearance)
        c = self._card()
        self.lbl_theme = label("", "title")
        self.seg_theme = Segmented([("dark", "dark", True), ("light", "light", True)])
        self.lbl_lang = label("", "title")
        self.seg_lang = Segmented([("fa", "فارسی", False), ("en", "English", False)])
        self._row(c, "moon", self.lbl_theme, self.seg_theme)
        c.layout().addWidget(hline())
        self._row(c, "globe", self.lbl_lang, self.seg_lang)
        root.addWidget(c)
        self.seg_theme.changed.connect(self._theme)
        self.seg_lang.changed.connect(self._lang)

        # ---- behavior
        self.sec_behavior = label("", "accent")
        root.addWidget(self.sec_behavior)
        c = self._card()
        self.lbl_tray = label("", "title")
        self.sub_tray = label("", "sub", wrap=True)
        self.sw_tray = ToggleSwitch()
        h = QHBoxLayout()
        h.setSpacing(12)
        h.addWidget(IconChip("tray", "accent2", 38, 19))
        v = QVBoxLayout()
        v.setSpacing(1)
        v.addWidget(self.lbl_tray)
        v.addWidget(self.sub_tray)
        h.addLayout(v, 1)
        h.addWidget(self.sw_tray)
        c.layout().addLayout(h)
        root.addWidget(c)
        self.sw_tray.toggled.connect(self._tray)

        # ---- benchmark
        self.sec_bench = label("", "accent")
        root.addWidget(self.sec_bench)
        c = self._card()
        self.lbl_count = label("", "title")
        self.step_count = Stepper(1, 100, 5)
        self.lbl_timeout = label("", "title")
        self.step_timeout = Stepper(200, 1000, 100)
        self._row(c, "activity", self.lbl_count, self.step_count)
        c.layout().addWidget(hline())
        self._row(c, "timer", self.lbl_timeout, self.step_timeout)
        self.bench_note = label("", "sub", wrap=True)
        c.layout().addWidget(self.bench_note)
        root.addWidget(c)
        self.step_count.valueChanged.connect(lambda v: self.db.set("test_count", v))
        self.step_timeout.valueChanged.connect(lambda v: self.db.set("timeout_ms", v))

        # ---- network
        self.sec_net = label("", "accent")
        root.addWidget(self.sec_net)
        c = self._card()
        self.lbl_adapter = label("", "title")
        self.val_adapter = ElidedLabel("", "sub")
        self.btn_detect = IconButton("refresh", "text", 18, "btn_detect", object_name="iconbox", pad=18)
        h = QHBoxLayout()
        h.setSpacing(12)
        h.addWidget(IconChip("wifi", "accent2", 38, 19))
        v = QVBoxLayout()
        v.setSpacing(1)
        v.addWidget(self.lbl_adapter)
        v.addWidget(self.val_adapter)
        h.addLayout(v, 1)
        h.addWidget(self.btn_detect)
        c.layout().addLayout(h)
        c.layout().addWidget(hline())
        self.lbl_admin = label("", "title")
        self.val_admin = label("", "title")
        self._row(c, "shield_check", self.lbl_admin, self.val_admin)
        root.addWidget(c)
        self.btn_detect.clicked.connect(self.detect_adapter)

        # ---- data
        self.sec_data = label("", "accent")
        root.addWidget(self.sec_data)
        c = self._card()
        self.btn_clear = QPushButton()
        self.btn_clear.setObjectName("secondary")
        self.btn_open = QPushButton()
        self.btn_open.setObjectName("secondary")
        for b in (self.btn_clear, self.btn_open):
            b.setCursor(Qt.PointingHandCursor)
            c.layout().addWidget(b)
        root.addWidget(c)
        self.btn_clear.clicked.connect(self._clear)
        self.btn_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))

        # ---- about the project
        self.sec_about = label("", "accent")
        root.addWidget(self.sec_about)
        c = self._card()
        self.about_desc = label("", "sub", wrap=True)
        self.about_desc.setStyleSheet("font-size: 9.5pt;")
        c.layout().addWidget(self.about_desc)
        c.layout().addWidget(hline())
        self.link_rows = []
        for icon_name, title_key, shown, url in (
                ("github", "about_github", links.GITHUB_URL.replace("https://", ""), links.GITHUB_URL),
                ("heart", "about_donate", links.DONATE_URL.replace("https://", ""), links.DONATE_URL),
                ("send", "about_telegram", links.TELEGRAM_ID, links.telegram_url(links.TELEGRAM_ID)),
                ("megaphone", "about_channel", links.CHANNEL_ID, links.telegram_url(links.CHANNEL_ID))):
            c.layout().addWidget(self._link_row(icon_name, title_key, shown, url))
        root.addWidget(c)
        self.about = label("", "sub", align=Qt.AlignCenter)
        root.addWidget(self.about)
        root.addStretch(1)

        self._load()
        skin.changed.connect(self.retranslate)
        self.retranslate()
        self._adapter_loaded = False

    # ------------------------------------------------------------------ helpers
    def _card(self):
        c = Card("card")
        v = QVBoxLayout(c)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(12)
        return c

    def _row(self, card, icon_name, lbl, control):
        h = QHBoxLayout()
        h.setSpacing(12)
        h.addWidget(IconChip(icon_name, "accent2", 38, 19))
        lbl.setWordWrap(True)
        h.addWidget(lbl, 1)
        h.addWidget(control)
        card.layout().addLayout(h)

    def _link_row(self, icon_name, title_key, shown, url):
        row = ClickableCard("card2")
        h = QHBoxLayout(row)
        h.setContentsMargins(12, 9, 12, 9)
        h.setSpacing(12)
        chip = IconChip(icon_name, "accent2", 38, 19)
        title = label("", "title")
        sub = ElidedLabel(shown, "sub")
        sub.setLayoutDirection(Qt.LeftToRight)
        sub.setAlignment(Qt.AlignLeading | Qt.AlignVCenter)
        v = QVBoxLayout()
        v.setSpacing(0)
        v.addWidget(title)
        v.addWidget(sub)
        self.chev_labels = getattr(self, "chev_labels", [])
        chev = IconLabel("chevron_left" if skin.rtl else "chevron_right", "sub", 18)
        self.chev_labels.append(chev)
        for w_ in (chip, title, sub, chev):
            w_.setAttribute(Qt.WA_TransparentForMouseEvents)
        h.addWidget(chip)
        h.addLayout(v, 1)
        h.addWidget(chev)
        row.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        self.link_rows.append((title, title_key))
        return row

    def _load(self):
        self.seg_theme.set_current(self.db.get("theme"))
        self.seg_lang.set_current(self.db.get("lang"))
        self.sw_tray.set_checked_silent(self.db.get_bool("minimize_tray"))
        self.step_count.set_value(self.db.get_int("test_count", 20))
        self.step_timeout.set_value(self.db.get_int("timeout_ms", 1000))

    def retranslate(self):
        self.title.setText(tr("set_title"))
        self.sec_appearance.setText(tr("sec_appearance"))
        self.lbl_theme.setText(tr("theme"))
        self.lbl_lang.setText(tr("language"))
        self.sec_behavior.setText(tr("sec_behavior"))
        self.lbl_tray.setText(tr("minimize_tray"))
        self.sub_tray.setText(tr("minimize_tray_sub"))
        self.sec_bench.setText(tr("sec_benchmark"))
        self.lbl_count.setText(tr("test_count"))
        self.lbl_timeout.setText(tr("timeout_ms"))
        self.bench_note.setText(tr("bench_note"))
        self.sec_net.setText(tr("sec_network"))
        self.lbl_adapter.setText(tr("active_adapter"))
        self.lbl_admin.setText(tr("admin_status"))
        admin = wd.is_admin()
        self.val_admin.setText(tr("yes") if admin else tr("no"))
        self.val_admin.setStyleSheet(f"color: {col('good' if admin else 'warn')}; font-weight: 700;")
        self.sec_data.setText(tr("sec_data"))
        self.btn_clear.setText(tr("clear_results"))
        self.btn_open.setText(tr("open_data"))
        self.sec_about.setText(tr("sec_about"))
        self.about_desc.setText(tr("about_desc"))
        for title, key in self.link_rows:
            title.setText(tr(key))
        for chev in self.chev_labels:
            chev.set_icon("chevron_left" if skin.rtl else "chevron_right")
        self.about.setText(f"Nexus DNS · {tr('version', v=__version__)}")
        if not self._adapter_thread:
            self.val_adapter.setText(getattr(self, "_adapter_text", tr("adapter_unknown")))

    # ------------------------------------------------------------------ handlers
    def _theme(self, key):
        self.db.set("theme", key)
        skin.apply(theme=key)

    def _lang(self, key):
        self.db.set("lang", key)
        skin.apply(lang=key)

    def _tray(self, on):
        self.db.set("minimize_tray", "1" if on else "0")
        if on and not self.w.tray_available:
            self.w.toast(tr("msg_no_tray"), "warn")

    def _clear(self):
        self.db.clear_results()
        self.w.data_changed()
        self.w.toast(tr("msg_results_cleared"), "ok")

    def on_shown(self):
        """PowerShell is only started when the user actually opens Settings (saves CPU/RAM at startup)."""
        if not self._adapter_loaded:
            self.detect_adapter()

    def detect_adapter(self):
        self._adapter_loaded = True
        if self._adapter_thread:
            return
        if not wd.supported():
            self._adapter_text = tr("err_not_windows")
            self.val_adapter.setText(self._adapter_text)
            return
        self.val_adapter.setText(tr("detecting"))
        t = AdapterThread(self)
        t.done.connect(self._adapter_done)
        t.finished.connect(t.deleteLater)
        self._adapter_thread = t
        t.start()

    def _adapter_done(self, ok, res):
        self._adapter_thread = None
        if ok:
            self._adapter_text = f"{res.name} — {res.description}"
        else:
            self._adapter_text = tr("err_" + res) if res in ("no_adapter", "not_windows") else tr("adapter_unknown")
        self.val_adapter.setText(self._adapter_text)

    def shutdown(self):
        if self._adapter_thread:
            self._adapter_thread.wait(3000)
