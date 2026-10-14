"""Award/finance end-to-end workflows in external temporary V1 databases."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import hashlib
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QScrollArea, QStackedWidget

from database.initializer import create_empty_database
from database.runtime import runtime_connection
from gui.award_finance import AwardFinanceManagePage, ReportManagePage, ReportSearchPage
from gui.common import ImageViewer
from services.attachments import AwardAttachmentService, FinanceAttachmentService
from services.award_finance import AwardService, FinanceService
from services.pdf_import import RenderedPage
from services.report_word import ReportWordOutputService, ReportWordPreflightError, ReportWordWriteError
from services.settings import PdfSettings, SettingsService
from services.word_service import WordNotRunningError, WordNoActiveDocumentError
from tests.test_gui_word_repairs import StyleWord


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='TenderSystem_award_finance_')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.db = self.root / 'v1.db'
        create_empty_database(self.db)
        with runtime_connection(self.db, write=True) as connection:
            connection.executemany('INSERT INTO 公司业绩表(业绩ID,项目名称) VALUES(?,?)', [(1, '甲工程'), (2, '乙工程')])
        self.awards, self.finance = AwardService(self.db), FinanceService(self.db)
        self.a = self.awards.save(None, {'业绩ID': 1, '获奖名称': '优质工程奖', '获奖级别': '省级', '获奖年份': '2024'})
        self.b = self.awards.save(None, {'业绩ID': 2, '获奖名称': '安全奖', '获奖年份': '2025'})
        self.f = self.finance.save(None, {'财务报告年度': '2024', '营业收入': '1,234.50 万元', '净利润': ''})
        self.g = self.finance.save(None, {'财务报告年度': '2025年度', '营业收入': None, '净利润': '亏损(100)'})
        self.award_publisher = AwardAttachmentService(self.db, data_root=self.root)
        self.finance_publisher = FinanceAttachmentService(self.db, data_root=self.root)
        self.preferences = SettingsService(self.root / 'settings.json')
        self.word = StyleWord()
        self.award_output = ReportWordOutputService(self.awards.repository, data_root=self.root, word_factory=lambda: self.word)
        self.finance_output = ReportWordOutputService(self.finance.repository, data_root=self.root, word_factory=lambda: self.word)
        image = QImage(80, 120, QImage.Format_RGB32)
        image.fill(QColor('blue'))
        picture = self.root / 'page.jpg'
        image.save(str(picture), 'JPEG')
        self.pages = tuple(RenderedPage(i, picture) for i in (1, 2, 3))

    def domains(self):
        return ((self.awards, self.award_publisher, self.award_output, self.a, self.b),
                (self.finance, self.finance_publisher, self.finance_output, self.f, self.g))

    def show(self, page):
        self.addCleanup(page.close)
        page.resize(1200, 850)
        page.show()
        self.app.processEvents()
        return page

    def selection_page(self, service, output):
        return self.show(ReportSearchPage(service, output, self.preferences, lambda _: None))

    def management_page(self, service, publisher):
        return self.show(ReportManagePage(service, settings_service=self.preferences, attachment_service=publisher,
                                        notify=lambda _: None))

    def writes(self):
        return [call for call in self.word.calls if call[0] not in ('document', 'selection')]

    def test_real_schema_and_financial_text_preservation(self):
        with runtime_connection(self.db) as connection:
            self.assertEqual(['获奖ID', '业绩ID', '获奖名称', '获奖级别', '获奖年份'],
                             [row['name'] for row in connection.execute('PRAGMA table_info(获奖工程表)')])
            self.assertEqual(['INTEGER', 'TEXT', 'TEXT', 'TEXT'],
                             [row['type'] for row in connection.execute('PRAGMA table_info(财务报告表)')])
            self.assertEqual(13, connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0])
        row = self.finance.repository.get(self.f)
        self.assertEqual('1,234.50 万元', row['营业收入'])
        self.assertEqual('', row['净利润'])
        changed = {**row, '营业收入': '  000.00 元  ', '净利润': None}
        self.finance.save(self.f, changed)
        self.assertEqual('  000.00 元  ', self.finance.repository.get(self.f)['营业收入'])
        self.assertIsNone(self.finance.repository.get(self.f)['净利润'])
        with self.assertRaises(ValueError):
            self.finance.save(self.f, {**changed, '营业收入': 100})
        self.assertEqual('  000.00 元  ', self.finance.repository.get(self.f)['营业收入'])

    def test_search_and_stable_year_order(self):
        for service, _, _, first, recent in self.domains():
            self.assertEqual([first, recent], [r[service.repository.key] for r in service.search()])
            self.assertEqual([first], [r[service.repository.key] for r in service.search(year='2024')])
            self.assertEqual([], service.search(year="' OR 1=1 --"))
            self.assertEqual([], service.search(year='%'))
        self.assertEqual([self.a], [r['获奖ID'] for r in self.awards.search(name='优质', year='2024', grade='省', project='甲')])
        self.assertEqual([], self.awards.search(name='优质', project='乙'))
        third = self.awards.save(None, {'业绩ID': 1, '获奖名称': '未知年份', '获奖年份': None})
        fourth = self.awards.save(None, {'业绩ID': 1, '获奖名称': '同年份', '获奖年份': '2025年'})
        self.assertEqual([self.a, self.b, third, fourth], [r['获奖ID'] for r in self.awards.search()])

    def test_crud_invalid_input_fk_and_restrict(self):
        for service, publisher, _, record_id, _ in self.domains():
            with self.subTest(domain=service.repository.label):
                row = service.repository.get(record_id)
                changed = {**row, service.repository.name_field: '修改后的文本'}
                service.save(record_id, changed)
                self.assertEqual('修改后的文本', service.repository.get(record_id)[service.repository.name_field])
                with self.assertRaises(ValueError):
                    service.save(record_id, {**changed, service.repository.name_field: '  '})
                if service is self.awards:
                    with self.assertRaises(sqlite3.IntegrityError):
                        service.save(record_id, {**changed, '业绩ID': 999})
                    self.assertEqual(1, service.repository.get(record_id)['业绩ID'])
                publisher.save_pages((record_id,), self.pages[:1])
                with self.assertRaisesRegex(ValueError, '关联附件'):
                    service.delete(record_id)
                with self.assertRaises(sqlite3.IntegrityError), runtime_connection(self.db, write=True) as connection:
                    connection.execute(f'DELETE FROM "{service.repository.table}" WHERE "{service.repository.key}"=?', (record_id,))
                publisher.delete_all((record_id,))
                service.delete(record_id)
                self.assertIsNone(service.repository.get(record_id))

    def test_attachment_numeric_order_and_own_table_only(self):
        for service, _, output, record_id, _ in self.domains():
            self.root.joinpath('Images').mkdir(exist_ok=True)
            with runtime_connection(self.db, write=True) as connection:
                for number in (10, 2, 1):
                    path = f'Images/{service.repository.key}-{number}.jpg'
                    (self.root / path).write_bytes(self.pages[0].path.read_bytes())
                    connection.execute(f'INSERT INTO "{service.repository.image_table}"("{service.repository.key}",路径,备注) VALUES(?,?,?)',
                                       (record_id, path, number if service is self.awards else str(number)))
                connection.execute("INSERT INTO 公司业绩图表(业绩ID,文件类型,路径,备注) VALUES(1,?,'Images/not-award.jpg',1)",
                                   (service.repository.label,))
            rows = service.repository.attachments(record_id)
            self.assertEqual([1, 2, 10], [int(r['备注']) for r in rows])
            plan = output.build_plan({record_id}, PdfSettings())
            self.assertEqual(3, plan.image_count)
            self.assertFalse(any('not-award' in str(image.path) for image in plan.blocks[0].images))

    def test_pdf_publication_replace_delete_and_actual_remark_types(self):
        for service, publisher, _, record_id, _ in self.domains():
            publisher.save_pages((record_id,), self.pages)
            rows = service.repository.attachments(record_id)
            self.assertEqual([1, 2, 3] if service is self.awards else ['1', '2', '3'], [r['备注'] for r in rows])
            for row in rows:
                uuid.UUID(Path(row['路径']).stem)
                self.assertEqual('Images', Path(row['路径']).parts[0])
                self.assertTrue((self.root / row['路径']).is_file())
            old = {self.root / row['路径'] for row in rows}
            publisher.save_pages((record_id,), self.pages[:1], replace=True)
            self.assertFalse(any(path.exists() for path in old))
            publisher.delete_all((record_id,))
            self.assertEqual([], service.repository.attachments(record_id))
        self.assertEqual([], list((self.root / 'Images').iterdir()))

    def test_failed_replace_rolls_back_rows_and_new_images(self):
        for service, publisher, _, record_id, _ in self.domains():
            publisher.save_pages((record_id,), self.pages)
            rows = service.repository.attachments(record_id)
            paths = set((self.root / 'Images').iterdir())
            actual = publisher.repository.replace_rows
            def fail_after_delete(connection, group, pages):
                actual(connection, group, pages)
                raise RuntimeError('injected after insert')
            with patch.object(publisher.repository, 'replace_rows', side_effect=fail_after_delete):
                with self.assertRaises(RuntimeError):
                    publisher.save_pages((record_id,), self.pages[:1], replace=True)
            self.assertEqual(rows, service.repository.attachments(record_id))
            self.assertEqual(paths, set((self.root / 'Images').iterdir()))

    def test_shared_paths_remain_after_replace_and_delete(self):
        self.award_publisher.save_pages((self.a,), self.pages[:1])
        shared = self.awards.repository.attachments(self.a)[0]['路径']
        with runtime_connection(self.db, write=True) as connection:
            connection.execute('INSERT INTO 财务报告图表(年度ID,路径,备注) VALUES(?,?,NULL)', (self.f, shared))
        self.award_publisher.save_pages((self.a,), self.pages[:1], replace=True)
        self.assertTrue((self.root / shared).exists())
        self.finance_publisher.delete_all((self.f,))
        self.assertFalse((self.root / shared).exists())

    def test_word_title_and_no_title_multiblock_sequence(self):
        for service, publisher, output, first, recent in self.domains():
            publisher.save_pages((first,), self.pages[:2])
            publisher.save_pages((recent,), self.pages[:1])
            for titles in (False, True):
                self.word.calls.clear()
                plan = output.insert({first, recent}, PdfSettings(), insert_title=titles)
                self.assertEqual([recent, first], [block.record_id for block in plan.blocks])
                expected = []
                for block in plan.blocks:
                    if titles:
                        expected.extend([('style', '标题 4'), ('text', block.title), ('paragraph',)])
                    expected.append(('style', '图片'))
                    expected.extend([('image',)] * len(block.images))
                    expected.append(('pagebreak',))
                self.assertEqual(expected, [c[:1] if c[0] == 'image' else c for c in self.writes()])
                self.assertEqual(('pagebreak',), self.writes()[-1])
        self.assertEqual('2024年度财务报告', self.finance.repository.title(self.finance.repository.get(self.f)))
        self.assertEqual('2025年度财务报告', self.finance.repository.title(self.finance.repository.get(self.g)))

    def test_preflight_zero_writes_all_business_failures(self):
        for service, _, output, record_id, _ in self.domains():
            for ids in (set(), {999}, {record_id}):
                self.word.calls.clear()
                with self.assertRaises(ReportWordPreflightError):
                    output.insert(ids, PdfSettings())
                self.assertEqual([], self.word.calls)
            with runtime_connection(self.db, write=True) as connection:
                connection.execute(f'INSERT INTO "{service.repository.image_table}"("{service.repository.key}",路径) VALUES(?,?)',
                                   (record_id, 'Images/missing.jpg'))
            with self.assertRaisesRegex(ReportWordPreflightError, 'missing.jpg'):
                output.insert({record_id}, PdfSettings())
            self.assertEqual([], self.word.calls)

    def test_style_fallback_matrix_and_settings_unchanged(self):
        self.preferences.save(PdfSettings())
        before = self.preferences.path.read_bytes()
        for _, publisher, output, record_id, _ in self.domains():
            publisher.save_pages((record_id,), self.pages[:1])
            for titles, missing, answer in ((True, [], True), (False, ['标题 4'], True),
                                           (True, ['标题 4'], False), (True, ['标题 4'], True),
                                           (False, ['图片'], False), (False, ['图片'], True),
                                           (True, ['图片', '标题 4'], True)):
                self.word.calls.clear()
                self.word.missing = missing
                prompts = []
                def confirm(details):
                    prompts.append(details)
                    return answer
                needed = set(missing) & ({'图片', '标题 4'} if titles else {'图片'})
                if needed and not answer:
                    with self.assertRaises(ReportWordPreflightError):
                        output.insert({record_id}, self.preferences.load(), insert_title=titles, confirm_style_fallback=confirm)
                    self.assertEqual([], self.writes())
                else:
                    output.insert({record_id}, self.preferences.load(), insert_title=titles, confirm_style_fallback=confirm)
                    self.assertIn(('style', 'builtin-normal' if '图片' in needed else '图片'), self.writes())
                    if titles:
                        self.assertIn(('style', 'builtin-normal' if '标题 4' in needed else '标题 4'), self.writes())
                self.assertEqual(int(bool(needed)), len(prompts))
                self.assertEqual(before, self.preferences.path.read_bytes())

    def test_word_connection_and_partial_write_failure(self):
        for _, publisher, output, record_id, _ in self.domains():
            publisher.save_pages((record_id,), self.pages[:1])
            for error in (WordNotRunningError(), WordNoActiveDocumentError()):
                output.word_factory = lambda error=error: (_ for _ in ()).throw(error)
                with self.assertRaises(type(error)):
                    output.insert({record_id}, PdfSettings())
            output.word_factory = lambda: self.word
            self.word.calls.clear()
            self.word.fail_image = True
            with self.assertRaisesRegex(ReportWordWriteError, 'Word 插入未完整完成'):
                output.insert({record_id}, PdfSettings())
            self.assertFalse(any(c[0] == 'pagebreak' for c in self.word.calls))
            self.word.fail_image = False

    def test_selection_mouse_checkbox_copy_preview_no_database_writes(self):
        for service, publisher, output, record_id, recent in self.domains():
            publisher.save_pages((record_id,), self.pages[:1])
            before = hashlib.sha256(self.db.read_bytes()).digest()
            page = self.selection_page(service, output)
            index = next(i for i, row in enumerate(page.model.rows) if row[service.repository.key] == record_id)
            text_cell = page.model.index(index, 1)
            QTest.mouseClick(page.records_view.viewport(), Qt.LeftButton, pos=page.records_view.visualRect(text_cell).center())
            self.assertEqual(record_id, page.current_record_id)
            self.assertEqual(set(), page.selected_ids)
            self.assertIsNotNone(page.preview._pixmap)
            with patch.object(ImageViewer, 'exec', return_value=0) as opened:
                QTest.mouseClick(page.preview, Qt.LeftButton)
                opened.assert_called_once()
            check_cell = page.model.index(index, 0)
            QTest.mouseClick(page.records_view.viewport(), Qt.LeftButton, pos=page.records_view.visualRect(check_cell).center())
            self.assertEqual({record_id}, page.selected_ids)
            self.assertEqual(record_id, page.current_record_id)
            other = next(i for i, row in enumerate(page.model.rows) if row[service.repository.key] == recent)
            QTest.mouseClick(page.records_view.viewport(), Qt.LeftButton,
                             pos=page.records_view.visualRect(page.model.index(other, 1)).center())
            self.assertEqual(recent, page.current_record_id)
            self.assertEqual({record_id}, page.selected_ids)
            QTest.mouseDClick(page.info_view.viewport(), Qt.LeftButton,
                              pos=page.info_view.visualRect(page.info_model.index(0, 1)).center())
            self.assertEqual(service.repository.get(recent)[service.repository.name_field], QGuiApplication.clipboard().text())
            QGuiApplication.clipboard().setText('unchanged')
            QTest.mouseDClick(page.records_view.viewport(), Qt.LeftButton, pos=page.records_view.visualRect(page.model.index(other, 0)).center())
            self.assertEqual('unchanged', QGuiApplication.clipboard().text())
            page.filters['year'].setText('2024')
            page.search()
            self.assertTrue(record_id in page.selected_ids)
            page.insert_title.setChecked(True)
            page.hide()
            page.show()
            self.assertTrue(page.insert_title.isChecked())
            self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).digest())

    def test_missing_picture_placeholder_and_null_copy(self):
        with runtime_connection(self.db, write=True) as connection:
            connection.execute('INSERT INTO 财务报告图表(年度ID,路径) VALUES(?,?)', (self.g, 'Images/missing.jpg'))
        page = self.selection_page(self.finance, self.finance_output)
        index = next(i for i, row in enumerate(page.model.rows) if row['年度ID'] == self.g)
        page.records_view.setCurrentIndex(page.model.index(index, 1))
        self.assertIn('图片文件尚未就位', page.preview.text())
        QGuiApplication.clipboard().setText('unchanged')
        QTest.mouseDClick(page.info_view.viewport(), Qt.LeftButton,
                          pos=page.info_view.visualRect(page.info_model.index(1, 1)).center())
        self.assertEqual('unchanged', QGuiApplication.clipboard().text())

    def test_management_gui_crud_failure_retains_input_and_foreign_key(self):
        for service, publisher, _, _, _ in self.domains():
            page = self.management_page(service, publisher)
            page.new_record()
            name_field = service.repository.name_field
            page.inputs[name_field].setText('2026' if service is self.finance else '新增奖项')
            if page.project:
                page.project.setCurrentIndex(page.project.findData(2))
            page.save_record()
            record_id = page.record_id
            self.assertIsNotNone(record_id)
            if page.project:
                self.assertEqual(2, service.repository.get(record_id)['业绩ID'])
            page.set_mode('edit')
            page.inputs[name_field].setText('   ')
            page.save_record()
            self.assertIn('保存失败', page.error_label.text())
            self.assertEqual('   ', page.inputs[name_field].text())
            self.assertNotEqual('   ', service.repository.get(record_id)[name_field])
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
                page.records_view.selectRow(0)
            self.assertEqual(record_id, page.record_id)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
                page.cancel()
            publisher.save_pages((record_id,), self.pages[:1])
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                page.delete_record()
            self.assertIn('关联附件', page.error_label.text())
            publisher.delete_all((record_id,))
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                page.delete_record()
            self.assertIsNone(service.repository.get(record_id))

    def test_financial_gui_edit_keeps_text_null_empty(self):
        page = self.management_page(self.finance, self.finance_publisher)
        index = next(i for i, row in enumerate(page.model.rows) if row['年度ID'] == self.f)
        page.records_view.selectRow(index)
        page.set_mode('edit')
        page.inputs['营业收入'].setText('  000123.00元  ')
        page.save_record()
        row = self.finance.repository.get(self.f)
        self.assertEqual('  000123.00元  ', row['营业收入'])
        self.assertEqual('', row['净利润'])
        index = next(i for i, row in enumerate(page.model.rows) if row['年度ID'] == self.g)
        page.records_view.selectRow(index)
        page.set_mode('edit')
        page.inputs['净利润'].setText('负 100 万元')
        page.save_record()
        self.assertIsNone(self.finance.repository.get(self.g)['营业收入'])

    def test_gui_pdf_preview_rotate_cancel_confirm_replace_delete(self):
        source = self.root / 'test.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page(width=120, height=180)
            pdf.new_page(width=180, height=120)
            pdf.save(str(source))
        source_before = source.read_bytes()
        for service, publisher, _, _, _ in self.domains():
            page = self.management_page(service, publisher)
            editor = page.attachments
            self.assertTrue(editor.preview.large_view_enabled)
            before = self.db.read_bytes()
            existing = set((self.root / 'Images').glob('*')) if (self.root / 'Images').exists() else set()
            editor.start_pdf_import(source)
            temporary = editor.pages[0].path.parent
            editor.show_page(1)
            editor.rotate(90)
            editor.cancel_import()
            self.assertFalse(temporary.exists())
            self.assertEqual(before, self.db.read_bytes())
            self.assertEqual(existing, set((self.root / 'Images').glob('*')))
            editor.start_pdf_import(source)
            editor.confirm_import()
            self.assertEqual(2, len(editor.model.rows))
            with patch.object(ImageViewer, 'exec', return_value=0) as viewer:
                QTest.mouseClick(editor.preview, Qt.LeftButton)
                viewer.assert_called_once()
            old = {self.root / row['路径'] for row in editor.model.rows}
            editor.start_pdf_import(source)
            editor.confirm_import()
            self.assertFalse(any(path.exists() for path in old))
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                editor.delete_all()
            self.assertEqual([], editor.model.rows)
        self.assertEqual(source_before, source.read_bytes())

    def test_tab_switch_guards_unsaved_and_pending_pdf(self):
        award = ReportManagePage(self.awards, settings_service=self.preferences,
                                attachment_service=self.award_publisher, notify=lambda _: None)
        finance = ReportManagePage(self.finance, settings_service=self.preferences,
                                  attachment_service=self.finance_publisher, notify=lambda _: None)
        page = self.show(AwardFinanceManagePage(award, finance))
        award.set_mode('edit')
        award.inputs['获奖名称'].setText('未保存')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            page.tabs.setCurrentIndex(1)
        self.assertEqual(0, page.tabs.currentIndex())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            page.tabs.setCurrentIndex(1)
        self.assertEqual(1, page.tabs.currentIndex())
        self.assertEqual('view', award.mode)
        source = self.root / 'pending.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page(width=120, height=180)
            pdf.save(str(source))
        finance.attachments.start_pdf_import(source)
        temporary = finance.attachments.pages[0].path.parent
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            page.tabs.setCurrentIndex(0)
        self.assertEqual(1, page.tabs.currentIndex())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            page.tabs.setCurrentIndex(0)
        self.assertFalse(temporary.exists())

    def test_main_navigation_and_new_page_size_stability(self):
        from gui.main_window import build_main_window
        from services.people import PeopleService
        window = build_main_window(PeopleService(self.db), self.db, settings_service=self.preferences,
            award_service=self.awards, finance_service=self.finance,
            award_word_service=self.award_output, finance_word_service=self.finance_output,
            award_attachment_service=self.award_publisher, finance_attachment_service=self.finance_publisher)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        stack = window.findChild(QStackedWidget, 'workspace')
        geometry = window.geometry()
        for _ in range(20):
            for name, page in (('navAwardSearch', window.award_search_page), ('navFinanceSearch', window.finance_search_page),
                               ('navAwardFinanceManage', window.award_finance_manage_page), ('navPersonSearch', window.person_word_page)):
                window.findChild(QPushButton, name).click()
                self.app.processEvents()
                self.assertIs(page, stack.currentWidget())
                self.assertEqual(geometry, window.geometry())

    def test_award_editor_scrolls_inside_default_and_small_window(self):
        from gui.main_window import build_main_window
        from services.people import PeopleService
        window = build_main_window(PeopleService(self.db), self.db, settings_service=self.preferences,
            award_attachment_service=self.award_publisher, finance_attachment_service=self.finance_publisher)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        original = window.size()
        window.findChild(QPushButton, 'navAwardFinanceManage').click()
        self.app.processEvents()
        page = window.award_manage_page
        scroll = page.findChild(QScrollArea, 'awardDetailScroll')
        self.assertIsNotNone(scroll)
        self.assertEqual(original, window.size())
        # Long names and taller content must stay inside the existing viewport.
        page.project.addItem('很长的关联工程名称' * 80, 1)
        page.project.setCurrentIndex(page.project.count() - 1)
        page.error_label.setText('\n'.join(['用于验证内部滚动的多行说明'] * 45))
        self.app.processEvents()
        self.assertEqual(original, window.size())
        for size in (window.minimumSizeHint(), original * 1.2, original):
            window.resize(size)
            self.app.processEvents()
            content = scroll.widget()
            self.assertLessEqual(content.width(), scroll.viewport().width())
            self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            self.app.processEvents()
            bottom = page.error_label.mapTo(scroll.viewport(), page.error_label.rect().bottomLeft()).y()
            self.assertLess(bottom, scroll.viewport().height())
            self.assertGreaterEqual(bottom, 0)
            self.assertTrue(page.rect().contains(scroll.geometry()))
        window.showMaximized()
        self.app.processEvents()
        window.showNormal()
        self.app.processEvents()
        self.assertEqual(original, window.size())
        window.award_finance_manage_page.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertEqual(original, window.size())
        finance_scroll = window.finance_manage_page.findChild(QScrollArea)
        self.assertEqual(Qt.ScrollBarAsNeeded, finance_scroll.horizontalScrollBarPolicy())

    def test_gui_fallback_once_cancel_zero_write_session_retained(self):
        for service, publisher, output, record_id, _ in self.domains():
            publisher.save_pages((record_id,), self.pages[:1])
            self.preferences.save(PdfSettings())
            before = self.preferences.path.read_bytes()
            page = self.selection_page(service, output)
            page.selected_ids.add(record_id)
            page.insert_title.setChecked(True)
            self.word.missing = ['图片', '标题 4']
            self.word.calls.clear()
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.No) as prompt:
                page.insert_to_word()
                prompt.assert_called_once()
            self.assertEqual([], self.writes())
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes) as prompt:
                page.insert_to_word()
                prompt.assert_called_once()
            self.assertEqual(2, self.writes().count(('style', 'builtin-normal')))
            self.assertEqual({record_id}, page.selected_ids)
            self.assertTrue(page.insert_title.isChecked())
            self.assertEqual(before, self.preferences.path.read_bytes())
