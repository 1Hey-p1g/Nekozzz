"""Portable first launch initializes V1; development requires an explicit DB."""

import argparse
import sqlite3
import sys

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
from config.paths import resource_path
from services.settings import SettingsService
from gui.theme import ThemeManager
from version import APP_NAME

from gui.main_window import build_main_window
from services.people import PeopleService
from database.startup import prepare_database


def main(argv=None):
    parser = argparse.ArgumentParser(description="Nekozzz 人员及证书工作台")
    parser.add_argument("--database", help="独立的 V1 SQLite 数据库文件；旧正式 tender.db 禁用")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(resource_path('resources/icon.png'))))
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Nekozzz.Desktop')
    app.theme_manager = ThemeManager(app)
    app.theme_manager.apply(SettingsService().load().theme)
    if not args.database and not getattr(sys, 'frozen', False):
        parser.error('开发模式必须使用 --database 明确指定独立 V1 数据库')
    try:
        database_path = prepare_database(args.database)
    except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError) as error:
        QMessageBox.critical(None, "无法打开 V1 数据库", str(error))
        return 2
    window = build_main_window(PeopleService(database_path), database_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
