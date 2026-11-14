"""Theme (dark / light), language and global stylesheet - one switch, applied live."""
from string import Template

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication

from . import i18n

DARK = dict(
    bg="#0b0a13", bg2="#12102a", glow="#2a1b6e", card="#15132a", card2="#1b1936", border="#2b2852",
    panel="#181630", text="#f3f2ff", sub="#9d99c0", accent="#7c4dff", accent2="#a07bff",
    good="#22c55e", warn="#f5c518", bad="#ef4444", off="#7f7d96", input="#1a1832", hover="#252245",
    chip="#221f45", good_bg="rgba(34,197,94,0.10)", bad_bg="rgba(239,68,68,0.10)", warn_bg="rgba(245,197,24,0.10)",
    shadow="#000000")
LIGHT = dict(
    bg="#f4f4f9", bg2="#ebebf4", glow="#d9ccff", card="#ffffff", card2="#f5f5fb", border="#e1e1ec",
    panel="#ffffff", text="#17171d", sub="#6a6a7c", accent="#6a47f5", accent2="#8a6bff",
    good="#16a34a", warn="#d49a00", bad="#dc2626", off="#9a9aab", input="#f0f0f7", hover="#ebebf5",
    chip="#ece8ff", good_bg="rgba(22,163,74,0.10)", bad_bg="rgba(220,38,38,0.08)", warn_bg="rgba(212,154,0,0.10)",
    shadow="#000000")

QSS = Template(r"""
* { font-family: "Segoe UI", "Tahoma", "Vazirmatn", "Noto Sans Arabic", "DejaVu Sans", sans-serif; }
QWidget { color: $text; font-size: 10pt; }
QLabel { background: transparent; }
QLabel[role="h1"] { font-size: 17pt; font-weight: 700; }
QLabel[role="title"] { font-size: 11.5pt; font-weight: 600; }
QLabel[role="sub"] { color: $sub; font-size: 9pt; }
QLabel[role="accent"] { color: $accent2; font-size: 10pt; font-weight: 600; }
QLabel[role="value"] { font-size: 12pt; font-weight: 700; }
QLabel[role="stat"] { font-size: 13pt; font-weight: 700; }
QLabel#chip { background: $chip; border-radius: 13px; }
QFrame#card { background: $card; border: 1px solid $border; border-radius: 22px; }
QFrame#card2 { background: $card2; border: 1px solid $border; border-radius: 16px; }
QFrame#card2[sel="true"] { border: 1px solid $accent; }
QFrame#status { background: $card; border: 1px solid $border; border-radius: 22px; }
QFrame#status[state="online"] { background: $good_bg; border: 1px solid $good; }
QFrame#status[state="offline"] { background: $bad_bg; border: 1px solid $bad; }
QFrame#status[state="domestic"] { background: $warn_bg; border: 1px solid $warn; }
QFrame#sep { background: $border; border: none; min-height: 1px; max-height: 1px; }
QFrame#vsep { background: $border; border: none; min-width: 1px; max-width: 1px; }
QFrame#dialogPanel { background: $panel; border: 1px solid $border; border-radius: 24px; }
QFrame#popup { background: $panel; border: 1px solid $border; border-radius: 18px; }
QFrame#navbar { background: $card; border: 1px solid $border; border-radius: 26px; }
QPushButton { outline: none; }
QPushButton#primary { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 $accent, stop:1 $accent2);
  color: white; border: none; border-radius: 26px; padding: 15px 20px; font-size: 11.5pt; font-weight: 700; }
QPushButton#primary:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 $accent2, stop:1 $accent2); }
QPushButton#primary:disabled { background: $card2; color: $off; border: 1px solid $border; }
QPushButton#danger { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #e11d48, stop:1 #f43f5e);
  color: white; border: none; border-radius: 26px; padding: 15px 20px; font-size: 11.5pt; font-weight: 700; }
QPushButton#danger:hover { background: #fb4468; }
QPushButton#danger:disabled { background: $card2; color: $off; border: 1px solid $border; }
QPushButton#secondary { background: $card2; border: 1px solid $border; border-radius: 15px; padding: 10px 16px; font-weight: 600; }
QPushButton#secondary:hover { background: $hover; }
QPushButton#secondary:disabled { color: $off; }
QPushButton#iconbox { background: $card2; border: 1px solid $border; border-radius: 14px; padding: 0px; }
QPushButton#iconbox:hover { background: $hover; border: 1px solid $accent; }
QPushButton#iconbox:disabled { background: $card2; }
QPushButton#tile { background: $card; border: 1px solid $border; border-radius: 22px; }
QPushButton#tile:hover { background: $hover; }
QPushButton#tile:disabled { background: $card; }
QPushButton#iconbtn { background: transparent; border: none; border-radius: 12px; }
QPushButton#iconbtn:hover { background: $hover; }
QPushButton#iconbtn:disabled { background: transparent; }
QPushButton#winbtn { background: transparent; border: none; border-radius: 8px; }
QPushButton#winbtn:hover { background: $hover; }
QPushButton#winclose { background: transparent; border: none; border-radius: 8px; }
QPushButton#winclose:hover { background: $bad; }
QFrame#seg { background: $input; border: 1px solid $border; border-radius: 15px; }
QPushButton#segbtn { background: transparent; border: none; border-radius: 12px; padding: 7px 14px; color: $sub; font-weight: 600; }
QPushButton#segbtn:checked { background: $accent; color: white; }
QPushButton#chipbtn { background: $input; border: 1px solid $border; border-radius: 16px; padding: 0px 8px; color: $sub; font-weight: 600; }
QPushButton#chipbtn:checked { background: $accent; border: 1px solid $accent; color: white; }
QLineEdit, QSpinBox { background: $input; border: 1px solid $border; border-radius: 14px; padding: 10px 14px; selection-background-color: $accent; selection-color: white; }
QLineEdit:focus, QSpinBox:focus { border: 1px solid $accent; }
QSpinBox { padding: 6px 2px; font-weight: 700; font-size: 11pt; color: $text; }
QSpinBox::up-button, QSpinBox::down-button { width: 0px; height: 0px; border: none; }
QSpinBox QLineEdit { background: transparent; border: none; padding: 0px; }
QComboBox { background: $input; border: 1px solid $border; border-radius: 15px; padding: 9px 30px; font-weight: 600; }
QComboBox:hover { border: 1px solid $accent; }
QComboBox::drop-down { border: none; width: 0px; }
QComboBox::down-arrow { image: none; width: 0px; }
QComboBox QAbstractItemView { background: $panel; border: 1px solid $border; border-radius: 12px; padding: 4px;
  selection-background-color: $accent; selection-color: white; outline: 0; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: $off; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { background: $input; border: none; border-radius: 5px; min-height: 10px; max-height: 10px; text-align: center; color: transparent; }
QProgressBar::chunk { border-radius: 5px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 $accent, stop:1 $accent2); }
QMenu { background: $panel; border: 1px solid $border; border-radius: 14px; padding: 6px; }
QMenu::item { padding: 9px 26px; border-radius: 9px; }
QMenu::item:selected { background: $hover; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QToolTip { background: $panel; color: $text; border: 1px solid $border; padding: 6px 9px; border-radius: 8px; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { border-radius: 12px; }
QListWidget::item:hover { background: $hover; }
QListWidget::item:selected { background: $chip; }
QLabel#toast { border-radius: 16px; padding: 12px 18px; font-weight: 600; }
""")


class Skin(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.theme = "dark"
        self.lang = "fa"

    @property
    def p(self):
        return DARK if self.theme == "dark" else LIGHT

    @property
    def rtl(self):
        return self.lang == "fa"

    def apply(self, theme=None, lang=None):
        if theme:
            self.theme = theme
        if lang:
            self.lang = lang
        app = QApplication.instance()
        if app:
            app.setStyleSheet(QSS.substitute(self.p))
            app.setLayoutDirection(Qt.RightToLeft if self.rtl else Qt.LeftToRight)
            font = QFont("Segoe UI", 10)
            font.setStyleStrategy(QFont.PreferAntialias)
            app.setFont(font)
        self.changed.emit()


skin = Skin()


def tr(key: str, **kw) -> str:
    text = i18n.STRINGS.get(skin.lang, {}).get(key) or i18n.STRINGS["en"].get(key, key)
    return text.format(**kw) if kw else text


def col(name: str) -> str:
    """Palette role -> hex; a raw '#rrggbb' passes through."""
    return skin.p.get(name, name)


def qcol(name: str, alpha: float = 1.0) -> QColor:
    c = QColor(col(name))
    c.setAlphaF(alpha)
    return c
