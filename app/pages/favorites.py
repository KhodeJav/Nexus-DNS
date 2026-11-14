"""Favorites page: manage DNS servers and groups."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..dialogs import DnsDialog, GroupDialog, confirm, inform
from ..skin import col, skin, tr
from ..widgets import (centered, Avatar, Card, ElidedLabel, IconButton, IconChip, Segmented, hline, label)


class DnsRow(Card):
    def __init__(self, page, d, show_group=False):
        super().__init__("card2")
        self.page, self.d = page, d
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 9, 8, 9)
        h.setSpacing(10)
        h.addWidget(Avatar(d["name"], 38, d["primary_ip"]))
        v = QVBoxLayout()
        v.setSpacing(0)
        v.addWidget(ElidedLabel(d["name"], "title"))
        ips = d["primary_ip"] + (f"  ·  {d['secondary_ip']}" if d["secondary_ip"] else "")
        sub = ElidedLabel(ips, "sub")
        sub.setLayoutDirection(Qt.LeftToRight)
        sub.setAlignment(Qt.AlignLeading | Qt.AlignVCenter)
        v.addWidget(sub)
        if show_group:
            v.addWidget(ElidedLabel(d["group_name"], "sub"))
        h.addLayout(v, 1)
        fav, pin = bool(d["is_favorite"]), bool(d["is_pinned"])
        star = IconButton("star_fill" if fav else "star", "warn" if fav else "sub", 20, "tip_fav", pad=12)
        pinb = IconButton("pin_fill" if pin else "pin", "accent2" if pin else "sub", 20, "tip_pin", pad=12)
        more = IconButton("more", "sub", 20, "tip_more", pad=12)
        star.clicked.connect(lambda: page.toggle_fav(d))
        pinb.clicked.connect(lambda: page.toggle_pin(d))
        more.clicked.connect(lambda: page.row_menu(d, more))
        for b in (star, pinb, more):
            h.addWidget(b)


class FavoritesPage(QScrollArea):
    def __init__(self, win):
        super().__init__()
        self.w, self.db = win, win.db
        self.mode = "groups"
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

        head = QHBoxLayout()
        head.setSpacing(8)
        tv = QVBoxLayout()
        tv.setSpacing(0)
        self.title = label("", "h1")
        self.sub = label("", "sub")
        tv.addWidget(self.title)
        tv.addWidget(self.sub)
        self.btn_group = IconButton("folder_plus", "text", 21, "add_group", object_name="iconbox", pad=20)
        self.btn_add = IconButton("plus", "text", 21, "add_dns", object_name="iconbox", pad=20)
        self.btn_group.clicked.connect(self.add_group)
        self.btn_add.clicked.connect(self.add_dns)
        head.addLayout(tv, 1)
        head.addWidget(self.btn_group)
        head.addWidget(self.btn_add)
        root.addLayout(head)

        self.seg = Segmented([("groups", "filter_groups", True), ("fav", "filter_fav", True)])
        self.seg.set_current("groups")
        self.seg.changed.connect(self._set_mode)
        root.addWidget(self.seg)

        self.holder = QVBoxLayout()
        self.holder.setSpacing(14)
        root.addLayout(self.holder)
        root.addStretch(1)
        skin.changed.connect(self.retranslate)
        self.retranslate()

    def retranslate(self):
        self.title.setText(tr("fav_title"))
        self.sub.setText(tr("fav_sub"))
        self.reload()

    def _set_mode(self, mode):
        self.mode = mode
        self.reload()

    # ------------------------------------------------------------------ build
    def _clear(self):
        while self.holder.count():
            it = self.holder.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def reload(self):
        self._clear()
        groups = self.db.list_groups()
        if self.mode == "fav":
            items = self.db.list_dns(favorites_only=True)
            if not items:
                self.holder.addWidget(label(tr("empty_fav"), "sub", wrap=True, align=Qt.AlignCenter))
                return
            card = Card("card")
            v = QVBoxLayout(card)
            v.setContentsMargins(12, 12, 12, 12)
            v.setSpacing(8)
            for d in items:
                v.addWidget(DnsRow(self, d, show_group=True))
            self.holder.addWidget(card)
            return
        if not groups:
            self.holder.addWidget(label(tr("empty_all"), "sub", wrap=True, align=Qt.AlignCenter))
            return
        for g in groups:
            self.holder.addWidget(self._section(g))

    def _section(self, g):
        card = Card("card")
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        h = QHBoxLayout()
        h.setSpacing(10)
        h.addWidget(IconChip("folder", "accent2", 36, 18))
        t = QVBoxLayout()
        t.setSpacing(0)
        t.addWidget(ElidedLabel(g["name"], "title"))
        t.addWidget(label(tr("group_count", n=g["count"]), "sub"))
        h.addLayout(t, 1)
        add = IconButton("plus", "sub", 20, "add_dns", pad=12)
        more = IconButton("more", "sub", 20, "tip_more", pad=12)
        add.clicked.connect(lambda: self.add_dns(g["id"]))
        more.clicked.connect(lambda: self.group_menu(g, more))
        h.addWidget(add)
        h.addWidget(more)
        v.addLayout(h)
        items = self.db.list_dns(g["id"])
        if not items:
            v.addWidget(label(tr("empty_group"), "sub", align=Qt.AlignCenter))
        for d in items:
            v.addWidget(DnsRow(self, d))
        return card

    # ------------------------------------------------------------------ actions
    def _done(self, toast=None):
        self.w.data_changed()
        if toast:
            self.w.toast(tr(toast), "ok")

    def toggle_fav(self, d):
        self.db.set_favorite(d["id"], not d["is_favorite"])
        self._done()

    def toggle_pin(self, d):
        self.db.set_pinned(d["id"], not d["is_pinned"])
        self._done()

    def add_dns(self, group_id=None):
        groups = self.db.list_groups()
        if not groups:
            inform(self.w, tr("err_need_group"))
            return
        dlg = DnsDialog(self.w, groups, default_group=group_id if isinstance(group_id, int) else None)
        if dlg.exec() and dlg.values:
            self.db.add_dns(*dlg.values)
            self._done("msg_saved")

    def edit_dns(self, d):
        dlg = DnsDialog(self.w, self.db.list_groups(), dns=d)
        if dlg.exec() and dlg.values:
            if self._is_connected(d["id"]) and dlg.values[1] != d["primary_ip"]:
                inform(self.w, tr("confirm_del_connected"))
                return
            self.db.update_dns(d["id"], *dlg.values)
            self._done("msg_saved")

    def _is_connected(self, dns_id):
        c = self.w.home.conn
        return bool(c) and c.get("dns_id") == dns_id

    def delete_dns(self, d):
        if self._is_connected(d["id"]):
            inform(self.w, tr("confirm_del_connected"))
            return
        if confirm(self.w, tr("confirm_del_dns", name=d["name"]), "btn_delete", danger=True):
            self.db.delete_dns(d["id"])
            self._done("msg_deleted")

    def row_menu(self, d, anchor):
        m = QMenu(self)
        m.addAction(tr("m_use"), lambda: self.w.use_dns(d["id"]))
        m.addAction(tr("m_edit"), lambda: self.edit_dns(d))
        m.addAction(tr("m_unpin") if d["is_pinned"] else tr("m_pin"), lambda: self.toggle_pin(d))
        m.addAction(tr("m_unfav") if d["is_favorite"] else tr("m_fav"), lambda: self.toggle_fav(d))
        others = [g for g in self.db.list_groups() if g["id"] != d["group_id"]]
        if others:
            sub = m.addMenu(tr("m_move"))
            for g in others:
                sub.addAction(g["name"], lambda gid=g["id"]: self._move(d, gid))
        m.addSeparator()
        m.addAction(tr("m_delete"), lambda: self.delete_dns(d))
        self.w.blur_on()
        try:
            m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        finally:
            self.w.blur_off()

    def _move(self, d, gid):
        self.db.move_dns(d["id"], gid)
        self._done("msg_saved")

    def add_group(self):
        dlg = GroupDialog(self.w, "dlg_new_group")
        if dlg.exec() and dlg.result_name:
            self.db.add_group(dlg.result_name)
            self._done("msg_saved")

    def group_menu(self, g, anchor):
        m = QMenu(self)
        m.addAction(tr("m_rename"), lambda: self.rename_group(g))
        m.addAction(tr("m_delete_group"), lambda: self.delete_group(g))
        self.w.blur_on()
        try:
            m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        finally:
            self.w.blur_off()

    def rename_group(self, g):
        dlg = GroupDialog(self.w, "dlg_rename_group", g["name"])
        if dlg.exec() and dlg.result_name:
            self.db.rename_group(g["id"], dlg.result_name)
            self._done("msg_saved")

    def delete_group(self, g):
        c = self.w.home.conn
        if c and any(d["id"] == c.get("dns_id") for d in self.db.list_dns(g["id"])):
            inform(self.w, tr("confirm_del_connected"))
            return
        if confirm(self.w, tr("confirm_del_group", name=g["name"], n=g["count"]), "btn_delete", danger=True):
            self.db.delete_group(g["id"])
            self._done("msg_deleted")
