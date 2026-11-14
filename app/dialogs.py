"""Frameless, themed dialogs (add/edit DNS, group name, confirm, results, event log)."""
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget, QButtonGroup)
from PySide6.QtGui import QColor

from . import dns_bench as bench
from .skin import col, skin, tr
from .ui_helpers import big_value, fmt_ms, fmt_pct, rank_key, stat_text, status_text, value_grade
from .validators import clean_name, parse_ipv4
from .widgets import Avatar, Card, Combo, ElidedLabel, IconButton, hline, label, vline


class BaseDialog(QDialog):
    def __init__(self, parent, title_key=None, title_text=None, width=380):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._title_key = title_key
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        self.panel = QFrame()
        self.panel.setObjectName("dialogPanel")
        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.panel.setGraphicsEffect(shadow)
        outer.addWidget(self.panel)
        v = QVBoxLayout(self.panel)
        v.setContentsMargins(20, 14, 20, 20)
        v.setSpacing(14)
        head = QHBoxLayout()
        self.title = QLabel(title_text or (tr(title_key) if title_key else ""))
        self.title.setProperty("role", "title")
        head.addWidget(self.title, 1)
        self.close_btn = IconButton("x", "sub", 18, "tip_close")
        self.close_btn.clicked.connect(self.reject)
        head.addWidget(self.close_btn)
        v.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        v.addLayout(self.body)
        self.setMinimumWidth(width)
        self._drag = None

    def _host(self):
        p = self.parentWidget()
        while p is not None and not hasattr(p, "blur_on"):
            p = p.parentWidget()
        return p

    def showEvent(self, e):
        super().showEvent(e)
        host = self._host()
        if host and not getattr(self, "_blurred", False):
            self._blurred = True
            host.blur_on()
        par = self.parentWidget().window() if self.parentWidget() else None
        if par:
            c = par.frameGeometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)

    def done(self, result):
        host = self._host()
        if host and getattr(self, "_blurred", False):
            self._blurred = False
            host.blur_off()
        super().done(result)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < 64 and self.windowHandle():
            self.windowHandle().startSystemMove()
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and isinstance(self.focusWidget(), QPushButton):
            self.focusWidget().click()
            return
        super().keyPressEvent(e)


def _buttons(dlg, ok_text, ok_slot, ok_object="primary", cancel=True):
    row = QHBoxLayout()
    row.setSpacing(10)
    ok = QPushButton(ok_text)
    ok.setObjectName(ok_object)
    ok.setCursor(Qt.PointingHandCursor)
    ok.setStyleSheet("padding: 11px 18px; border-radius: 16px; font-size: 10.5pt;")
    ok.clicked.connect(ok_slot)
    row.addWidget(ok, 1)
    if cancel:
        c = QPushButton(tr("btn_cancel"))
        c.setObjectName("secondary")
        c.setCursor(Qt.PointingHandCursor)
        c.clicked.connect(dlg.reject)
        row.addWidget(c, 1)
    dlg.body.addLayout(row)
    return ok


def confirm(parent, text, ok_key="btn_yes", danger=False, title_key="confirm_title") -> bool:
    d = BaseDialog(parent, title_key, width=340)
    msg = label(text, wrap=True)
    d.body.addWidget(msg)
    _buttons(d, tr(ok_key), d.accept, "danger" if danger else "primary")
    return d.exec() == QDialog.Accepted


def inform(parent, text, title_key="err_title", ok_key="btn_ok"):
    d = BaseDialog(parent, title_key, width=340)
    d.body.addWidget(label(text, wrap=True))
    _buttons(d, tr(ok_key), d.accept, cancel=False)
    d.exec()


def _field(dlg, caption_key):
    dlg.body.addWidget(label(tr(caption_key), "sub"))
    e = QLineEdit()
    dlg.body.addWidget(e)
    return e


class GroupDialog(BaseDialog):
    def __init__(self, parent, title_key, name=""):
        super().__init__(parent, title_key, width=340)
        self.edit = _field(self, "f_group_name")
        self.edit.setText(name)
        self.edit.setMaxLength(40)
        self.error = label("", "sub")
        self.error.setStyleSheet(f"color: {col('bad')};")
        self.error.hide()
        self.body.addWidget(self.error)
        _buttons(self, tr("btn_save"), self._ok)
        self.result_name = None
        self.edit.setFocus()
        self.edit.returnPressed.connect(self._ok)

    def _ok(self):
        n = clean_name(self.edit.text())
        if not n:
            self.error.setText(tr("err_name"))
            self.error.show()
            return
        self.result_name = n
        self.accept()


class DnsDialog(BaseDialog):
    def __init__(self, parent, groups, dns=None, default_group=None):
        super().__init__(parent, "dlg_edit_dns" if dns else "dlg_add_dns", width=380)
        self.groups = groups
        self.name = _field(self, "f_name")
        self.name.setMaxLength(40)
        self.primary = _field(self, "f_primary")
        self.secondary = _field(self, "f_secondary")
        for e in (self.primary, self.secondary):
            e.setLayoutDirection(Qt.LeftToRight)
            e.setPlaceholderText("8.8.8.8")
            e.setMaxLength(15)
        self.body.addWidget(label(tr("f_group"), "sub"))
        self.group = Combo()
        for g in groups:
            self.group.addItem(g["name"], g["id"])
        self.body.addWidget(self.group)
        self.error = label("", "sub", wrap=True)
        self.error.setStyleSheet(f"color: {col('bad')};")
        self.error.hide()
        self.body.addWidget(self.error)
        _buttons(self, tr("btn_save"), self._ok)
        if dns:
            self.name.setText(dns["name"])
            self.primary.setText(dns["primary_ip"])
            self.secondary.setText(dns["secondary_ip"])
            self._select_group(dns["group_id"])
        elif default_group is not None:
            self._select_group(default_group)
        self.values = None
        self.name.setFocus()

    def _select_group(self, gid):
        i = self.group.findData(gid)
        if i >= 0:
            self.group.setCurrentIndex(i)

    def _fail(self, text):
        self.error.setText(text)
        self.error.show()

    def _ok(self):
        name = clean_name(self.name.text())
        if not name:
            return self._fail(tr("err_name"))
        p = parse_ipv4(self.primary.text())
        if not p:
            return self._fail(tr("err_ip", value=self.primary.text().strip() or "—"))
        s_raw = self.secondary.text().strip()
        s = ""
        if s_raw:
            s = parse_ipv4(s_raw)
            if not s:
                return self._fail(tr("err_ip", value=s_raw))
            if s == p:
                return self._fail(tr("err_same_ip"))
        gid = self.group.currentData()
        if gid is None:
            return self._fail(tr("err_need_group"))
        self.values = (name, p, s, gid)
        self.accept()


# ------------------------------------------------------------------------------ results
def _stats_row(res):
    stats = QHBoxLayout()
    for i, (key, text) in enumerate((("col_avg", stat_text(res, "avg")),
                                     ("col_jitter", stat_text(res, "jitter")),
                                     ("col_loss", fmt_pct(res.get("loss")) if res else "—"))):
        if i:
            stats.addWidget(vline())
        col_l = QVBoxLayout()
        col_l.setSpacing(1)
        col_l.addWidget(label(tr(key), "sub", align=Qt.AlignCenter))
        col_l.addWidget(label(text, "stat", align=Qt.AlignCenter))
        stats.addLayout(col_l, 1)
    return stats


def _value_box(res):
    """Big coloured last-ping value + status text, right/left aligned like the original card."""
    big = QVBoxLayout()
    big.setSpacing(0)
    g = value_grade(res)
    val = QLabel(big_value(res))
    val.setStyleSheet(f"font-size: 15pt; font-weight: 700; color: {col(g)};")
    val.setAlignment(Qt.AlignRight | Qt.AlignVCenter if not skin.rtl else Qt.AlignLeft | Qt.AlignVCenter)
    st = QLabel(status_text(res))
    st.setProperty("role", "sub")
    st.setAlignment(val.alignment())
    big.addWidget(val)
    big.addWidget(st)
    return big


class ResultRow(Card):
    selected = Signal(int)

    def __init__(self, dns, res, res2=None, parent=None):
        super().__init__("card2", parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(Avatar(dns["name"], 38, dns["primary_ip"]))
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(ElidedLabel(dns["name"], "title"))
        ip = QLabel(dns["primary_ip"])
        ip.setProperty("role", "sub")
        ip.setLayoutDirection(Qt.LeftToRight)
        ip.setAlignment(Qt.AlignLeading | Qt.AlignVCenter)
        names.addWidget(ip)
        top.addLayout(names, 1)
        top.addLayout(_value_box(res))
        v.addLayout(top)
        v.addWidget(hline())
        v.addLayout(_stats_row(res))
        if dns["secondary_ip"]:                       # same block again for the Secondary server
            v.addWidget(hline())
            head = QHBoxLayout()
            head.setSpacing(10)
            t = QVBoxLayout()
            t.setSpacing(0)
            t.addWidget(label(tr("secondary_dns"), "accent"))
            ip2 = QLabel(dns["secondary_ip"])
            ip2.setProperty("role", "sub")
            ip2.setLayoutDirection(Qt.LeftToRight)
            ip2.setAlignment(Qt.AlignLeading | Qt.AlignVCenter)
            t.addWidget(ip2)
            head.addLayout(t, 1)
            head.addLayout(_value_box(res2))
            v.addLayout(head)
            v.addWidget(hline())
            v.addLayout(_stats_row(res2))
        btn = QPushButton(tr("btn_select"))
        btn.setObjectName("primary")
        btn.setStyleSheet("padding: 11px 18px; border-radius: 16px; font-size: 10.5pt;")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: self.selected.emit(dns["id"]))
        v.addWidget(btn)


class ResultsDialog(BaseDialog):
    dns_selected = Signal(int)

    def __init__(self, parent, db, group_id):
        super().__init__(parent, "results_title", width=420)
        self.db, self.group_id, self.mode = db, group_id, "avg"
        self.setMinimumHeight(560)
        sort_row = QHBoxLayout()
        sort_row.setSpacing(6)
        sort_row.addWidget(label(tr("sort_by"), "sub"))
        self._group = QButtonGroup(self)
        for key, text in (("avg", "sort_avg"), ("jitter", "sort_jitter"), ("loss", "sort_loss"), ("last", "sort_last")):
            b = QPushButton(tr(text))
            b.setObjectName("chipbtn")
            b.setCheckable(True)
            b.setChecked(key == "avg")
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(32)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, k=key: self._set_mode(k))
            self._group.addButton(b)
            sort_row.addWidget(b, 1)
        self.body.addLayout(sort_row)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.viewport().setAutoFillBackground(False)
        self.holder = QWidget()
        self.holder.setAutoFillBackground(False)
        self.list_l = QVBoxLayout(self.holder)
        self.list_l.setContentsMargins(0, 0, 4, 0)
        self.list_l.setSpacing(10)
        self.scroll.setWidget(self.holder)
        self.holder.setAutoFillBackground(False)
        self.body.addWidget(self.scroll, 1)
        self._rebuild()

    def _set_mode(self, mode):
        self.mode = mode
        self._rebuild()

    def _rebuild(self):
        while self.list_l.count():
            it = self.list_l.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        items = self.db.list_dns(self.group_id)
        ids = [d["id"] for d in items]
        results = self.db.results_map(ids)
        results2 = self.db.results_map(ids, "secondary")
        if not results and not results2:
            self.list_l.addWidget(label(tr("results_empty"), "sub", wrap=True, align=Qt.AlignCenter))
            self.list_l.addStretch(1)
            return
        items.sort(key=lambda d: rank_key(results.get(d["id"]), results2.get(d["id"]), self.mode))
        for d in items:
            row = ResultRow(d, results.get(d["id"]), results2.get(d["id"]))
            row.selected.connect(self._pick)
            self.list_l.addWidget(row)
        self.list_l.addStretch(1)

    def _pick(self, dns_id):
        self.dns_selected.emit(dns_id)
        self.accept()


class LogDialog(BaseDialog):
    def __init__(self, parent, events):
        super().__init__(parent, "log_title", width=380)
        self.setMinimumHeight(420)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        holder = QWidget()
        holder.setAutoFillBackground(False)
        lay = QVBoxLayout(holder)
        lay.setSpacing(8)
        lay.setContentsMargins(0, 0, 4, 0)
        if not events:
            lay.addWidget(label(tr("log_empty"), "sub", align=Qt.AlignCenter))
        for stamp, text, kind in events:
            row = Card("card2")
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 9, 12, 9)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {col({'ok': 'good', 'error': 'bad', 'warn': 'warn'}.get(kind, 'accent2'))};")
            h.addWidget(dot)
            h.addWidget(label(text, wrap=True), 1)
            t = label(stamp, "sub")
            t.setLayoutDirection(Qt.LeftToRight)
            h.addWidget(t)
            lay.addWidget(row)
        lay.addStretch(1)
        scroll.setWidget(holder)
        holder.setAutoFillBackground(False)
        self.body.addWidget(scroll, 1)
