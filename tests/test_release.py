import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from services.settings import PdfSettings, SettingsService
from gui.theme import resolve_theme, dark_stylesheet
import config.paths as paths

class ReleaseTests(unittest.TestCase):
    def test_resource_icon(self):
        from PIL import Image
        with Image.open(paths.resource_path('resources/icon.ico')) as icon:
            self.assertEqual(icon.ico.sizes(), {(s,s) for s in (16,24,32,48,64,128,256)})
        with self.assertRaises(ValueError):
            paths.resource_path('../outside')

    def test_frozen_paths(self):
        try:
            with patch.object(sys,'frozen',True,create=True), patch.object(sys,'_MEIPASS','C:/release/_internal',create=True), patch.object(sys,'executable','C:/release/TenderSystem.exe'):
                importlib.reload(paths)
                self.assertEqual(paths.DATA_ROOT,Path('C:/release').resolve())
                self.assertEqual(paths.SETTINGS_FILE,paths.DATA_ROOT/'config/settings.json')
                self.assertEqual(paths.resource_path('resources/icon.png'),Path('C:/release/_internal/resources/icon.png'))
                self.assertNotEqual(paths.DATA_ROOT,paths.RESOURCE_ROOT)
        finally:
            importlib.reload(paths)

    def test_theme_settings(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as directory:
            service=SettingsService(Path(directory)/'settings.json')
            self.assertEqual(service.load().theme,'system')
            service.save(replace(PdfSettings(),theme='dark'))
            self.assertEqual(service.load().theme,'dark')
        with patch('gui.theme.system_theme',return_value='dark'):
            self.assertEqual(resolve_theme('system'),'dark')
            self.assertEqual(resolve_theme('light'),'light')
        self.assertIn('#223044',dark_stylesheet('background: white; color: #23405d;'))

    def test_theme_control_single_save_and_reload(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        from gui.settings_page import SettingsPage
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            service=SettingsService(Path(directory)/'settings.json')
            with patch.object(service,'save',wraps=service.save) as save:
                page=SettingsPage(service,lambda _:None)
                events=[]
                page.theme_changed.connect(events.append)
                self.assertEqual(save.call_count,0)
                page.theme.setCurrentIndex(2)
                self.assertEqual(save.call_count,1)
                self.assertEqual(events,['dark'])
                page.show_settings(service.load())
                self.assertEqual(save.call_count,1)
                self.assertEqual(page.theme.currentIndex(),2)
                page.close(); page.deleteLater(); app.processEvents()
