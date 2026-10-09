"""Release identity and compatibility; isolated databases only."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from PySide6.QtWidgets import QApplication
from database.startup import prepare_database
from gui.about import AboutPage
from PySide6.QtWidgets import QLabel
from version import APP_NAME, APP_VERSION, DB_SCHEMA_VERSION, BACKUP_FORMAT_VERSION


class NekozzzIdentityTests(unittest.TestCase):
    def test_identity_and_versions(self):
        self.assertEqual((APP_NAME, APP_VERSION), ('Nekozzz', '0.9.3'))
        self.assertEqual((DB_SCHEMA_VERSION, BACKUP_FORMAT_VERSION), (1, 1))
        app = QApplication.instance() or QApplication([])
        dialog = AboutPage()
        identity = '\n'.join(label.text() for label in dialog.findChildren(QLabel))
        self.assertIn('Version 0.9.3', identity)
        self.assertIn('1Hey-p1g', identity)
        self.assertIn('GNU Affero General Public License v3.0', identity)
        from version import APP_LICENSE
        self.assertEqual(APP_LICENSE, 'AGPL-3.0-only')
        dialog.close()
        dialog.deleteLater()
        app.processEvents()

    def test_packaging_identity(self):
        spec = Path('Nekozzz.spec').read_text(encoding='utf-8')
        self.assertIn('name=APP_NAME', spec)
        self.assertIn("('FileVersion',APP_VERSION+'.0')", spec)
        self.assertIn("('OriginalFilename',APP_NAME+'.exe')", spec)
        self.assertIn("('LegalCopyright','Copyright © 2026 1Hey-p1g')", spec)
        self.assertNotIn('CompanyName', spec)
        self.assertIn("root/'resources/icon.ico'", spec)
        self.assertIn('Nekozzz.spec', Path('build_windows.ps1').read_text(encoding='utf-8'))
        self.assertIn('<string>Nekozzz</string>', Path('ui/main_window.ui').read_text(encoding='utf-8'))

    def test_default_database_compatibility(self):
        with tempfile.TemporaryDirectory(prefix='Nekozzz_identity_') as folder:
            path = prepare_database(packaged=True, data_root=Path(folder))
            self.assertEqual(path, Path(folder)/'database/TenderSystem-v1.db')
            before = path.read_bytes()
            self.assertEqual(prepare_database(packaged=True, data_root=Path(folder)), path)
            self.assertEqual(before, path.read_bytes())

    def test_license_and_notice_resources(self):
        text = Path('LICENSE').read_text(encoding='utf-8')
        self.assertIn('GNU AFFERO GENERAL PUBLIC LICENSE', text)
        self.assertIn('Version 3, 19 November 2007', text)
        self.assertIn('END OF TERMS AND CONDITIONS', text)
        self.assertTrue(Path('licenses/manifest.json').is_file())
        self.assertTrue(Path('THIRD_PARTY_NOTICES.md').is_file())
