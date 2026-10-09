"""Target routing, persistence and GUI wiring, without real Office writes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from dataclasses import replace
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import pywintypes
from PySide6.QtWidgets import QApplication

from database.initializer import create_empty_database
from gui.main_window import build_main_window
from gui.settings_page import SettingsPage
from services.people import PeopleService
from services.settings import SettingsService, PdfSettings
from services.office_writer import OfficeWriterConnector, writer_error_message
from services.word_service import WordNoActiveDocumentError, WordNotRunningError, WordOperationError
from tests import test_word_service as fixture


class OfficeWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='Nekozzz_office_writer_')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.settings = SettingsService(self.root / 'settings.json')

    def test_running_matrix_never_falls_back_or_launches(self):
        for running in ((), ('word',), ('wps',), ('word', 'wps')):
            for target in ('word', 'wps'):
                with self.subTest(running=running, target=target):
                    self.settings.save(replace(PdfSettings(), writer_target=target))
                    app = SimpleNamespace()
                    calls = []
                    def get(progid):
                        calls.append(progid)
                        key = 'wps' if progid == 'KWPS.Application' else 'word'
                        if key not in running:
                            raise pywintypes.com_error(-2147221021, 'not running', None, None)
                        return app
                    factory = OfficeWriterConnector(self.settings, get)
                    if target in running:
                        self.assertIs(app, factory().application)
                    else:
                        with self.assertRaises(WordNotRunningError):
                            factory()
                    self.assertEqual(['KWPS.Application' if target == 'wps' else 'Word.Application'], calls)

    def test_no_document_and_lost_com_are_target_specific(self):
        self.settings.save(replace(PdfSettings(), writer_target='wps'))
        app = SimpleNamespace(Documents=SimpleNamespace(Count=0))
        service = OfficeWriterConnector(self.settings, lambda _: app)()
        with self.assertRaisesRegex(WordNoActiveDocumentError, 'WPS Writer'):
            service.active_document()
        app.Documents.Count = 1
        app.ActiveDocument = object()
        app.Selection = fixture.FakeSelection()
        app.Selection.TypeText = Mock(side_effect=pywintypes.com_error(-1, 'lost COM', None, None))
        with self.assertRaisesRegex(WordOperationError, 'WPS Writer.*lost COM'):
            service.insert_text('test')
        self.assertIn('WPS Writer', writer_error_message(WordNotRunningError(), 'wps'))

    def test_worker_cannot_acquire_com(self):
        get = Mock()
        errors = []
        def run():
            try:
                OfficeWriterConnector(self.settings, get)()
            except Exception as error:
                errors.append(error)
        thread = Thread(target=run)
        thread.start()
        thread.join()
        self.assertIsInstance(errors[0], WordOperationError)
        get.assert_not_called()

    def test_legacy_default_and_target_persistence_without_init_write(self):
        self.settings.path.write_text('{"dpi":300}', encoding='utf-8')
        self.assertEqual('word', self.settings.load().writer_target)
        before = self.settings.path.read_bytes()
        page = SettingsPage(self.settings, lambda _: None)
        self.addCleanup(page.close)
        self.assertEqual(before, self.settings.path.read_bytes())
        page.writer_target.setCurrentIndex(page.writer_target.findData('wps'))
        self.assertEqual('wps', SettingsService(self.settings.path).load().writer_target)
        self.assertEqual(300, self.settings.load().dpi)
        with patch.object(self.settings, 'save', side_effect=OSError('cannot write')):
            page.writer_target.setCurrentIndex(page.writer_target.findData('word'))
        self.assertEqual('wps', page.writer_target.currentData())
        self.assertIn('cannot write', page.error_label.text())

    def test_every_main_window_output_shares_factory_and_status(self):
        db = self.root / 'test.db'
        create_empty_database(db)
        window = build_main_window(PeopleService(db), db, settings_service=self.settings)
        self.addCleanup(window.close)
        pages = [window.person_word_page, window.person_autofill_page,
                 window.project_search_page, window.qualification_search_page,
                 window.award_search_page, window.finance_search_page]
        factory = pages[0].output_service.word_factory
        for page in pages:
            self.assertIs(factory, page.output_service.word_factory)
        window.settings_page.writer_target.setCurrentIndex(1)
        self.assertIn('WPS Writer', window.statusBar().currentMessage())
        self.assertEqual('wps', self.settings.load().writer_target)

    def test_default_word_primitives_and_explicit_wps_share_algorithm(self):
        for target in ('word', 'wps'):
            self.settings.save(replace(PdfSettings(), writer_target=target))
            selection = fixture.FakeSelection()
            document = SimpleNamespace(Styles=fixture.FakeStyles())
            app = SimpleNamespace(Documents=SimpleNamespace(Count=1), ActiveDocument=document, Selection=selection)
            service = OfficeWriterConnector(self.settings, lambda _: app)()
            service.set_selection_style(use_normal=True)
            service.insert_text('first')
            service.insert_paragraph()
            service.insert_text('second')
            service.insert_page_break()
            self.assertEqual([('text', 'first'), ('paragraph',), ('text', 'second'), ('break', 7)], selection.calls)
