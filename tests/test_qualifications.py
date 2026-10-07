"""Company qualification vertical workflow, isolated files and fake Word."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import hashlib
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QStackedWidget

from database.initializer import create_empty_database
from database.runtime import runtime_connection
from gui.qualification_manage import QualificationManagePage
from gui.qualification_search import QualificationSearchPage
from gui.settings_page import SettingsPage
from repositories.attachment_repository import QualificationAttachmentRepository
from services.attachments import QualificationAttachmentService
from services.pdf_import import RenderedPage
from services.qualifications import QualificationService
from services.qualification_word import QualificationWordOutputService, QualificationWordPreflightError, QualificationWordWriteError
from services.settings import PdfSettings, SettingsService
from services.word_service import WordNotRunningError, WordNoActiveDocumentError, WordOperationError
from tests.test_gui_word_repairs import StyleWord


class QualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='TenderSystem_qualifications_')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.db = self.root / 'v1.db'
        create_empty_database(self.db)
        with runtime_connection(self.db, write=True) as connection:
            connection.executemany('INSERT INTO 公司信息表(公司ID,公司名称) VALUES(?,?)', [(1, '甲公司'), (2, '乙公司')])
        self.service = QualificationService(self.db)
        self.a = self.service.save(None, {'公司ID': 1, '资质证书名称': '施工资质', '资质等级': '一级', '有效期': None})
        self.b = self.service.save(None, {'公司ID': 2, '资质证书名称': '安全许可证', '有效期': ''})
        self.publisher = QualificationAttachmentService(self.db, data_root=self.root)
        self.preferences = SettingsService(self.root / 'settings.json')
        self.word = StyleWord()
        self.output = QualificationWordOutputService(self.service.qualifications, data_root=self.root,
                                                      word_factory=lambda: self.word)
        image = QImage(80, 120, QImage.Format_RGB32)
        image.fill(QColor('blue'))
        picture = self.root / 'page.jpg'
        image.save(str(picture), 'JPEG')
        self.pages = tuple(RenderedPage(i, picture) for i in (1, 2, 3))

    def search_page(self):
        page = QualificationSearchPage(self.service, self.output, self.preferences, lambda _: None)
        self.addCleanup(page.close)
        page.resize(1200, 800)
        page.show()
        self.app.processEvents()
        return page

    def manage_page(self):
        page = QualificationManagePage(self.service, settings_service=self.preferences,
                                        attachment_service=self.publisher, notify=lambda _: None)
        self.addCleanup(page.close)
        page.resize(1100, 850)
        page.show()
        self.app.processEvents()
        return page

    def test_crud_company_fk_dates_null_and_empty(self):
        record = self.service.qualifications.get(self.a)
        self.assertIsNone(record['有效期'])
        self.assertEqual('', self.service.qualifications.get(self.b)['有效期'])
        changed = {**record, '公司ID': 2, '发证日期': '2024-01-01', '资质证书名称': '施工资质修改'}
        self.service.save(self.a, changed)
        self.assertEqual(2, self.service.qualifications.get(self.a)['公司ID'])
        for values in ({**changed, '公司ID': 999}, {**changed, '资质证书名称': '  '},
                       {**changed, '有效期': '2025-02-30'}, {**changed, '发证日期': '20250101'}):
            with self.subTest(values=values), self.assertRaises(Exception):
                self.service.save(self.a, values)
            self.assertEqual('施工资质修改', self.service.qualifications.get(self.a)['资质证书名称'])
        self.service.delete(self.a)
        self.assertIsNone(self.service.qualifications.get(self.a))

    def test_search_combined_expiry_and_sql_input(self):
        for kwargs, expected in (({'name': '施工'}, [self.a]), ({'grade': '一级'}, [self.a]),
                                 ({'company_id': 2}, [self.b]), ({'status': '长期有效'}, [self.a]),
                                 ({'name': '施工', 'company_id': 2}, []), ({'name': "' OR 1=1 --"}, []),
                                 ({'name': '%'}, [])):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(expected, [row['资质ID'] for row in self.service.search(**kwargs)])
        for offset, expected in ((-1, '已过期'), (29, '即将到期'), (30, '正常有效')):
            row = self.service.qualifications.get(self.a)
            self.service.save(self.a, {**row, '有效期': (date.today() + timedelta(days=offset)).isoformat()})
            self.assertEqual(expected, self.service.search(name='施工')[0]['有效期状态'])

    def test_numeric_pages_and_name_normalization(self):
        with runtime_connection(self.db, write=True) as connection:
            connection.executemany('INSERT INTO 公司资质图表(资质ID,路径,备注) VALUES(?,?,?)',
                [(self.a, f'Images/{i}.jpg', str(i)) for i in (10, 2, 1)])
            connection.execute('INSERT INTO 公司资质表(公司ID,资质证书名称) VALUES(1,?)', ('  施工资质  ',))
        self.assertEqual(['1', '2', '10'], [row['备注'] for row in self.service.qualifications.attachments(self.a)])
        self.assertEqual(['安全许可证', '施工资质'], self.service.qualifications.list_names())

    def test_import_replace_delete_uuid_text_pages(self):
        self.publisher.save_pages((self.a,), self.pages)
        records = self.service.qualifications.attachments(self.a)
        self.assertEqual(['1', '2', '3'], [row['备注'] for row in records])
        import uuid
        for row in records:
            self.assertEqual('Images', Path(row['路径']).parts[0])
            uuid.UUID(Path(row['路径']).stem)
            self.assertTrue((self.root / row['路径']).is_file())
        old = {self.root / row['路径'] for row in records}
        self.publisher.save_pages((self.a,), self.pages[:1], replace=True)
        self.assertFalse(any(path.exists() for path in old))
        self.publisher.delete_all((self.a,))
        self.assertEqual([], self.service.qualifications.attachments(self.a))
        self.assertEqual([], list((self.root / 'Images').iterdir()))

    def test_failed_replace_preserves_old_and_cleans_new(self):
        self.publisher.save_pages((self.a,), self.pages)
        rows = self.service.qualifications.attachments(self.a)
        paths = set((self.root / 'Images').iterdir())
        with patch.object(QualificationAttachmentRepository, 'replace_rows', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                self.publisher.save_pages((self.a,), self.pages[:1], replace=True)
        self.assertEqual(rows, self.service.qualifications.attachments(self.a))
        self.assertEqual(paths, set((self.root / 'Images').iterdir()))

    def test_shared_path_across_tables_is_not_deleted(self):
        self.publisher.save_pages((self.a,), self.pages[:1])
        old = self.service.qualifications.attachments(self.a)[0]['路径']
        with runtime_connection(self.db, write=True) as connection:
            connection.execute("INSERT INTO 人员表(人员ID,姓名) VALUES(1,'张三')")
            connection.execute("INSERT INTO 人员证书表(证书ID,人员ID,证书名称) VALUES(1,1,'证书')")
            connection.execute('INSERT INTO 人员证书图表(证书ID,路径,备注) VALUES(1,?,NULL)', (old,))
        self.publisher.delete_all((self.a,))
        self.assertTrue((self.root / old).is_file())

    def test_attachment_constraints_wrong_parent_and_import_mode(self):
        for group, pages in (((999,), self.pages), ((self.a,), (self.pages[1],))):
            with self.assertRaises((LookupError, ValueError)):
                self.publisher.save_pages(group, pages)
        self.publisher.save_pages((self.a,), self.pages)
        with self.assertRaisesRegex(ValueError, '替换'):
            self.publisher.save_pages((self.a,), self.pages)
        with self.assertRaisesRegex(ValueError, '附件'):
            self.service.delete(self.a)
        with self.assertRaises(Exception), runtime_connection(self.db, write=True) as connection:
            connection.execute('DELETE FROM 公司资质表 WHERE 资质ID=?', (self.a,))

    def test_gui_preview_pdf_cancel_rotation_confirm_replace(self):
        page = self.manage_page()
        index = next(i for i, row in enumerate(page.model.rows) if row['资质ID'] == self.a)
        page.qualifications_view.selectRow(index)
        source = self.root / 'source.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page(width=120, height=180)
            pdf.new_page(width=180, height=120)
            pdf.save(str(source))
        before = hashlib.sha256(self.db.read_bytes()).digest()
        source_before = source.read_bytes()
        editor = page.attachments
        editor.start_pdf_import(source)
        temporary = editor.pages[0].path.parent
        editor.show_page(1)
        editor.rotate(90)
        editor.cancel_import()
        self.assertFalse(temporary.exists())
        self.assertFalse((self.root / 'Images').exists())
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).digest())
        editor.start_pdf_import(source)
        editor.confirm_import()
        self.assertEqual(2, len(editor.model.rows))
        self.assertIsNotNone(editor.preview._pixmap)
        old = {self.root / row['路径'] for row in editor.model.rows}
        editor.start_pdf_import(source)
        editor.confirm_import()
        self.assertEqual(2, len(editor.model.rows))
        self.assertFalse(any(path.exists() for path in old))
        self.assertEqual(source_before, source.read_bytes())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            editor.delete_all()
        self.assertEqual([], editor.model.rows)

    def test_gui_crud_save_failure_cancel_and_delete_blocker(self):
        page = self.manage_page()
        page.new_qualification()
        page.company.setCurrentIndex(page.company.findData(1))
        page.inputs['资质证书名称'].setText('新资质')
        page.save_qualification()
        new_id = page.qualification_id
        self.assertIsNotNone(new_id)
        page.set_mode('edit')
        page.inputs['有效期'].setText('bad-date')
        page.save_qualification()
        self.assertIn('保存失败', page.error_label.text())
        self.assertEqual('bad-date', page.inputs['有效期'].text())
        self.assertIsNone(self.service.qualifications.get(new_id)['有效期'])
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            page.qualifications_view.selectRow(0)
        self.assertEqual(new_id, page.qualification_id)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            page.cancel()
        self.publisher.save_pages((new_id,), self.pages[:1])
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            page.delete_qualification()
        self.assertIn('关联附件', page.error_label.text())
        self.publisher.delete_all((new_id,))
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            page.delete_qualification()
        self.assertIsNone(self.service.qualifications.get(new_id))

    def test_search_mouse_check_copy_preview_and_state_is_read_only(self):
        self.publisher.save_pages((self.a,), self.pages[:1])
        before = hashlib.sha256(self.db.read_bytes()).digest()
        page = self.search_page()
        row = next(i for i, r in enumerate(page.model.rows) if r['资质ID'] == self.a)
        index = page.model.index(row, 1)
        QTest.mouseClick(page.qualifications_view.viewport(), Qt.LeftButton,
                         pos=page.qualifications_view.visualRect(index).center())
        self.assertIsNotNone(page.preview._pixmap)
        from gui.common import ImageViewer
        with patch.object(ImageViewer, 'exec', return_value=0) as viewer:
            QTest.mouseClick(page.preview, Qt.LeftButton)
            viewer.assert_called_once()
        point = page.qualifications_view.visualRect(page.model.index(row, 0)).center()
        QTest.mouseClick(page.qualifications_view.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual({self.a}, page.selected_ids)
        QTest.mouseDClick(page.qualifications_view.viewport(), Qt.LeftButton,
                          pos=page.qualifications_view.visualRect(index).center())
        self.assertEqual('施工资质', QGuiApplication.clipboard().text())
        QGuiApplication.clipboard().setText('unchanged')
        QTest.mouseDClick(page.qualifications_view.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual('unchanged', QGuiApplication.clipboard().text())
        page.selected_ids.add(self.a)
        page.name_input.setText('安全')
        page.search()
        self.assertEqual({self.a}, page.selected_ids)
        page.clear_search()
        self.assertEqual({self.a}, page.selected_ids)
        viewed_id, pixmap = page.current_qualification_id, page.preview._pixmap
        page.clear_selection()
        self.assertEqual(set(), page.selected_ids)
        self.assertEqual(viewed_id, page.current_qualification_id)
        self.assertIs(pixmap, page.preview._pixmap)
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).digest())

    def test_missing_images_preview_does_not_crash(self):
        with runtime_connection(self.db, write=True) as connection:
            connection.execute('INSERT INTO 公司资质图表(资质ID,路径) VALUES(?,?)', (self.a, 'Images/missing.jpg'))
        page = self.search_page()
        page.name_input.setText('施工')
        page.search()
        self.assertIn('图片文件尚未就位', page.preview.text())
        self.assertTrue(page.preview.large_view_enabled)

    def test_word_order_pages_structure_and_resize_options(self):
        self.publisher.save_pages((self.a,), self.pages)
        self.publisher.save_pages((self.b,), self.pages[:1])
        settings = PdfSettings(company_qualification_name_order=('施工资质', '安全许可证'), enlarge_small_images=True)
        plan = self.output.insert({self.b, self.a}, settings)
        self.assertEqual([self.a, self.b], [block.qualification_id for block in plan.blocks])
        writes = [call[0] for call in self.word.calls if call[0] not in ('document', 'selection')]
        self.assertEqual(['style', 'image', 'image', 'image', 'pagebreak', 'style', 'image', 'pagebreak'], writes)
        self.assertTrue(all(call[2]['enlarge_small'] for call in self.word.calls if call[0] == 'image'))
        self.assertFalse(any(call[0] in ('text', 'paragraph') for call in self.word.calls))

    def test_word_same_name_id_unknown_name_and_numeric_pages(self):
        second = self.service.save(None, {'公司ID': 1, '资质证书名称': '施工资质', '资质等级': '二级'})
        self.publisher.save_pages((self.b,), self.pages[:1])
        self.publisher.save_pages((second,), self.pages[:1])
        with runtime_connection(self.db, write=True) as connection:
            for number in (10, 2, 1):
                relative = f'Images/n-{number}.jpg'
                (self.root / relative).write_bytes(self.pages[0].path.read_bytes())
                connection.execute('INSERT INTO 公司资质图表(资质ID,路径,备注) VALUES(?,?,?)',
                                   (self.a, relative, str(number)))
        plan = self.output.build_plan({second, self.b, self.a},
                                      PdfSettings(company_qualification_name_order=('施工资质',)))
        self.assertEqual([self.a, second, self.b], [block.qualification_id for block in plan.blocks])
        self.assertEqual(['n-1.jpg', 'n-2.jpg', 'n-10.jpg'], [image.path.name for image in plan.blocks[0].images])

    def test_optional_names_plan_style_structure_and_fallback(self):
        self.publisher.save_pages((self.a,), self.pages[:1])
        self.publisher.save_pages((self.b,), self.pages[:1])
        settings = PdfSettings(company_qualification_name_order=('施工资质', '安全许可证'))
        selected = {self.a, self.b}
        plan = self.output.insert(selected, settings, insert_qualification_name=True)
        self.assertTrue(plan.insert_qualification_name)
        self.assertEqual([self.a, self.b], [block.qualification_id for block in plan.blocks])
        expected = []
        for block in plan.blocks:
            expected.extend([('style', '标题 4'), ('text', block.name), ('paragraph',),
                             ('style', '图片'), ('image',), ('pagebreak',)])
        writes = [call[:1] if call[0] == 'image' else call for call in self.word.calls
                  if call[0] not in ('document', 'selection')]
        self.assertEqual(expected, writes)
        self.word.calls.clear()
        self.word.missing = ['标题 4']
        prompts = []
        def confirm(details):
            prompts.append(details)
            return False
        with self.assertRaises(QualificationWordPreflightError):
            self.output.insert(selected, settings, insert_qualification_name=True, confirm_style_fallback=confirm)
        self.assertEqual([[('文本样式', '标题 4')]], prompts)
        self.assertFalse(any(c[0] in ('style', 'text', 'paragraph', 'image', 'pagebreak') for c in self.word.calls))
        self.word.calls.clear()
        self.output.insert(selected, settings, insert_qualification_name=True, confirm_style_fallback=lambda _: True)
        self.assertIn(('style', 'builtin-normal'), self.word.calls)
        self.assertIn(('style', '图片'), self.word.calls)
        self.word.calls.clear()
        self.output.insert(selected, settings, confirm_style_fallback=lambda _: self.fail('Text style is unused'))
        self.assertFalse(any(c[0] == 'text' for c in self.word.calls))

    def test_session_name_toggle_and_single_column_grade_edit(self):
        self.publisher.save_pages((self.a,), self.pages[:1])
        page = self.search_page()
        page.selected_ids.add(self.a)
        self.assertFalse(page.insert_name.isChecked())
        with patch.object(self.preferences, 'save') as save:
            page.insert_name.setChecked(True)
            page.search()
            page.hide()
            page.show()
            page.insert_to_word()
            save.assert_not_called()
        self.assertTrue(page.insert_name.isChecked())
        self.assertEqual({self.a}, page.selected_ids)
        self.assertIn(('text', '施工资质'), self.word.calls)
        fresh = self.search_page()
        self.assertFalse(fresh.insert_name.isChecked())
        manage = self.manage_page()
        self.assertEqual([('证书名称', '资质证书名称')], manage.model.columns)
        for i, row in enumerate(manage.model.rows):
            manage.qualifications_view.selectRow(i)
            self.assertEqual(row['资质ID'], manage.qualification_id)
            self.assertEqual(row['资质等级'] or '', manage.inputs['资质等级'].text())
        index = next(i for i, row in enumerate(manage.model.rows) if row['资质ID'] == self.a)
        manage.qualifications_view.selectRow(index)
        manage.set_mode('edit')
        manage.inputs['资质等级'].setText('二级')
        manage.save_qualification()
        self.assertEqual('二级', self.service.qualifications.get(self.a)['资质等级'])

    def test_word_missing_record_attachment_image_zero_writes(self):
        for ids in (set(), {999}, {self.a}):
            with self.subTest(ids=ids), self.assertRaises(QualificationWordPreflightError):
                self.output.insert(ids, PdfSettings())
            self.assertEqual([], self.word.calls)
        with runtime_connection(self.db, write=True) as connection:
            connection.execute('INSERT INTO 公司资质图表(资质ID,路径) VALUES(?,?)', (self.a, 'Images/missing.jpg'))
        with self.assertRaisesRegex(QualificationWordPreflightError, 'missing.jpg'):
            self.output.insert({self.a}, PdfSettings())
        self.assertEqual([], self.word.calls)

    def test_word_style_fallback_cancel_and_preferences_unchanged(self):
        self.publisher.save_pages((self.a,), self.pages[:1])
        self.preferences.save(PdfSettings())
        before = self.preferences.path.read_bytes()
        page = self.search_page()
        page.selected_ids.add(self.a)
        self.word.missing = ['图片']
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.No) as prompt:
            page.insert_to_word()
            prompt.assert_called_once()
        self.assertFalse(any(call[0] in ('style', 'image', 'pagebreak') for call in self.word.calls))
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            page.insert_to_word()
        self.assertIn(('style', 'builtin-normal'), self.word.calls)
        self.assertEqual(before, self.preferences.path.read_bytes())
        self.assertEqual({self.a}, page.selected_ids)

    def test_word_connection_and_partial_failure(self):
        self.publisher.save_pages((self.a,), self.pages[:1])
        for error in (WordNotRunningError(), WordNoActiveDocumentError()):
            self.output.word_factory = lambda error=error: (_ for _ in ()).throw(error)
            with self.assertRaises(type(error)):
                self.output.insert({self.a}, PdfSettings())
        self.output.word_factory = lambda: self.word
        self.word.fail_image = True
        with self.assertRaisesRegex(QualificationWordWriteError, '施工资质'):
            self.output.insert({self.a}, PdfSettings())
        self.assertFalse(any(call[0] == 'pagebreak' for call in self.word.calls))

    def test_settings_merge_drag_single_save_reset_and_legacy(self):
        self.preferences.save(PdfSettings(dpi=300, company_qualification_name_order=('已消失', '施工资质')))
        page = SettingsPage(self.preferences, lambda _: None,
                            qualification_names=self.service.qualifications.list_names)
        self.addCleanup(page.close)
        self.assertEqual(('已消失', '施工资质', '安全许可证'), page.qualification_order.values())
        with patch.object(self.preferences, 'save', wraps=self.preferences.save) as save:
            page.show_settings(self.preferences.load())
            save.assert_not_called()
            item = page.qualification_order.takeItem(2)
            page.qualification_order.insertItem(0, item)
            page.qualification_order.order_changed.emit()
            self.assertEqual(1, save.call_count)
        self.assertEqual(('安全许可证', '已消失', '施工资质'), self.preferences.load().company_qualification_name_order)
        self.assertEqual(300, self.preferences.load().dpi)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), \
             patch.object(self.preferences, 'save', wraps=self.preferences.save) as save:
            page.restore_defaults()
            self.assertEqual(1, save.call_count)
        self.assertEqual(('安全许可证', '施工资质'), self.preferences.load().company_qualification_name_order)
        self.preferences.path.write_text('{"dpi":150,"project_attachment_type_order":["合同"]}', encoding='utf-8')
        self.assertEqual((), self.preferences.load().company_qualification_name_order)
        self.assertEqual(150, self.preferences.load().dpi)
        self.assertEqual(('合同',), self.preferences.load().project_attachment_type_order)

    def test_main_navigation_and_unsaved_guard(self):
        from gui.main_window import build_main_window
        from services.people import PeopleService
        window = build_main_window(PeopleService(self.db), self.db,
            settings_service=self.preferences, qualification_service=self.service,
            qualification_word_service=self.output, qualification_attachment_service=self.publisher)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        stack = window.findChild(QStackedWidget, 'workspace')
        window.findChild(QPushButton, 'navQualSearch').click()
        self.assertIs(window.qualification_search_page, stack.currentWidget())
        window.findChild(QPushButton, 'navQualManage').click()
        page = window.qualification_manage_page
        self.assertIs(page, stack.currentWidget())
        page.set_mode('edit')
        page.inputs['资质证书名称'].setText('尚未保存')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            window.findChild(QPushButton, 'navQualSearch').click()
        self.assertIs(page, stack.currentWidget())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            window.findChild(QPushButton, 'navQualSearch').click()
        self.assertIs(window.qualification_search_page, stack.currentWidget())
