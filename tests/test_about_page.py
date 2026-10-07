import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QStackedWidget
from database.initializer import create_empty_database
from services.people import PeopleService
from services.settings import SettingsService
from gui.main_window import build_main_window
from version import APP_NAME, APP_SUBTITLE, APP_COPYRIGHT, APP_VERSION


class AboutPageTests(unittest.TestCase):
    def test_navigation_identity_icon_and_themes(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix='Nekozzz_about_') as folder:
            db = Path(folder) / 'test.db'
            create_empty_database(db)
            settings = SettingsService(Path(folder) / 'settings.json')
            window = build_main_window(PeopleService(db), db, settings_service=settings)
            try:
                window.show()
                app.processEvents()
                about = window.findChild(QPushButton, 'navAbout')
                settings_button = window.findChild(QPushButton, 'navSettings')
                nav = settings_button.parentWidget().layout()
                self.assertEqual(nav.indexOf(about), nav.indexOf(settings_button) + 1)
                self.assertGreater(about.y(), settings_button.y())
                stack = window.findChild(QStackedWidget, 'workspace')
                before = set(w for w in app.allWidgets() if isinstance(w, QDialog))
                about.click()
                app.processEvents()
                self.assertIs(stack.currentWidget(), window.about_page)
                self.assertTrue(about.isChecked())
                self.assertFalse(settings_button.isChecked())
                self.assertEqual(before, set(w for w in app.allWidgets() if isinstance(w, QDialog)))
                self.assertIsNone(app.activeModalWidget())
                self.assertIsNone(window.menuWidget())
                texts = [label.text() for label in window.about_page.findChildren(QLabel)]
                for text in (APP_NAME, APP_SUBTITLE, f'Version {APP_VERSION}',
                             'Developed by 1Hey-p1g', APP_COPYRIGHT,
                             'Licensed under the GNU Affero General Public License v3.0'):
                    self.assertIn(text, texts)
                pixmap = window.about_page.icon.pixmap()
                self.assertFalse(pixmap.isNull())
                self.assertLessEqual(pixmap.width(), 96)
                self.assertLessEqual(pixmap.height(), 96)
                for theme in ('light', 'dark', 'system'):
                    app.theme_manager.apply(theme)
                    app.processEvents()
                    self.assertIs(stack.currentWidget(), window.about_page)
                    settings_button.click()
                    self.assertIs(stack.currentWidget(), window.settings_page)
                    window.findChild(QPushButton, 'navPersonSearch').click()
                    self.assertIs(stack.currentWidget(), window.search_page)
                    about.click()
                    self.assertIs(stack.currentWidget(), window.about_page)
                self.assertFalse(settings.path.exists())
            finally:
                app.theme_manager.apply('system')
                window.close()
                window.deleteLater()
                app.processEvents()
