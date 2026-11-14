"""Nexus DNS - entry point."""
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.db import Database
from app.paths import data_dir, resource_path
from app.skin import skin, tr


def setup_logging():
    h = RotatingFileHandler(data_dir() / "app.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h])

    def hook(t, v, tb):
        logging.getLogger("dnschanger").error("Unhandled: %s", "".join(traceback.format_exception(t, v, tb)))
    sys.excepthook = hook


def main():
    setup_logging()
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DNSChanger.App")
        except Exception:
            pass
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Nexus DNS")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(resource_path("assets/icon.png")))

    db = Database(data_dir() / "dns_changer.db")
    skin.theme, skin.lang = db.get("theme"), db.get("lang")

    lock = QLockFile(str(data_dir() / "app.lock"))
    if not lock.tryLock(200):
        skin.apply()
        QMessageBox.information(None, "Nexus DNS", tr("already_running"))
        return 0

    skin.apply()
    from app.main_window import MainWindow
    win = MainWindow(db)
    win.show()
    code = app.exec()
    lock.unlock()
    db.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
