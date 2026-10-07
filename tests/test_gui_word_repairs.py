"""Narrow regression tests; temporary databases and fake Word only."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox
from gui.common import ImagePreview, ImageViewer
from gui.word_styles import confirm_style_fallback
from tests import test_projects, test_person_word
from services.person_word import PersonWordJob, PersonWordPreflightError
from services.project_word import ProjectWordPreflightError


class StyleWord(test_person_word.FakeWord):
    def missing_styles(self, names):
        return [name for name in names if name in self.missing]

    def normal_style(self):
        return object()

    def set_selection_style(self, name=None, *, use_normal=False):
        self.calls.append(('style', 'builtin-normal' if use_normal else name))


class Repairs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def fixture(self, cls):
        fixture = cls()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_fallback_matrix_person_and_project(self):
        for kind in ('person', 'project'):
            fixture = self.fixture(test_person_word.PersonWordTests if kind == 'person' else test_projects.ProjectTests)
            if kind == 'person':
                output, settings = fixture.output, fixture.settings
                job = PersonWordJob()
                job.add(1)
                job.item(1).selected_certificate_ids.add(5)
                flag, error = 'insert_person_name', PersonWordPreflightError
            else:
                _, output, job, settings = fixture.output_fixture()
                flag, error = 'insert_project_name', ProjectWordPreflightError
            before = settings
            for with_name, missing, answer in (
                (True, [], True), (False, ['图片'], False),
                (False, ['图片'], True), (True, ['标题 4'], True),
                (True, ['图片', '标题 4'], True), (False, ['标题 4'], True),
            ):
                with self.subTest(kind=kind, name=with_name, missing=missing, answer=answer):
                    word = StyleWord()
                    word.missing = missing
                    output.word_factory = lambda: word
                    setattr(job, flag, with_name)
                    prompts = []
                    def confirm(details):
                        prompts.append(details)
                        return answer
                    required_missing = set(missing) & ({'图片', '标题 4'} if with_name else {'图片'})
                    if required_missing and not answer:
                        with self.assertRaises(error):
                            output.insert(job, settings, confirm_style_fallback=confirm)
                        self.assertFalse(any(c[0] in ('style', 'image', 'text', 'paragraph', 'pagebreak') for c in word.calls))
                    else:
                        output.insert(job, settings, confirm_style_fallback=confirm)
                        styles = [c[1] for c in word.calls if c[0] == 'style']
                        self.assertIn('builtin-normal' if '图片' in required_missing else '图片', styles)
                        if with_name:
                            self.assertIn('builtin-normal' if '标题 4' in required_missing else '标题 4', styles)
                    self.assertEqual(int(bool(required_missing)), len(prompts))
                    self.assertEqual(before, settings)

    def test_single_shared_question(self):
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes) as question:
            self.assertTrue(confirm_style_fallback(None, [('图片样式', 'A'), ('文本样式', 'B')]))
            question.assert_called_once()

    def test_preview_click_and_original_scaling(self):
        preview = ImagePreview(large_view_enabled=True)
        self.addCleanup(preview.close)
        preview.resize(200, 200)
        preview.show()
        self.app.processEvents()
        with patch.object(ImageViewer, 'exec', return_value=0) as opened:
            QTest.mouseClick(preview, Qt.LeftButton)
            opened.assert_not_called()
            source = QPixmap(800, 400)
            source.fill(Qt.blue)
            preview._pixmap = source
            preview._rescale()
            QTest.mouseClick(preview, Qt.LeftButton)
            opened.assert_called_once()
            preview.large_view_enabled = False
            QTest.mouseClick(preview, Qt.LeftButton)
            self.assertEqual(1, opened.call_count)
        viewer = ImageViewer(source)
        self.addCleanup(viewer.close)
        viewer.show()
        for width, height in ((600, 400), (400, 600)):
            viewer.resize(width, height)
            self.app.processEvents()
            self.assertEqual(source.size(), viewer.original_pixmap.size())
            scaled = viewer.image.pixmap()
            self.assertAlmostEqual(2, scaled.width() / scaled.height(), delta=.02)

    def test_twenty_navigation_rounds_do_not_grow(self):
        fixture = self.fixture(test_projects.ProjectTests)
        fixture.service.save(fixture.a, {
            '项目名称': 'A配网', '项目主要内容': '长工程内容与换行验证。' * 150,
        }, 1)
        _, output, _, _ = fixture.output_fixture()
        from gui.main_window import build_main_window
        from services.people import PeopleService
        window = build_main_window(PeopleService(fixture.db), fixture.db,
            settings_service=fixture.settings, project_service=fixture.service,
            project_attachment_service=fixture.publisher, project_word_service=output)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        page = window.project_search_page
        page.job.add(fixture.a)
        page.refresh_task(fixture.a)
        window.findChild(QPushButton, 'navProjectSearch').click()
        QTest.qWait(10)
        # Settle row wrapping/minimum geometry before taking the navigation baseline.
        for _ in range(4):
            page.fit_tables()
            self.app.processEvents()
        self.assertIsNotNone(page.preview._pixmap)
        baseline = window.geometry()
        minimum = window.minimumSizeHint()
        for _ in range(20):
            for name in ('navPersonSearch', 'navProjectSearch', 'navPersonManage',
                         'navProjectManage', 'navSettings', 'navPersonSearch', 'navProjectSearch'):
                window.findChild(QPushButton, name).click()
                QTest.qWait(2)
                self.assertEqual(baseline, window.geometry())
                self.assertEqual(minimum, window.minimumSizeHint())
            page.fit_tables()
            required = sum(page.info_view.rowHeight(i) for i in range(min(4,page.info_model.rowCount())))
            self.assertGreaterEqual(page.info_view.viewport().height(),required)
        cap = page.info_view.maximumHeight()
        for _ in range(20):
            page.fit_tables()
        self.assertEqual(cap, page.info_view.maximumHeight())
        self.assertLessEqual(page.info_view.height(), int(page.right.height() * .45) + 1)
        self.assertGreater(page.info_view.verticalScrollBar().maximum(), 0)

    def test_gui_fallback_does_not_save_preferences(self):
        from services.settings import SettingsService
        from gui.person_word import PersonWordPage
        from gui.project_search import ProjectSearchPage
        for kind in ('person', 'project'):
            fixture = self.fixture(test_person_word.PersonWordTests if kind == 'person' else test_projects.ProjectTests)
            if kind == 'person':
                output, settings = fixture.output, fixture.settings
                job = PersonWordJob()
                job.add(1)
                job.item(1).selected_certificate_ids.add(5)
                page_type, service = PersonWordPage, fixture.people
            else:
                _, output, job, settings = fixture.output_fixture()
                page_type, service = ProjectSearchPage, fixture.service
            preferences = SettingsService(fixture.root / 'fallback-settings.json')
            preferences.save(settings)
            original = preferences.path.read_bytes()
            word = StyleWord()
            word.missing = ['图片']
            output.word_factory = lambda: word
            page = page_type(service, output, preferences, lambda _: None)
            self.addCleanup(page.close)
            page.job = job
            for answer in (QMessageBox.No, QMessageBox.Yes):
                with self.subTest(kind=kind, answer=answer):
                    word.calls.clear()
                    with patch.object(QMessageBox, 'question', return_value=answer) as prompt, \
                         patch.object(preferences, 'save', wraps=preferences.save) as save:
                        page.insert_to_word()
                        prompt.assert_called_once()
                        save.assert_not_called()
                    writes = [c for c in word.calls if c[0] in ('style', 'image', 'text', 'paragraph', 'pagebreak')]
                    if answer == QMessageBox.No:
                        self.assertEqual([], writes)
                    else:
                        self.assertIn(('style', 'builtin-normal'), writes)
                    self.assertEqual(original, preferences.path.read_bytes())
