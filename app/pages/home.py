"""Home page: status, DNS selection, connect/disconnect, tests, live ping card."""
import time

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QBoxLayout, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
                               QScrollArea, QStackedLayout, QVBoxLayout, QWidget, QSizePolicy, QComboBox, QApplication)

from .. import dns_bench as bench
from .. import windows_dns as wd
from ..dialogs import ResultsDialog, confirm, inform
from ..icons import icon, pixmap
from ..paths import resource_path
from ..skin import col, skin, tr
from ..ui_helpers import big_value, fmt_ms, fmt_pct, no_reply, rank_key, stat_text, status_text, value_grade
from ..widgets import (Avatar, Card, ClickableCard, FitLabel, centered, Combo, ElidedLabel, IconButton, IconChip, IconLabel, PingChart,
                       hline, label, vline)
from ..workers import ApplyThread, BenchmarkThread

MAX_CONTENT_W = 1240      # full-screen content never gets wider than this
WIDE_MIN_W = 880          # from this width the home page switches to two columns
ERR_CODES = ("offline", "not_windows", "no_adapter", "verify_failed", "bad_servers", "flush_failed")


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


class ActionTile(QPushButton):
    def __init__(self, icon_name, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumHeight(78)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(10)
        self.chip = IconChip(icon_name, "accent2", 40, 20)
        self.chip.setAttribute(Qt.WA_TransparentForMouseEvents)
        v = QVBoxLayout()
        v.setSpacing(1)
        self.title = FitLabel("", "title")
        self.sub = label("", "sub", wrap=True)
        for w in (self.title, self.sub):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        v.addStretch(1)
        v.addWidget(self.title)
        v.addWidget(self.sub)
        v.addStretch(1)
        h.addWidget(self.chip)
        h.addLayout(v, 1)


class DnsPicker(ClickableCard):
    def __init__(self, parent=None):
        super().__init__("card2", parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(12)
        self.avatar = Avatar("?", 44)
        v = QVBoxLayout()
        v.setSpacing(0)
        self.name = ElidedLabel("", "title")
        self.ip = FitLabel("", "sub", Qt.AlignLeading | Qt.AlignVCenter)
        self.ip.setLayoutDirection(Qt.LeftToRight)
        v.addWidget(self.name)
        v.addWidget(self.ip)
        self.chev = IconLabel("chevron_down", "sub", 20)
        h.addWidget(self.avatar)
        h.addLayout(v, 1)
        h.addWidget(self.chev)
        for w in (self.avatar, self.name, self.ip, self.chev):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setMinimumHeight(66)

    def set_dns(self, d):
        if d:
            self.avatar.set_name(d["name"], d["primary_ip"])
            self.name.setText(d["name"])
            self.ip.setText(d["primary_ip"])
        else:
            self.avatar.set_name("?")
            self.name.setText(tr("no_dns"))
            self.ip.setText("")


class DnsPopup(QFrame):
    picked = Signal(int)

    def __init__(self, items, current_id, width, parent=None, host=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self._host, self._blurred = host, False
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoMouseReplay)      # the click that closes us must not reach the picker
        self.closed_at = 0.0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        panel = QFrame()
        panel.setObjectName("popup")
        outer.addWidget(panel)
        v = QVBoxLayout(panel)
        v.setContentsMargins(6, 6, 6, 6)
        self.list = QListWidget()
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        v.addWidget(self.list)
        for d in items:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, d["id"])
            it.setSizeHint(QSize(0, 56))
            self.list.addItem(it)
            row = QWidget()
            row.setAttribute(Qt.WA_TransparentForMouseEvents)
            h = QHBoxLayout(row)
            h.setContentsMargins(8, 4, 8, 4)
            h.setSpacing(10)
            h.addWidget(Avatar(d["name"], 36, d["primary_ip"]))
            t = QVBoxLayout()
            t.setSpacing(0)
            t.addWidget(ElidedLabel(d["name"], "title"))
            ip = QLabel(d["primary_ip"])
            ip.setProperty("role", "sub")
            ip.setLayoutDirection(Qt.LeftToRight)
            ip.setAlignment(Qt.AlignLeading | Qt.AlignVCenter)
            t.addWidget(ip)
            h.addLayout(t, 1)
            if d["is_pinned"]:
                h.addWidget(IconLabel("pin_fill", "accent2", 16))
            if d["is_favorite"]:
                h.addWidget(IconLabel("star_fill", "warn", 16))
            if d["id"] == current_id:
                h.addWidget(IconLabel("check", "good", 18))
            self.list.setItemWidget(it, row)
            if d["id"] == current_id:
                self.list.setCurrentItem(it)
        self.list.itemClicked.connect(self._clicked)
        rows = min(len(items), 5)
        self.setFixedSize(width, rows * 58 + 30)

    def showEvent(self, e):
        super().showEvent(e)
        if self._host and not self._blurred:
            self._blurred = True
            self._host.blur_on()

    def hideEvent(self, e):
        self.closed_at = time.monotonic()
        if self._host and self._blurred:
            self._blurred = False
            self._host.blur_off()
        super().hideEvent(e)

    def _clicked(self, it):
        self.picked.emit(it.data(Qt.UserRole))
        self.close()


class HomePage(QScrollArea):
    def __init__(self, win):
        super().__init__()
        self.w, self.db = win, win.db
        self.groups, self.dns_items = [], []
        self.sel_group = self.db.get_int("sel_group", -1)
        self.sel_dns = self.db.get_int("sel_dns", -1)
        self.conn = None
        self.bench = None
        self._applying = False
        self._apply_mode = ""
        self._mode = "single"
        self._live = []
        self._popup = None
        self.view_role = "primary"      # which server's numbers the ping card shows

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        body = QWidget()
        outer = centered(body, MAX_CONTENT_W)
        self.setWidget(outer)
        outer.setAutoFillBackground(False)
        body.setAutoFillBackground(False)
        root = QVBoxLayout(body)
        self.root = root
        root.setContentsMargins(18, 4, 18, 14)
        root.setSpacing(14)
        # two columns on wide/full-screen windows, one column on a narrow window (see _apply_layout)
        self.cols = QBoxLayout(QBoxLayout.TopToBottom)
        self.cols.setSpacing(14)
        self.col_a, self.col_b = QVBoxLayout(), QVBoxLayout()
        self.col_a.setSpacing(14)
        self.col_b.setSpacing(14)
        self.cols.addLayout(self.col_a, 1)
        self.cols.addLayout(self.col_b, 1)
        self._layout_key = None

        # ---- header
        head = QHBoxLayout()
        head.setSpacing(12)
        self.logo = QLabel()
        self.logo.setFixedSize(54, 54)
        pm = QPixmap(resource_path("assets/icon.png")).scaled(108, 108, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(2)
        self.logo.setPixmap(pm)
        tv = QVBoxLayout()
        tv.setSpacing(0)
        self.app_title = FitLabel("", "h1", Qt.AlignLeading | Qt.AlignVCenter)
        self.tagline = FitLabel("", "sub", Qt.AlignLeading | Qt.AlignVCenter)
        tv.addWidget(self.app_title)
        tv.addWidget(self.tagline)
        self.btn_flush = IconButton("broom", "text", 22, "tip_flush")
        self.btn_bell = IconButton("bell", "text", 22, "tip_events")
        self.btn_net = IconButton("wifi", "off", 24)          # green = online, red = offline
        self._net_msg = ("", "info")
        self.btn_flush.clicked.connect(self.on_flush)
        self.btn_bell.clicked.connect(win.show_events)
        self.btn_net.clicked.connect(self._net_clicked)
        head.addWidget(self.logo)
        head.addLayout(tv, 1)
        head.addWidget(self.btn_flush)
        head.addWidget(self.btn_bell)
        head.addWidget(self.btn_net)
        root.addLayout(head)
        root.addLayout(self.cols)

        # ---- selection card
        sel = Card("card")
        sv = QVBoxLayout(sel)
        sv.setContentsMargins(16, 16, 16, 16)
        sv.setSpacing(12)
        r1 = QHBoxLayout()
        r1.setSpacing(12)
        self.lbl_group = FitLabel("", "title")
        self.combo_group = Combo()
        self.combo_group.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_group.setMinimumContentsLength(10)
        self.combo_group.setMaximumWidth(170)
        self.combo_group.use_styled_popup()
        r1.addWidget(IconChip("layers"))
        r1.addWidget(self.lbl_group, 1)
        r1.addWidget(self.combo_group)
        sv.addLayout(r1)
        sv.addWidget(hline())
        r2 = QHBoxLayout()
        r2.setSpacing(12)
        self.lbl_dns = FitLabel("", "title")
        self.btn_star = IconButton("star", "sub", 22, "tip_fav")
        self.btn_pin = IconButton("pin", "sub", 22, "tip_pin")
        r2.addWidget(IconChip("server"))
        r2.addWidget(self.lbl_dns, 1)
        r2.addWidget(self.btn_star)
        r2.addWidget(self.btn_pin)
        sv.addLayout(r2)
        self.picker = DnsPicker()
        sv.addWidget(self.picker)
        boxes = QHBoxLayout()
        boxes.setSpacing(10)
        self.lbl_primary, self.val_primary = FitLabel("", "accent"), FitLabel("—", "value")
        self.lbl_secondary, self.val_secondary = FitLabel("", "accent"), FitLabel("—", "value")
        self.boxes = {}
        for role, lb, vl, name in (("primary", self.lbl_primary, self.val_primary, "server"),
                                   ("secondary", self.lbl_secondary, self.val_secondary, "server")):
            box = ClickableCard("card2")
            box.clicked.connect(lambda r=role: self._set_view_role(r))
            self.boxes[role] = box
            bh = QHBoxLayout(box)
            bh.setContentsMargins(12, 10, 12, 10)
            bh.setSpacing(10)
            vv = QVBoxLayout()
            vv.setSpacing(0)
            vl.setLayoutDirection(Qt.LeftToRight)
            vl.setAlignment(Qt.AlignLeading | Qt.AlignVCenter)
            vv.addWidget(lb)
            vv.addWidget(vl)
            bh.addWidget(IconChip(name, "accent2", 36, 18))
            bh.addLayout(vv, 1)
            boxes.addWidget(box, 1)
        sv.addLayout(boxes)
        self.btn_connect = QPushButton()
        self.btn_connect.setObjectName("primary")
        self.btn_connect.setCursor(Qt.PointingHandCursor)
        self.btn_connect.setMinimumHeight(56)
        self.btn_connect.setIconSize(QSize(24, 24))
        self.btn_connect.setFocusPolicy(Qt.NoFocus)
        sv.addWidget(self.btn_connect)
        self.conn_info = label("", "sub", wrap=True, align=Qt.AlignCenter)
        self.conn_info.hide()
        sv.addWidget(self.conn_info)
        self.col_a.addWidget(sel)
        self.col_a.addStretch(1)

        # ---- test tiles
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tile_group = ActionTile("users")
        self.tile_single = ActionTile("play")
        tiles.addWidget(self.tile_group, 1)
        tiles.addWidget(self.tile_single, 1)
        self.col_b.addLayout(tiles)

        # ---- test progress (only while testing)
        self.prog = Card("card")
        pv = QVBoxLayout(self.prog)
        pv.setContentsMargins(16, 14, 16, 14)
        pv.setSpacing(8)
        ph = QHBoxLayout()
        self.prog_title = ElidedLabel("", "title")
        self.btn_stop = QPushButton()
        self.btn_stop.setObjectName("secondary")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setIconSize(QSize(14, 14))
        self.btn_stop.setStyleSheet("padding: 7px 14px;")
        ph.addWidget(self.prog_title, 1)
        ph.addWidget(self.btn_stop)
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setTextVisible(False)
        self.prog_counts = label("", "sub")
        pv.addLayout(ph)
        pv.addWidget(self.prog_bar)
        pv.addWidget(self.prog_counts)
        self.prog.hide()
        self.col_b.addWidget(self.prog)

        # ---- ping card
        self.ping = ClickableCard("card")
        pc = QVBoxLayout(self.ping)
        pc.setContentsMargins(0, 0, 0, 12)
        pc.setSpacing(0)
        stack_host = QWidget()
        stack_host.setMinimumHeight(138)
        stack = QStackedLayout(stack_host)
        stack.setStackingMode(QStackedLayout.StackAll)
        self.chart = PingChart()
        self.chart.setAttribute(Qt.WA_TransparentForMouseEvents)
        overlay = QWidget()
        overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        ov = QVBoxLayout(overlay)
        ov.setContentsMargins(20, 16, 20, 6)
        ov.setSpacing(0)
        top = QHBoxLayout()
        self.dot = QLabel("●")
        self.lbl_last = label("", "sub")
        self.chev = IconLabel("chevron_left", "sub", 18)
        top.addWidget(self.dot)
        top.addWidget(self.lbl_last)
        top.addStretch(1)
        top.addWidget(self.chev)
        self.big = FitLabel("— ms", None, Qt.AlignLeading | Qt.AlignVCenter)
        self.big_sub = label("", "sub")
        ov.addLayout(top)
        ov.addWidget(self.big)
        ov.addWidget(self.big_sub)
        ov.addStretch(1)
        stack.addWidget(self.chart)
        stack.addWidget(overlay)
        overlay.raise_()
        pc.addWidget(stack_host)
        sep = hline()
        sep.setContentsMargins(16, 0, 16, 0)
        pc.addWidget(sep)
        stats = QHBoxLayout()
        stats.setContentsMargins(10, 10, 10, 0)
        self.stat_vals, self.stat_lbls = [], []
        for i, ic in enumerate(("timer", "activity", "pie")):
            if i:
                stats.addWidget(vline())
            col_l = QVBoxLayout()
            col_l.setSpacing(2)
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addStretch(1)
            row.addWidget(IconLabel(ic, "accent2", 18))
            lb = label("", "sub")
            row.addWidget(lb)
            row.addStretch(1)
            val = label("—", "stat", align=Qt.AlignCenter)
            col_l.addLayout(row)
            col_l.addWidget(val)
            stats.addLayout(col_l, 1)
            self.stat_lbls.append(lb)
            self.stat_vals.append(val)
        pc.addLayout(stats)
        self.col_b.addWidget(self.ping)

        # ---- quick connect (best result of the group) + centered description
        self.quick = Card("card2")
        qv = QVBoxLayout(self.quick)
        qv.setContentsMargins(14, 14, 14, 14)
        qv.setSpacing(10)
        self.btn_quick = QPushButton()
        self.btn_quick.setObjectName("secondary")
        self.btn_quick.setCursor(Qt.PointingHandCursor)
        self.btn_quick.setFocusPolicy(Qt.NoFocus)
        self.btn_quick.setMinimumHeight(46)
        self.btn_quick.setIconSize(QSize(20, 20))
        self.quick_desc = label("", "sub", wrap=True, align=Qt.AlignCenter)
        self.quick_desc.setStyleSheet("font-size: 9.5pt;")
        self.quick_desc.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)   # room for the 2nd line
        qv.addWidget(self.btn_quick)
        qv.addWidget(self.quick_desc)
        self.col_b.addWidget(self.quick)
        self.col_b.addStretch(1)
        root.addStretch(1)
        self._best_id = None

        # ---- wiring
        self.combo_group.currentIndexChanged.connect(self._group_changed)
        self.picker.clicked.connect(self._open_picker)
        self.btn_star.clicked.connect(self._toggle_fav)
        self.btn_pin.clicked.connect(self._toggle_pin)
        self.btn_connect.clicked.connect(self.on_connect)
        self.tile_group.clicked.connect(self.start_group_test)
        self.tile_single.clicked.connect(self.start_single_test)
        self.btn_stop.clicked.connect(self.stop_test)
        self.ping.clicked.connect(self.open_results)
        self.btn_quick.clicked.connect(self._quick_connect)
        win.monitor.checked.connect(self.refresh_status)
        skin.changed.connect(self.retranslate)
        self.btn_net.installEventFilter(self)          # tooltip text is built only when it is shown
        self.retranslate()
        self.reload()

    # ================================================================ texts / theme
    def retranslate(self):
        self.app_title.setText(tr("app_name"))
        self.tagline.setText(tr("tagline"))
        self.lbl_group.setText(tr("select_group"))
        self.lbl_dns.setText(tr("select_dns"))
        self.lbl_primary.setText(tr("primary_dns"))
        self.lbl_secondary.setText(tr("secondary_dns"))
        self.tile_group.title.setText(tr("test_group"))
        self.tile_group.sub.setText(tr("test_group_sub"))
        self.tile_single.title.setText(tr("test_single"))
        self.tile_single.sub.setText(tr("test_single_sub"))
        self.lbl_last.setText(tr("last_ping"))
        for lb, key in zip(self.stat_lbls, ("avg_ping", "jitter", "packet_loss")):
            lb.setText(tr(key))
        self.btn_stop.setText(tr("btn_stop") if not (self.bench and self.bench.isInterruptionRequested()) else tr("testing_stopping"))
        self.btn_stop.setIcon(icon("stop", col("text"), 14))
        self.btn_quick.setText(tr("quick_connect"))
        self.btn_quick.setIcon(icon("zap", col("accent2"), 20))
        self._apply_layout()
        self.chev.set_icon("chevron_left" if skin.rtl else "chevron_right")
        self._style_stars()
        self.refresh_status()
        self.refresh_connect_button()
        self._refresh_result_card()
        self._refresh_tip()

    def _style_stars(self):
        d = self.current_dns()
        fav = bool(d and d["is_favorite"])
        pin = bool(d and d["is_pinned"])
        self.btn_star.set_icon("star_fill" if fav else "star", "warn" if fav else "sub")
        self.btn_pin.set_icon("pin_fill" if pin else "pin", "accent2" if pin else "sub")
        self.btn_star.setEnabled(d is not None)
        self.btn_pin.setEnabled(d is not None)

    # ================================================================ internet status
    def refresh_status(self, *_):
        """The header Wi-Fi icon shows the connection: green = online, red = offline."""
        st = self.w.monitor.status
        if st is None:
            title, color, kind, icon_name = tr("status_checking"), "off", "info", "wifi"
        elif st.online and st.scope == "global":
            title, color, kind, icon_name = tr("status_online"), "good", "ok", "wifi"
        elif st.online:
            title, color, kind, icon_name = tr("status_domestic"), "warn", "warn", "wifi"
        else:
            title, color, kind, icon_name = tr("status_offline"), "bad", "error", "wifi_off"
        if getattr(self, "_net_icon", None) != (icon_name, color):
            self._net_icon = (icon_name, color)
            self.btn_net.set_icon(icon_name, color)
        self._net_msg = (title, kind)
        self.refresh_connect_button()

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "btn_net", None) and ev.type() == QEvent.ToolTip:
            tip = self._net_msg[0]
            if self.w.monitor.status is not None:
                age = int(time.time() - self.w.monitor.last_ts)
                when = tr("just_now") if age < 4 else tr("secs_ago", n=age) if age < 60 else tr("mins_ago", n=age // 60)
                tip += "\n" + tr("last_check", t=when)
            self.btn_net.setToolTip(tip)
        return super().eventFilter(obj, ev)

    def _net_clicked(self):
        """Tap the icon: re-check right now and say what the status is."""
        self.w.monitor.check_now()
        title, kind = self._net_msg
        self.w.toast(title, kind)

    # ================================================================ data
    def current_dns(self):
        for d in self.dns_items:
            if d["id"] == self.sel_dns:
                return d
        return None

    def reload(self):
        """(Re)read groups and DNS from the database, keeping the user's selection."""
        self._load_conn_name()
        self.groups = self.db.list_groups()
        ids = [g["id"] for g in self.groups]
        if self.sel_group not in ids:
            self.sel_group = ids[0] if ids else -1
        self.combo_group.blockSignals(True)
        self.combo_group.clear()
        for g in self.groups:
            self.combo_group.addItem(g["name"], g["id"])
        i = self.combo_group.findData(self.sel_group)
        if i >= 0:
            self.combo_group.setCurrentIndex(i)
        self.combo_group.blockSignals(False)
        self._load_dns()

    def _load_dns(self):
        self.dns_items = self.db.list_dns(self.sel_group) if self.sel_group != -1 else []
        ids = [d["id"] for d in self.dns_items]
        if self.sel_dns not in ids:
            self.sel_dns = ids[0] if ids else -1
        self.db.set("sel_group", self.sel_group)
        self.db.set("sel_dns", self.sel_dns)
        self._show_selection()

    def _show_selection(self):
        d = self.current_dns()
        self.picker.set_dns(d)
        self.val_primary.setText(d["primary_ip"] if d else "—")
        self.val_secondary.setText(d["secondary_ip"] if d and d["secondary_ip"] else "—")
        if not (d and d["secondary_ip"]):
            self.view_role = "primary"
        self._style_boxes()
        self._style_stars()
        self._refresh_result_card()
        self._refresh_tip()
        self.refresh_connect_button()

    def select_dns(self, dns_id):
        d = self.db.get_dns(dns_id)
        if not d:
            return
        self.sel_group, self.sel_dns = d["group_id"], d["id"]
        self.reload()

    def _group_changed(self, _idx):
        gid = self.combo_group.currentData()
        if gid is None:
            return
        self.sel_group = gid
        self.sel_dns = -1
        self._load_dns()

    def _open_picker(self):
        # a click on the picker while the list is open only closes it (never closes-then-reopens)
        if self._popup is not None and time.monotonic() - self._popup.closed_at < 0.35:
            return
        if not self.dns_items:
            self.w.toast(tr("msg_empty_group"), "warn")
            return
        self._popup = DnsPopup(self.dns_items, self.sel_dns, self.picker.width(), self, host=self.w)
        self._popup.picked.connect(self._picked)
        pos = self.picker.mapToGlobal(QPoint(0, self.picker.height() + 2))
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if pos.y() + self._popup.height() > screen.availableGeometry().bottom():
            pos = self.picker.mapToGlobal(QPoint(0, -self._popup.height() - 2))
        self._popup.move(pos)
        self._popup.show()

    def _picked(self, dns_id):
        self.sel_dns = dns_id
        self.db.set("sel_dns", dns_id)
        self._show_selection()

    def _toggle_fav(self):
        d = self.current_dns()
        if d:
            self.db.set_favorite(d["id"], not d["is_favorite"])
            self.w.data_changed()

    def _toggle_pin(self):
        d = self.current_dns()
        if d:
            self.db.set_pinned(d["id"], not d["is_pinned"])
            self.w.data_changed()

    # ================================================================ ping card
    def _style_boxes(self):
        """Only the secondary box is marked, when its numbers are the ones on show."""
        for role, box in self.boxes.items():
            on = "true" if (role == "secondary" and self.view_role == "secondary") else "false"
            if box.property("sel") != on:
                box.setProperty("sel", on)
                repolish(box)

    def _set_view_role(self, role):
        d = self.current_dns()
        if role == "secondary" and not (d and d["secondary_ip"]):
            return
        self.view_role = role
        self._style_boxes()
        self._refresh_result_card()

    def _refresh_result_card(self):
        if self.bench and self.bench.isRunning():
            return
        d = self.current_dns()
        self._render_result(self.db.get_result(d["id"], self.view_role) if d else None)

    def _render_result(self, res):
        g = value_grade(res)
        self.big.setText(big_value(res))
        shown = col(g)
        if res and not no_reply(res) and res.get("last") is not None:
            shown = self._ping_colour(res["last"])           # colour follows the shown ping, same as during the test
        self.big.setStyleSheet(f"font-size: 30pt; font-weight: 800; color: {shown};")
        self.dot.setStyleSheet(f"color: {shown}; font-size: 10pt;")
        parts = []
        if self.view_role == "secondary":
            parts.append(tr("secondary_dns"))
        if res and res.get("status") != bench.OK:
            parts.append(status_text(res))
        elif not res:
            parts.append(tr("not_tested"))
        self.big_sub.setText("  ·  ".join(parts))
        vals = [stat_text(res, "avg"), stat_text(res, "jitter"),
                fmt_pct(res.get("loss")) if res else "—"]
        for lab, v in zip(self.stat_vals, vals):
            lab.setText(v)
        self.chart.set_values(res.get("samples") if res else [], {"good": "good", "warn": "warn", "bad": "bad"}.get(g, "accent"))

    def _refresh_tip(self):
        ids = [d["id"] for d in self.dns_items]
        results, results2 = self.db.results_map(ids), self.db.results_map(ids, "secondary")
        best = None
        for d in self.dns_items:
            r = results.get(d["id"])
            if r and r["status"] == bench.OK and r["avg"] is not None:
                key = rank_key(r, results2.get(d["id"]), "avg")
                if best is None or key < best[2]:
                    best = (d, r["avg"], key)
        if best:
            self._best_id = best[0]["id"]
            # \u202a..\u202c keeps "159 ms" in this order inside a Persian sentence
            self.quick_desc.setText(tr("quick_desc", name=best[0]["name"], ms="\u202a" + fmt_ms(best[1]) + "\u202c"))
            QTimer.singleShot(0, self._fit_wrapped)
            self.btn_quick.setEnabled(True)
        else:
            self._best_id = None
            self.quick_desc.setText(tr("tip_default"))
            self.btn_quick.setEnabled(False)
            QTimer.singleShot(0, self._fit_wrapped)

    def _quick_connect(self):
        """Select the group's best DNS and connect to it right away."""
        if self._applying or self._best_id is None:
            return
        if self._best_id != self.sel_dns:
            self._picked(self._best_id)
        if self._is_current_connected():
            self.w.toast(tr("msg_already_connected"), "ok")
            return
        self.on_connect()

    # ================================================================ responsive layout
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_layout()
        QTimer.singleShot(0, self._fit_wrapped)

    def _fit_wrapped(self):
        """Multi-line labels inside a scroll area: reserve the height their wrapped text really needs."""
        for lab in (self.quick_desc, self.conn_info):
            if lab.width() > 20:
                h = lab.heightForWidth(lab.width())
                if h > 0 and lab.minimumHeight() != h:
                    lab.setMinimumHeight(h)

    def _apply_layout(self):
        """Full-screen: selection on one side, tests/ping/quick-connect on the other, so nothing needs scrolling.
        Same widgets and design - only their arrangement changes."""
        wide = self.viewport().width() >= WIDE_MIN_W
        key = (wide, skin.rtl)
        if key == self._layout_key:
            return
        self._layout_key = key
        if wide:      # physical order: selection card on the left in both languages
            self.cols.setDirection(QBoxLayout.RightToLeft if skin.rtl else QBoxLayout.LeftToRight)
            self.root.setContentsMargins(28, 6, 28, 18)
        else:
            self.cols.setDirection(QBoxLayout.TopToBottom)
            self.root.setContentsMargins(18, 4, 18, 14)

    def open_results(self):
        if self.sel_group == -1:
            return
        dlg = ResultsDialog(self.w, self.db, self.sel_group)
        dlg.dns_selected.connect(self._result_chosen)
        dlg.exec()

    def _result_chosen(self, dns_id):
        self.select_dns(dns_id)
        self.w.toast(tr("msg_selected"), "ok")

    # ================================================================ connect / disconnect
    def set_connection(self, backup):
        self.conn = backup
        self._load_conn_name()
        self.refresh_connect_button()

    def _load_conn_name(self):
        d = self.db.get_dns(self.conn.get("dns_id")) if self.conn else None
        self._conn_name = d["name"] if d else "DNS"

    def _is_current_connected(self):
        return bool(self.conn) and self.conn.get("dns_id") == self.sel_dns

    def refresh_connect_button(self):
        b = self.btn_connect
        online = bool(self.w.monitor.online)
        if self._applying:
            text, name, ic, enabled = (tr("btn_connecting") if self._apply_mode == "connect" else tr("btn_disconnecting")), "primary", "zap", False
        elif self._is_current_connected():
            text, name, ic, enabled = tr("btn_disconnect"), "danger", "power", True
        else:
            text, name, ic, enabled = tr("btn_connect"), "primary", "zap", online and self.current_dns() is not None
        if b.objectName() != name:
            b.setObjectName(name)
            repolish(b)
        b.setText(text.replace("&", "&&"))      # a single & would be eaten as a keyboard mnemonic
        b.setEnabled(enabled)
        b.setIcon(icon(ic, "#ffffff" if enabled else col("off"), 24))
        if self.conn:
            self.conn_info.setText("●  " + tr("connected_to", name=self._conn_name))
            self.conn_info.setStyleSheet(f"color: {col('good')}; font-weight: 600;")
            self.conn_info.show()
        else:
            self.conn_info.hide()

    def on_connect(self):
        if self._applying:
            return
        if self._is_current_connected():
            return self._start_apply("disconnect", None)
        d = self.current_dns()
        if not d:
            self.w.toast(tr("msg_pick_dns"), "warn")
            return
        if not self.w.monitor.online:
            self.w.toast(tr("msg_offline_connect"), "error")
            return
        if not wd.supported():
            inform(self.w, tr("err_not_windows"))
            return
        if not self._ensure_admin():
            return
        self._start_apply("connect", d)

    def _ensure_admin(self):
        if wd.is_admin():
            return True
        if confirm(self.w, tr("admin_text"), "admin_yes", title_key="admin_title"):
            if not self.w.relaunch_admin():
                self.w.toast(tr("admin_cancelled"), "error")
        return False

    def on_flush(self):
        """Clear the DNS cache and turn the app's DNS off (previous Windows DNS restored)."""
        if self._applying:
            return
        if not wd.supported():
            inform(self.w, tr("err_not_windows"))
            return
        if not self._ensure_admin():
            return
        self._start_apply("flush", None)

    def _start_apply(self, mode, dns):
        self._applying, self._apply_mode = True, mode
        self.refresh_connect_button()
        t = ApplyThread(self.db, mode, dns, self)
        t.done.connect(self._apply_done)
        t.finished.connect(t.deleteLater)
        self._apply_thread = t
        t.start()

    def _apply_done(self, ok, msg, info):
        self._applying = False
        if ok and self._apply_mode == "flush":
            if info and info.get("restored") is not None:
                self.set_connection(None)
                self.w.toast(tr("msg_flushed_off"), "ok")
            else:
                self.set_connection(self.db.get_json("dns_backup"))
                self.w.toast(tr("msg_flushed"), "ok")
            self.w.log_event(tr("ev_flushed"), "ok")
            return
        if ok:
            if self._apply_mode == "connect":
                self.set_connection(info)
                self.w.toast(tr("msg_connected", adapter=info["name"]), "ok")
                d = self.db.get_dns(info["dns_id"])
                self.w.log_event(tr("ev_connected", name=d["name"] if d else "?", ip=info["applied"][0]), "ok")
            else:
                self.set_connection(None)
                gone = bool(info and info.get("gone"))
                self.w.toast(tr("msg_adapter_gone") if gone else tr("msg_disconnected"), "ok")
                self.w.log_event(tr("ev_disconnected"), "ok")
            return
        self.set_connection(self.db.get_json("dns_backup"))
        if msg == "offline":
            self.w.toast(tr("msg_offline_connect"), "error")
            self.w.log_event(tr("msg_offline_connect"), "error")
            return
        if msg in ERR_CODES:
            text = tr("err_" + msg)
        else:
            text = tr("err_generic", err=msg.replace("unexpected:", ""))
        self.w.log_event(text, "error")
        inform(self.w, text)

    # ================================================================ tests
    def start_single_test(self):
        d = self.current_dns()
        if not d:
            self.w.toast(tr("msg_pick_dns"), "warn")
            return
        self._start_bench([d], "single")

    def start_group_test(self):
        if not self.dns_items:
            self.w.toast(tr("msg_empty_group"), "warn")
            return
        self._start_bench(list(self.dns_items), "group")

    def _start_bench(self, items, mode):
        if self.bench is not None:
            return
        self._mode = mode
        self._count = max(1, self.db.get_int("test_count", 20))
        timeout = self.db.get_int("timeout_ms", 1000)
        self._live = []
        units = []
        for d in items:
            units.append((d["id"], "primary", d["name"], d["primary_ip"]))
            if d["secondary_ip"]:
                units.append((d["id"], "secondary", d["name"], d["secondary_ip"]))
        self._dns_count = len(items)
        t = BenchmarkThread(units, self._count, timeout, self)
        t.dns_started.connect(self._on_started)
        t.sample.connect(self._on_sample)
        t.dns_done.connect(self._on_done)
        t.finished_all.connect(self._on_finished)
        self.bench = t
        self.w.monitor.pause()
        self._idx, self._total = 0, len(units)
        self.tile_group.setEnabled(False)
        self.tile_single.setEnabled(False)
        self.prog_bar.setValue(0)
        self.prog_title.setText(tr("testing_name", name=items[0]["name"]))
        self.prog_counts.setText(tr("progress_counts", done=0, total=len(units), left=len(units)))
        self.btn_stop.setEnabled(True)
        self.btn_stop.setText(tr("btn_stop"))
        self.prog.show()
        self._show_waiting()
        t.start()

    @staticmethod
    def _ping_colour(ms):
        """ONE colour rule for the number, the dot and the chart: it follows the ping itself (same scale as the chart)."""
        return PingChart._colour(ms).name()

    def _show_waiting(self):
        """Nothing measured yet: dots everywhere, never a number left over from an earlier test."""
        dots = "\u2022 \u2022 \u2022"
        self.big.setText(dots)
        self.big.setStyleSheet(f"font-size: 30pt; font-weight: 800; color: {col('accent2')};")
        self.big_sub.setText("")
        for lab in self.stat_vals:
            lab.setText(dots)
        self.chart.set_values([], "accent")

    def _on_started(self, idx, total, dns_id, role, name, ip):
        self._idx, self._total = idx, total
        self._live = []
        shown = name if role == "primary" else f"{name} · {tr('secondary_dns')}"
        self.prog_title.setText(tr("testing_name", name=shown))
        self._show_waiting()
        self.big_sub.setText(shown)            # the card follows the server being tested right now
        self.prog_counts.setText(tr("progress_counts", done=idx, total=total, left=total - idx))
        self.prog_bar.setValue(int(idx * 100 / total))

    def _on_sample(self, dns_id, seq, ms):
        self._live.append(None if ms < 0 else ms)
        frac = (self._idx + min(seq / self._count, 1.0)) / self._total
        self.prog_bar.setValue(int(frac * 100))
        if self._mode == "single":
            self.prog_counts.setText(tr("progress_single", seq=seq, count=self._count))
        self.chart.set_values(self._live, "accent")          # live chart: single AND group tests
        ok = [v for v in self._live if v is not None]
        answered = self._live[-1] is not None                # the newest request got an answer
        dots = "\u2022 \u2022 \u2022"
        if not answered:                                     # the newest request expired: TIMEOUT in red
            self.big.setText(tr("st_timeout"))
            self.big.setStyleSheet(f"font-size: 30pt; font-weight: 800; color: {col('bad')};")
            self.dot.setStyleSheet(f"color: {col('bad')}; font-size: 10pt;")
            texts = [tr("st_timeout")] * 2
        elif len(self._live) < 3:                            # a lone first answer proves nothing (dead servers can answer once): keep dots
            self.big.setText(dots)
            self.big.setStyleSheet(f"font-size: 30pt; font-weight: 800; color: {col('accent2')};")
            texts = [dots] * 2
        else:
            self.big.setText(fmt_ms(ok[-1]))
            self.big.setStyleSheet(f"font-size: 30pt; font-weight: 800; color: {self._ping_colour(ok[-1])};")
            self.dot.setStyleSheet(f"color: {self._ping_colour(ok[-1])}; font-size: 10pt;")
            st = bench.compute_stats(self._live)
            texts = [fmt_ms(st["avg"]), fmt_ms(st["jitter"])]
        self.stat_vals[0].setText(texts[0])
        self.stat_vals[1].setText(texts[1])
        self.stat_vals[2].setText(fmt_pct(bench.compute_stats(self._live)["loss"]) if len(self._live) >= 2 or not answered else dots)

    def _on_done(self, dns_id, role, res):
        self.db.save_result(dns_id, res, role)
        self.stat_vals[2].setText(fmt_pct(res.get("loss")))   # final Packet Loss of this server (same number as the saved result)
        self._idx += 1
        self.prog_counts.setText(tr("progress_counts", done=self._idx, total=self._total, left=self._total - self._idx))
        self.prog_bar.setValue(int(self._idx * 100 / self._total))
        self._refresh_tip()

    def _on_finished(self, reason):
        t, self.bench = self.bench, None
        self.w.monitor.resume()
        if t:
            t.wait(1500)
            t.deleteLater()
        self.prog.hide()
        self.tile_group.setEnabled(True)
        self.tile_single.setEnabled(True)
        mode = self._mode
        self._mode = "single"
        self._refresh_result_card()
        self._refresh_tip()
        if reason == "done":
            if mode == "group":
                self.w.log_event(tr("ev_test_done", n=self._dns_count), "ok")
                self.w.toast(tr("msg_test_done"), "ok")
                self.open_results()
            else:
                d = self.current_dns()
                res = self.db.get_result(d["id"]) if d else None
                if res and res["status"] in (bench.TIMEOUT, bench.UNAVAILABLE):
                    self.w.toast(tr("msg_test_failed_single"), "warn")
                else:
                    self.w.toast(tr("msg_test_done"), "ok")
        elif reason == "offline":
            self.w.toast(tr("msg_test_offline_mid") if self._idx else tr("msg_offline_test"), "error")
            self.w.log_event(tr("ev_test_offline"), "error")
        else:
            self.w.toast(tr("msg_test_cancelled"), "warn")
            self.w.log_event(tr("ev_test_cancelled"), "warn")

    def stop_test(self):
        if self.bench:
            self.bench.requestInterruption()
            self.btn_stop.setEnabled(False)
            self.btn_stop.setText(tr("testing_stopping"))

    def shutdown(self):
        if self.bench:
            self.bench.requestInterruption()
            self.bench.wait(3000)
