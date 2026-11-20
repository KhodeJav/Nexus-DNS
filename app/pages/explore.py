"""Explore page: public DNS servers from the Nexus-DNS GitHub list, one card each, tested with the app's own engine.

Data download / validation lives in app.explorer, the ping engine is dns_bench.run_benchmark (the same one the
Home page uses), run for several servers at once by workers.ParallelBenchmarkThread. This file only builds widgets and wires the two together.
"""
import time

from PySide6.QtCore import QLocale, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QProgressBar, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from .. import dns_bench as bench
from .. import explorer
from ..dialogs import DnsDialog, inform
from ..icons import icon
from ..paths import resource_path
from ..skin import col, skin, tr
from ..ui_helpers import fmt_ms, fmt_pct, no_reply
from ..widgets import (Card, Combo, ElidedLabel, FitLabel, IconButton, IconLabel, PingChart, centered, hline, label, vline)
from ..workers import ExplorerFetchThread, ParallelBenchmarkThread

REFETCH_AFTER = 120        # seconds: opening the page again within this time does not download again
TWO_COLUMNS_FROM = 700     # viewport width (px) from which the cards use two columns
DASH = "--"


_flag_cache = {}


def country_name(code):
    """English country name of an ISO 3166-1 alpha-2 code (from Qt's own tables); the code itself when unknown."""
    try:
        terr = QLocale.codeToTerritory(code)
        name = QLocale.territoryToString(terr) if terr != QLocale.AnyTerritory else ""
    except (AttributeError, TypeError):
        name = ""
    return name or code


def flag_pixmap(code, height, dpr):
    """Flag image of an ISO 3166-1 alpha-2 code (bundled PNGs, so it also works where Windows draws no emoji flags)."""
    code = (code or "").lower()
    key = (code, height, dpr)
    if key not in _flag_cache:
        pm = QPixmap(resource_path(f"assets/flags/{code}.png")) if code.isalpha() and len(code) == 2 else QPixmap()
        if not pm.isNull():
            pm = pm.scaledToHeight(int(height * dpr), Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
        _flag_cache[key] = pm
    return _flag_cache[key]


def _repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


class StatBox(Card):
    """One small rectangle: caption on top, value below."""

    def __init__(self, caption_key):
        super().__init__("card2")
        self._key = caption_key
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 7, 8, 7)
        v.setSpacing(0)
        self.caption = label("", "sub", align=Qt.AlignCenter)
        self.value = FitLabel(DASH, "stat", Qt.AlignCenter)
        v.addWidget(self.caption)
        v.addWidget(self.value)
        self.retranslate()

    def retranslate(self):
        self.caption.setText(tr(self._key))

    def set_value(self, text, color=None):
        self.value.setText(text)
        self.value.setStyleSheet(f"color: {color};" if color else "")


class ExploreCard(Card):
    """A single DNS server. State: none | testing | done | error (+ the last result it was given)."""

    save_requested = Signal(object)          # the ExplorerDns of this card

    def __init__(self, dns):
        super().__init__("card2")
        self.dns, self.state, self.res = dns, "none", None
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.name = ElidedLabel("", "title")
        self.globe = IconLabel("globe", "accent2", 18)          # marks a discovered DNS
        self.flag = label("", None, align=Qt.AlignCenter)
        self.flag.setStyleSheet("background: transparent;")
        top.addWidget(self.name)
        top.addWidget(self.globe)
        top.addStretch(1)
        top.addWidget(self.flag)
        v.addLayout(top)

        mid = QHBoxLayout()
        mid.setSpacing(8)
        info = QVBoxLayout()
        info.setSpacing(0)
        self.lbl_primary = label("", "accent")
        self.ip = label("", "value")
        self.ip.setLayoutDirection(Qt.LeftToRight)
        self.ip.setAlignment(Qt.AlignLeading | Qt.AlignVCenter)
        self.ip.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info.addWidget(self.lbl_primary)
        info.addWidget(self.ip)
        mid.addLayout(info, 1)
        # same design as the Test All / Refresh buttons: the app's primary button, small and pill-shaped
        self.btn_select = QPushButton()
        self.btn_select.setObjectName("primary")
        self.btn_select.setCursor(Qt.PointingHandCursor)
        self.btn_select.setIconSize(QSize(16, 16))
        self.btn_select.setStyleSheet("QPushButton { padding: 0px 16px; border-radius: 19px; font-size: 10.5pt; }")
        self.btn_select.setFixedHeight(38)
        self.btn_select.clicked.connect(lambda: self.save_requested.emit(self.dns))
        v.addLayout(mid)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.b_last, self.b_jit, self.b_loss = StatBox("ex_last"), StatBox("jitter"), StatBox("packet_loss")
        for b in (self.b_last, self.b_jit, self.b_loss):
            stats.addWidget(b, 1)
        v.addLayout(stats)
        v.addWidget(self.btn_select)                             # full card width, right under the stat boxes
        self.set_dns(dns)
        skin.changed.connect(self.retranslate)
        # while this server is being tested a soft band of light slides across the card
        self._sweep = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1500)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._on_sweep)

    def _on_sweep(self, v):
        self._sweep = float(v)
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.state != "testing":
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        clip = QPainterPath()
        clip.addRoundedRect(r, 16, 16)
        p.setClipPath(clip)
        band = r.width() * 0.55
        x = r.left() - band + (r.width() + band) * self._sweep
        g = QLinearGradient(x, 0, x + band, 0)
        c = QColor(col("accent2"))
        c.setAlpha(0)
        g.setColorAt(0, c)
        c.setAlpha(46)
        g.setColorAt(0.5, c)
        c.setAlpha(0)
        g.setColorAt(1, c)
        p.fillRect(r, g)

    # ---- data
    def set_dns(self, dns):
        self.dns = dns
        self.name.setText(dns.name)
        self.ip.setText(dns.primary_dns)
        pm = flag_pixmap(dns.country_code, 18, self.devicePixelRatioF())
        self.flag.setPixmap(pm)                                  # the flag of the record's country_code
        self.flag.setToolTip(dns.country_code or tr("ex_unknown_country"))
        self.flag.setVisible(not pm.isNull())
        self.retranslate()

    def retranslate(self):
        self.lbl_primary.setText(tr("primary_dns"))
        self.btn_select.setText(tr("ex_select"))
        self.btn_select.setIcon(icon("plus", "#ffffff", 16))
        for b in (self.b_last, self.b_jit, self.b_loss):
            b.retranslate()
        self._paint()

    def set_state(self, state, res=None):
        self.state = state
        if res is not None:
            self.res = res
        if state == "testing":
            if self._anim.state() != QVariantAnimation.Running:
                self._anim.start()
        elif self._anim.state() == QVariantAnimation.Running:
            self._anim.stop()
        self._paint()
        self.update()

    # ---- look
    def _paint(self):
        testing = self.state == "testing"
        on = "true" if testing else "false"
        if self.property("sel") != on:                          # same accent outline the app uses for "selected"
            self.setProperty("sel", on)
            _repolish(self)

        res = self.res
        last_col = None
        if self.state == "error":                                # internal failure: clearly not a plain timeout
            last, jit, loss = tr("ex_st_error"), DASH, DASH
            last_col = col("bad")
            if res and not no_reply(res):
                loss = fmt_pct(res.get("loss"))
        elif not res:                                            # never tested (an old result is kept while re-testing)
            last = jit = loss = DASH
        elif no_reply(res):                                      # no answer: the Last Ping box itself says so
            last = tr("st_unavailable") if res.get("status") == bench.UNAVAILABLE else tr("st_timeout")
            last_col = col("bad")
            jit, loss = DASH, fmt_pct(res.get("loss"))
        else:
            last, jit = fmt_ms(res.get("last")), fmt_ms(res.get("jitter"))
            loss = fmt_pct(res.get("loss"))
            last_col = PingChart._colour(res["last"]).name() if res.get("last") is not None else None
        self.b_last.set_value(last, last_col)
        self.b_jit.set_value(jit)
        self.b_loss.set_value(loss)


class ExplorePage(QScrollArea):
    def __init__(self, win):
        super().__init__()
        self.w, self.db = win, win.db
        self.servers, self.updated_at = [], ""
        self.cards = {}                    # record id -> ExploreCard
        self.results = {}                  # primary IP -> result dict (shared by every card with that IP)
        self.cache = self.db.get_json(explorer.CACHE_KEY)
        self._fetch, self._bench = None, None
        self._fetched_at = 0.0
        self._net_state = "idle"           # idle | loading | offline | network | invalid
        self._cols = 0
        self._stop_asked = False
        self._pending = set()              # IPs queued in the running test
        self._unit_ips = []

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        body = QWidget()
        outer = centered(body, 980)
        self.setWidget(outer)
        outer.setAutoFillBackground(False)
        body.setAutoFillBackground(False)
        root = QVBoxLayout(body)
        root.setContentsMargins(18, 4, 18, 14)
        root.setSpacing(14)

        # ---- header
        head = QHBoxLayout()
        head.setSpacing(8)
        tv = QVBoxLayout()
        tv.setSpacing(0)
        self.title = label("", "h1")
        self.sub = label("", "sub", wrap=True)
        tv.addWidget(self.title)
        tv.addWidget(self.sub)
        head.addLayout(tv, 1)
        root.addLayout(head)

        # Test All + Refresh: two small buttons of the same design (the app's primary button, just smaller)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        small = "QPushButton { padding: 0px 18px; border-radius: 21px; font-size: 10.5pt; }"
        self.btn_all = QPushButton()
        self.btn_all.setObjectName("primary")
        self.btn_all.setCursor(Qt.PointingHandCursor)
        self.btn_all.setIconSize(QSize(18, 18))
        self.btn_all.setStyleSheet(small)
        self.btn_all.setFixedHeight(42)
        self.btn_all.clicked.connect(self.test_all)
        self.btn_refresh = QPushButton()
        self.btn_refresh.setObjectName("primary")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setIconSize(QSize(18, 18))
        self.btn_refresh.setStyleSheet("QPushButton { padding: 0px; border-radius: 21px; }")
        self.btn_refresh.setFixedSize(42, 42)                    # same height as Test All, a perfect circle
        self.btn_refresh.clicked.connect(lambda: self.refresh(force=True))
        actions.addWidget(self.btn_all, 1)
        actions.addWidget(self.btn_refresh)
        actions.setAlignment(Qt.AlignVCenter)
        root.addLayout(actions)

        # sort by country: default = the list as it came; a country = only its servers, lowest ping first
        self.combo_country = Combo()
        self.combo_country.use_styled_popup()
        self.combo_country.setFixedHeight(42)
        self.combo_country.addItem("", "")
        self.combo_country.currentIndexChanged.connect(self._country_changed)
        root.addWidget(self.combo_country)

        self.info = label("", "sub", wrap=True)                  # count / updated / offline / loading
        root.addWidget(self.info)

        # ---- progress (only while testing)
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
        self.btn_stop.clicked.connect(self.stop_test)
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
        root.addWidget(self.prog)

        # ---- message card (error / empty) with a retry button
        self.msg = Card("card")
        mv = QVBoxLayout(self.msg)
        mv.setContentsMargins(16, 16, 16, 16)
        mv.setSpacing(10)
        self.msg_text = label("", "sub", wrap=True, align=Qt.AlignCenter)
        self.btn_retry = QPushButton()
        self.btn_retry.setObjectName("secondary")
        self.btn_retry.setCursor(Qt.PointingHandCursor)
        self.btn_retry.clicked.connect(lambda: self.refresh(force=True))
        mv.addWidget(self.msg_text)
        mv.addWidget(self.btn_retry, 0, Qt.AlignCenter)
        self.msg.hide()
        root.addWidget(self.msg)

        # ---- cards
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        root.addLayout(self.grid)
        root.addStretch(1)

        self._load_cache()
        skin.changed.connect(self.retranslate)
        self.retranslate()

    # ================================================================ texts
    def retranslate(self):
        self.title.setText(tr("ex_title"))
        self.sub.setText(tr("ex_sub"))
        self.btn_retry.setText(tr("ex_retry"))
        self.btn_stop.setText(tr("btn_stop") if not self._stop_asked else tr("testing_stopping"))
        self.btn_stop.setIcon(icon("stop", col("text"), 14))
        self.prog_title.setText(tr("ex_progress"))
        self.combo_country.setItemText(0, tr("ex_all_countries"))
        self._paint_button()
        self._paint_refresh()
        self._paint_info()
        self._paint_message()
        if self._bench is None:
            self.prog_counts.setText("")

    def _paint_button(self):
        busy = self._bench is not None
        self.btn_all.setText(tr("ex_testing") if busy else tr("ex_test_all"))
        self.btn_all.setIcon(icon("activity", "#ffffff" if not busy else col("off"), 18))
        self.btn_all.setEnabled(bool(self._available()) and not busy)

    def _paint_refresh(self):
        self.btn_refresh.setToolTip(tr("ex_refresh"))
        self.btn_refresh.setIcon(icon("refresh", "#ffffff" if self.btn_refresh.isEnabled() else col("off"), 18))

    def _paint_info(self):
        parts = []
        if self._net_state == "loading":
            parts.append(tr("ex_loading"))
        elif self.servers:
            parts.append(tr("ex_count", n=len(self._available())))
            if self._net_state in ("offline", "network", "invalid"):
                parts.append(tr("ex_offline"))
            elif self.updated_at:
                parts.append(tr("ex_updated", t=self.updated_at))
        self.info.setText("  ·  ".join(parts))
        self.info.setVisible(bool(parts))

    def _paint_message(self):
        """Shown only when there is nothing to list: still loading, failed with no cache, or an empty list."""
        if self.servers:
            self.msg.hide()
            return
        if self._net_state == "loading" or self._net_state == "idle":
            self.msg.hide()
            return
        if self._net_state == "invalid":
            text = tr("ex_err_invalid")
        elif self._net_state in ("network", "offline"):
            text = tr("ex_err_network")
        else:
            text = tr("ex_empty")
        self.msg_text.setText(text)
        self.msg.show()

    # ================================================================ data (download + cache)
    def _load_cache(self):
        got = explorer.servers_from_cache(self.cache)
        if got:
            self.updated_at, servers = got
            self._set_servers(servers)
            self._fetched_at = float(self.cache.get("fetched_at", 0) or 0)
        else:
            self.cache = None

    def on_shown(self):
        """Called each time the tab is opened: download once, then only when the list is a bit old."""
        self._refresh_available()                                    # Favorites may have changed meanwhile
        if self._fetch is None and time.time() - self._fetched_at > REFETCH_AFTER:
            self.refresh()

    def refresh(self, force=False):
        if self._fetch is not None:
            return
        if not force and time.time() - self._fetched_at <= REFETCH_AFTER:
            return
        self._net_state = "loading"
        self.btn_refresh.setEnabled(False)
        self._paint_refresh()
        self._paint_info()
        self._paint_message()
        t = ExplorerFetchThread(self.cache, self)
        t.done.connect(self._on_fetched)
        self._fetch = t
        t.start()

    def _on_fetched(self, ok, changed, payload):
        t, self._fetch = self._fetch, None
        if t:
            t.wait(1500)
            t.deleteLater()
        self.btn_refresh.setEnabled(True)
        self._paint_refresh()
        if ok:
            self._net_state = "idle"
            self._fetched_at = time.time()
            self.cache = payload
            self.db.set_json(explorer.CACHE_KEY, payload)
            got = explorer.servers_from_cache(payload)
            if got:
                self.updated_at, servers = got
                if changed or not self.servers:
                    self._set_servers(servers)
        else:
            # the last valid list (if any) stays on screen; nothing broken ever reaches the UI
            self._net_state = payload if payload in ("network", "invalid") else "network"
            if self.servers and self._net_state == "network":
                self._net_state = "offline"
        self._paint_info()
        self._paint_message()
        self._paint_button()

    # ================================================================ cards
    def _set_servers(self, servers):
        """Create / update / remove cards by record id (never by row number)."""
        self.servers = list(servers)
        ids = {s.id for s in servers}
        for rid in [r for r in self.cards if r not in ids]:
            card = self.cards.pop(rid)
            self.grid.removeWidget(card)
            card.deleteLater()
        for s in servers:
            card = self.cards.get(s.id)
            if card is None:
                card = self.cards[s.id] = ExploreCard(s)
                card.save_requested.connect(self.save_dns)
            elif card.dns != s:
                card.set_dns(s)
            res = self.results.get(s.primary_dns)
            if res is not None and card.state == "none":
                card.set_state("done", res)
        self._fill_countries()
        self._place(force=True)
        self._paint_button()
        self._paint_info()
        self._paint_message()

    # ---- servers already saved in a Favorites group are not offered again (no duplicates)
    def _available(self):
        saved = {r["primary_ip"] for r in self.db.list_dns()}          # every group, also the user's own
        return [s for s in self.servers if s.primary_dns not in saved]

    def _refresh_available(self):
        self._fill_countries()
        self._place(force=True)
        self._paint_button()
        self._paint_info()

    # ---- sort by country
    def _fill_countries(self):
        """List the countries that really occur in the downloaded list (nothing hard-coded)."""
        keep = self.combo_country.currentData() or ""
        codes = sorted({s.country_code for s in self._available() if s.country_code}, key=country_name)
        self.combo_country.blockSignals(True)
        while self.combo_country.count() > 1:
            self.combo_country.removeItem(1)
        for c in codes:
            self.combo_country.addItem(f"{country_name(c)}  ({c})", c)
        i = self.combo_country.findData(keep)
        self.combo_country.setCurrentIndex(max(0, i))
        self.combo_country.blockSignals(False)
        self.combo_country.setItemText(0, tr("ex_all_countries"))

    def _country_changed(self, _=None):
        self._place(force=True)
        self._paint_info()

    def _shown_servers(self):
        code = self.combo_country.currentData() or ""
        if not code:
            return self._available()                                     # default: exactly as downloaded
        def ping(s):                                                     # lowest Last Ping first; no answer / untested last
            res = self.results.get(s.primary_dns)
            if not res or no_reply(res) or res.get("last") is None:
                return (1, 0.0)
            return (0, float(res["last"]))
        return sorted((s for s in self._available() if s.country_code == code), key=ping)

    def _place(self, force=False):
        cols = 2 if self.viewport().width() >= TWO_COLUMNS_FROM else 1
        if cols == self._cols and not force:
            return
        self._cols = cols
        for card in self.cards.values():
            self.grid.removeWidget(card)
            card.hide()
        for c in range(2):
            self.grid.setColumnStretch(c, 1 if c < cols else 0)
        for i, s in enumerate(self._shown_servers()):
            card = self.cards[s.id]
            self.grid.addWidget(card, i // cols, i % cols)
            card.show()

    # ---- save a server into a Favorites group (the app's existing group system)
    def save_dns(self, dns):
        groups = self.db.list_groups()
        if not groups:
            inform(self.w, tr("err_need_group"))
            return
        dlg = DnsDialog(self.w, groups, prefill=dict(name=dns.name, primary=dns.primary_dns,
                                                      secondary=dns.secondary_dns))
        if dlg.exec() and dlg.values:
            self.db.add_dns(*dlg.values)
            self.w.data_changed()
            self._refresh_available()                                # the saved server leaves this list
            self.w.toast(tr("msg_saved"), "ok")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    # ================================================================ Ping All (Primary DNS only)
    @property
    def busy(self):
        return self._bench is not None

    def test_all(self):
        if self._bench is not None or not self._available():
            return
        home = getattr(self.w, "home", None)
        if home is not None and home.bench is not None:
            self.w.toast(tr("ex_busy"), "warn")
            return
        # one test per unique Primary IP; every card with that IP shows the same result
        by_ip = {}
        for s in self._available():
            by_ip.setdefault(s.primary_dns, []).append(s)
        self._unit_ips = list(by_ip)
        units = [(i, "primary", by_ip[ip][0].name, ip) for i, ip in enumerate(self._unit_ips)]
        self._pending = set(self._unit_ips)
        for s in self.servers:
            self.cards[s.id].set_state("none" if s.primary_dns not in self.results else "done")
        count = max(1, self.db.get_int("test_count", 20))
        timeout = self.db.get_int("timeout_ms", 1000)
        t = ParallelBenchmarkThread(units, count, timeout, parent=self)
        t.dns_started.connect(self._on_started)
        t.dns_done.connect(self._on_done)
        t.finished_all.connect(self._on_finished)
        self._bench, self._stop_asked = t, False
        self._done, self._total = 0, len(units)
        self.w.monitor.pause()
        self.prog_bar.setValue(0)
        self.prog_counts.setText(f"{0} / {self._total}")
        self.btn_stop.setEnabled(True)
        self.btn_stop.setText(tr("btn_stop"))
        self.prog.show()
        self._paint_button()
        t.start()

    def _cards_for(self, ip):
        return [self.cards[s.id] for s in self.servers if s.primary_dns == ip and s.id in self.cards]

    def _on_started(self, idx, total, dns_id, role, name, ip):
        for c in self._cards_for(ip):
            c.set_state("testing")                     # the previous result (if any) stays visible meanwhile
        # several servers are tested at once, so the title stays generic; each card shows its own activity

    def _on_done(self, dns_id, role, res):
        ip = self._unit_ips[dns_id] if 0 <= dns_id < len(self._unit_ips) else None
        if ip is None:
            return
        self.results[ip] = res
        self._pending.discard(ip)
        for c in self._cards_for(ip):
            c.set_state("done", res)
        self._done += 1
        self.prog_counts.setText(f"{self._done} / {self._total}")
        self.prog_bar.setValue(int(self._done * 100 / max(1, self._total)))

    def _on_finished(self, reason):
        t, self._bench = self._bench, None
        self.w.monitor.resume()
        if t:
            t.wait(1500)
            t.deleteLater()
        self.prog.hide()
        self.prog_title.setText(tr("ex_progress"))
        stopped = self._stop_asked
        self._stop_asked = False
        # whatever never finished goes back to its previous state (or ERROR if the test itself broke)
        internal = reason == "cancelled" and not stopped
        for ip in list(self._pending):
            for c in self._cards_for(ip):
                if internal:
                    c.set_state("error")
                else:
                    c.set_state("done" if ip in self.results else "none")
        self._pending.clear()
        self._paint_button()
        if self.combo_country.currentData():
            self._place(force=True)                                  # results changed: lowest ping first again
        if reason == "done":
            self.w.toast(tr("msg_test_done"), "ok")
        elif reason == "offline":
            self.w.toast(tr("msg_test_offline_mid") if self._done else tr("msg_offline_test"), "error")
        elif internal:
            self.w.toast(tr("ex_err_test"), "error")
        else:
            self.w.toast(tr("msg_test_cancelled"), "warn")

    def stop_test(self):
        if self._bench:
            self._stop_asked = True
            self._bench.requestInterruption()
            self.btn_stop.setEnabled(False)
            self.btn_stop.setText(tr("testing_stopping"))

    def shutdown(self):
        if self._bench:
            self._bench.requestInterruption()
            self._bench.wait(3000)
        if self._fetch:
            self._fetch.wait(3000)
