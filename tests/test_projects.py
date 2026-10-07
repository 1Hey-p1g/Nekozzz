"""Isolated engineering CRUD, attachment scope, search, GUI and fake Word tests."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import sqlite3
import tempfile
import unittest
from dataclasses import replace
import hashlib
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QStackedWidget

from database.initializer import create_empty_database
from database.runtime import runtime_connection
from repositories.attachment_repository import ProjectAttachmentRepository
from services.attachments import ProjectAttachmentService
from services.pdf_import import RenderedPage
from services.projects import ProjectService, amount_to_scaled, amount_text
from services.settings import PdfSettings, SettingsService
from services.project_word import ProjectWordJob, ProjectWordOutputService, ProjectWordPreflightError, ProjectWordWriteError
from services.word_service import WordNotRunningError, WordNoActiveDocumentError, WordOperationError
from tests.test_person_word import FakeWord


class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='TenderSystem_projects_')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.db = self.root / 'v1.db'
        create_empty_database(self.db)
        with runtime_connection(self.db, write=True) as connection:
            connection.executemany('INSERT INTO 人员表(人员ID,姓名) VALUES(?,?)', [(1, '张三'), (2, '李四'), (3, '张三')])
        self.service = ProjectService(self.db)
        self.publisher = ProjectAttachmentService(self.db, data_root=self.root)
        self.settings = SettingsService(self.root / 'settings.json')
        self.a = self.service.save(None, {'项目名称': 'A配网', '合同金额': '500.1234',
                                         '开工时间': '2024-01-01', '竣工时间': '2025-01-01'}, 1)
        self.b = self.service.save(None, {'项目名称': 'B工程', '合同金额': '1000',
                                         '开工时间': '2022-01-01', '竣工时间': '2026-01-01'}, 2)
        picture = QImage(16, 24, QImage.Format_RGB32)
        picture.fill(QColor('blue'))
        path = self.root / 'page.jpg'
        picture.save(str(path), 'JPEG')
        self.pages = (RenderedPage(1, path), RenderedPage(2, path))

    def test_crud_and_precise_amount(self):
        self.assertEqual(5001234, self.service.projects.get(self.a)['合同金额_scaled'])
        self.assertEqual('500.1234', amount_text(5001234))
        self.service.save(self.a, {'项目名称': '修改工程', '合同金额': '0'}, None)
        self.assertEqual(0, self.service.projects.get(self.a)['合同金额_scaled'])
        self.service.delete(self.a)
        self.assertIsNone(self.service.projects.get(self.a))
        for value in ('NaN', 'Infinity', '1.00001', '1e30', 1.25):
            with self.subTest(value=value), self.assertRaises(ValueError):
                amount_to_scaled(value)

    def test_leader_change_clear_preserves_other_role_and_rollback(self):
        with runtime_connection(self.db, write=True) as connection:
            connection.execute("INSERT INTO 人员业绩表(人员ID,业绩ID,担任角色) VALUES(1,?,'技术负责人')", (self.a,))
        values = {'项目名称': '修改', '合同金额': '12'}
        self.service.save(self.a, values, 2)
        self.assertEqual(2, self.service.projects.get(self.a)['负责人ID'])
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.save(self.a, {'项目名称': '不应保存'}, 999)
        self.assertEqual('修改', self.service.projects.get(self.a)['项目名称'])
        self.assertEqual(2, self.service.projects.get(self.a)['负责人ID'])
        self.service.save(self.a, values, None)
        with runtime_connection(self.db) as connection:
            self.assertEqual(['技术负责人'], [r[0] for r in connection.execute(
                'SELECT 担任角色 FROM 人员业绩表 WHERE 业绩ID=?', (self.a,))])
        with self.assertRaisesRegex(ValueError, '人员任职'):
            self.service.delete(self.a)

    def test_attachment_group_scope_replace_delete_shared_path(self):
        self.publisher.save_pages((self.a, '合同'), self.pages)
        self.publisher.save_pages((self.a, '竣工报告'), self.pages[:1])
        self.publisher.save_pages((self.b, '合同'), self.pages[:1])
        old = self.service.projects.attachments(self.a, '合同')[0]['路径']
        with runtime_connection(self.db, write=True) as connection:
            connection.execute('INSERT INTO 公司业绩图表(业绩ID,文件类型,路径,备注) VALUES(?,?,?,1)',
                               (self.b, '共享', old))
        self.publisher.save_pages((self.a, '合同'), self.pages[:1], replace=True)
        self.assertTrue((self.root / old).is_file())
        self.assertEqual(1, len(self.service.projects.attachments(self.a, '竣工报告')))
        self.assertEqual(1, len(self.service.projects.attachments(self.b, '合同')))
        self.publisher.delete_all((self.b, '共享'))
        self.assertFalse((self.root / old).exists())
        self.publisher.delete_all((self.a, '合同'))
        self.assertEqual([], self.service.projects.attachments(self.a, '合同'))

    def test_failed_replace_keeps_old_rows_files_and_cleans_new(self):
        self.publisher.save_pages((self.a, '合同'), self.pages)
        before = list((self.root / 'Images').iterdir())
        rows = self.service.projects.attachments(self.a, '合同')
        with patch.object(ProjectAttachmentRepository, 'replace_rows', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                self.publisher.save_pages((self.a, '合同'), self.pages[:1], replace=True)
        self.assertEqual(rows, self.service.projects.attachments(self.a, '合同'))
        self.assertEqual(set(before), set((self.root / 'Images').iterdir()))

    def test_numeric_pages_and_foreign_key(self):
        with runtime_connection(self.db, write=True) as connection:
            connection.executemany('INSERT INTO 公司业绩图表(业绩ID,文件类型,路径,备注) VALUES(?,?,?,?)',
                                   [(self.a, '合同', f'Images/{n}.jpg', n) for n in (10, 2, 1)])
        self.assertEqual([1, 2, 10], [r['备注'] for r in self.service.projects.attachments(self.a, '合同')])
        with self.assertRaisesRegex(ValueError, '附件'):
            self.service.delete(self.a)
        with self.assertRaises(sqlite3.IntegrityError), runtime_connection(self.db, write=True) as connection:
            connection.execute('DELETE FROM 公司业绩表 WHERE 业绩ID=?', (self.a,))

    def test_manage_gui_fields_and_pdf_cancel(self):
        from gui.project_manage import ProjectManagePage
        import pymupdf
        page = ProjectManagePage(self.service, settings_service=self.settings,
                                 attachment_service=self.publisher, notify=lambda _: None)
        self.addCleanup(page.close)
        page.resize(1100, 850)
        page.show()
        self.app.processEvents()
        self.assertEqual(9, len(page.inputs))
        page.file_type.setCurrentText(' 新类型 ')
        self.assertEqual((self.a, '新类型'), page.attachments.group)
        source = self.root / 'sample.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page()
            pdf.new_page()
            pdf.save(str(source))
        page.attachments.start_pdf_import(source)
        temporary = page.attachments.pages[0].path.parent
        page.attachments.rotate(90)
        page.attachments.show_page(1)
        page.attachments.cancel_import()
        self.assertFalse(temporary.exists())
        self.assertFalse((self.root / 'Images').exists())
        self.assertEqual([], self.service.projects.attachments(self.a, '新类型'))
        page.attachments.start_pdf_import(source)
        page.attachments.confirm_import()
        self.assertEqual(2, len(self.service.projects.attachments(self.a, '新类型')))

    def test_all_search_conditions_and_combined_and(self):
        with runtime_connection(self.db, write=True) as connection:
            connection.execute("INSERT INTO 人员业绩表(人员ID,业绩ID,担任角色) VALUES(1,?,'技术负责人')", (self.b,))
        for kwargs, expected in (
            ({'name': '配网'}, [self.a]), ({'minimum_amount': '600'}, [self.b]),
            ({'completed_before': '2025-12-31'}, [self.a]),
            ({'started_after': '2023-01-01'}, [self.a]), ({'leader': '张'}, [self.a]),
            ({'minimum_amount': '500', 'completed_before': '2025-12-31',
              'started_after': '2023-01-01', 'leader': '张'}, [self.a]),
            ({'minimum_amount': '600', 'leader': '张'}, []), ({'name': "' OR 1=1 --"}, []),
        ):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(expected, [row['业绩ID'] for row in self.service.search(**kwargs)])
        self.assertEqual(2, len(self.service.search()))
        for kwargs in ({'minimum_amount': 'bad'}, {'started_after': '2025-02-30'}):
            with self.assertRaises(ValueError):
                self.service.search(**kwargs)

    def output_fixture(self):
        self.publisher.save_pages((self.a, '合同'), self.pages)
        self.publisher.save_pages((self.a, '竣工报告'), self.pages[:1])
        self.publisher.save_pages((self.b, '合同'), self.pages[:1])
        word = FakeWord()
        output = ProjectWordOutputService(self.service.projects, data_root=self.root, word_factory=lambda: word)
        job = ProjectWordJob()
        job.add(self.a)
        job.add(self.b)
        job.item(self.a).selected_attachment_types.update(('竣工报告', '合同'))
        job.item(self.b).selected_attachment_types.add('合同')
        settings = PdfSettings(project_attachment_type_order=('合同', '竣工报告'))
        return word, output, job, settings

    def test_job_state_and_project_order(self):
        word, output, job, settings = self.output_fixture()
        self.assertFalse(job.add(self.a))
        third = self.service.save(None, {'项目名称': 'C工程'}, None)
        self.publisher.save_pages((third, '合同'), self.pages[:1])
        job.add(third)
        job.item(third).selected_attachment_types.add('合同')
        job.reorder([third, self.a, self.b])
        plan = output.build_plan(job, settings)
        self.assertEqual([third, self.a, self.b], [block.project_id for block in plan.blocks])
        self.assertEqual(['合同', '合同', '竣工报告'], [image.file_type for image in plan.blocks[1].images])
        job.remove(self.a)
        self.assertEqual({'合同'}, job.item(self.b).selected_attachment_types)
        self.assertEqual([], word.calls)

    def test_plan_numeric_pages_unknown_types(self):
        word, output, job, settings = self.output_fixture()
        for number in (10, 2, 1):
            (self.root / 'Images' / f'n-{number}.jpg').write_bytes(self.pages[0].path.read_bytes())
        with runtime_connection(self.db, write=True) as connection:
            connection.execute('DELETE FROM 公司业绩图表 WHERE 业绩ID=? AND 文件类型=?', (self.a, '合同'))
            connection.executemany('INSERT INTO 公司业绩图表(业绩ID,文件类型,路径,备注) VALUES(?,?,?,?)',
                [(self.a, '合同', f'Images/n-{n}.jpg', n) for n in (10, 2, 1)])
        # Repository verifies 1,2,10 independently; plan retains precisely that order.
        plan = output.build_plan(job, replace(settings, project_attachment_type_order=('竣工报告',)))
        self.assertEqual(['竣工报告', '合同', '合同', '合同'], [i.file_type for i in plan.blocks[0].images])
        self.assertEqual(['n-1.jpg', 'n-2.jpg', 'n-10.jpg'], [i.path.name for i in plan.blocks[0].images[1:]])
        self.assertEqual([1, 2, 10], [r['备注'] for r in self.service.projects.attachments(self.a, '合同')])

    def test_word_call_order_both_name_modes_and_repeat(self):
        word, output, job, settings = self.output_fixture()
        for names in (False, True):
            job.insert_project_name = names
            word.calls.clear()
            plan = output.insert(job, settings)
            expected = []
            for block in plan.blocks:
                if names:
                    expected += [('style', '标题 4'), ('text', block.project_name), ('paragraph',)]
                expected += [('style', '图片')]
                expected += [('image', image.path.name) for image in block.images]
                expected += [('pagebreak',)]
            actual = [call[:2] for call in word.calls if call[0] not in ('document', 'selection', 'styles')]
            self.assertEqual(expected, actual)
        self.assertEqual(2, len(job.projects))
        self.assertEqual({'竣工报告', '合同'}, job.item(self.a).selected_attachment_types)

    def test_preflight_all_failure_cases_write_nothing(self):
        word, output, job, settings = self.output_fixture()
        cases = []
        empty = ProjectWordJob()
        cases.append(empty)
        zero = ProjectWordJob()
        zero.add(self.a)
        cases.append(zero)
        missing_type = ProjectWordJob()
        missing_type.add(self.a)
        missing_type.item(self.a).selected_attachment_types.add('不存在')
        cases.append(missing_type)
        missing_project = ProjectWordJob()
        missing_project.add(999)
        cases.append(missing_project)
        for invalid_job in cases:
            with self.assertRaises(ProjectWordPreflightError):
                output.insert(invalid_job, settings)
            self.assertEqual([], word.calls)
        (self.root / self.service.projects.attachments(self.a, '合同')[0]['路径']).unlink()
        with self.assertRaisesRegex(ProjectWordPreflightError, 'A配网 / 合同'):
            output.insert(job, settings)
        self.assertEqual([], word.calls)

    def test_style_and_connection_preflight_and_partial_failure(self):
        word, output, job, settings = self.output_fixture()
        for style in ('图片', '标题 4'):
            word.calls.clear()
            word.missing = [style]
            job.insert_project_name = True
            with self.assertRaises(ProjectWordPreflightError):
                output.insert(job, settings)
            self.assertFalse(any(call[0] in ('style', 'text', 'paragraph', 'image', 'pagebreak') for call in word.calls))
        word.missing = []
        for error in (WordNotRunningError(), WordNoActiveDocumentError()):
            output.word_factory = lambda e=error: (_ for _ in ()).throw(e)
            with self.assertRaises(type(error)):
                output.insert(job, settings)
        output.word_factory = lambda: word
        word.calls.clear()
        word.fail_image = True
        with self.assertRaisesRegex(ProjectWordWriteError, 'A配网 / 合同'):
            output.insert(job, settings)
        self.assertFalse(any(call[0] == 'pagebreak' for call in word.calls))

    def show_search(self):
        from gui.project_search import ProjectSearchPage
        from gui.copy_toast import CopyToast
        output = ProjectWordOutputService(self.service.projects, data_root=self.root,
                                          word_factory=lambda: FakeWord())
        page = ProjectSearchPage(self.service, output, self.settings, lambda _: None,
                                  copy_to_clipboard=QGuiApplication.clipboard().setText)
        self.addCleanup(page.close)
        page.resize(1250, 1000)
        page.show()
        self.app.processEvents()
        return page

    def double_add(self, page, index):
        point = page.projects_view.visualRect(page.project_model.index(index, 0)).center()
        QTest.mouseClick(page.projects_view.viewport(), Qt.LeftButton, pos=point)
        QTest.mouseDClick(page.projects_view.viewport(), Qt.LeftButton, pos=point)
        self.app.processEvents()

    def test_gui_task_preview_copy_checkbox_and_geometry(self):
        self.publisher.save_pages((self.a, '合同'), self.pages)
        self.publisher.save_pages((self.a, '竣工报告'), self.pages[:1])
        self.publisher.save_pages((self.b, '竣工报告'), self.pages[:1])
        before = hashlib.sha256(self.db.read_bytes()).digest()
        page = self.show_search()
        self.assertEqual(1, page.project_model.columnCount())
        self.double_add(page, 0)
        self.double_add(page, 1)
        self.double_add(page, 0)
        self.assertEqual([self.a, self.b], page.task_list.person_ids())
        self.assertEqual(self.a, page.current_id())
        self.assertFalse(page.preview.pixmap().isNull())
        self.assertLess(page.info_view.geometry().bottom(), page.right.layout().itemAt(2).widget().geometry().top())
        cell = page.types_view.visualRect(page.type_model.index(0, 0)).center()
        QTest.mouseClick(page.types_view.viewport(), Qt.LeftButton, pos=cell)
        self.assertEqual({'合同'}, page.job.item(self.a).selected_attachment_types)
        other_checkbox = page.types_view.visualRect(page.type_model.index(1, 0)).center()
        QTest.mouseClick(page.types_view.viewport(), Qt.LeftButton, pos=other_checkbox)
        self.assertEqual({'合同', '竣工报告'}, page.job.item(self.a).selected_attachment_types)
        self.assertEqual('合同', page.type_model.active_id)
        other_text = page.types_view.visualRect(page.type_model.index(1, 1)).center()
        QTest.mouseClick(page.types_view.viewport(), Qt.LeftButton, pos=other_text)
        self.assertEqual('竣工报告', page.type_model.active_id)
        self.assertNotIn('项目负责人', [row['字段'] for row in page.info_model.rows])
        page.personnel_view.scrollTo(page.personnel_model.index(0, 1))
        self.app.processEvents()
        point = page.personnel_view.visualRect(page.personnel_model.index(0, 1)).center()
        QTest.mouseDClick(page.personnel_view.viewport(), Qt.LeftButton, pos=point)
        self.assertEqual('张三', QGuiApplication.clipboard().text())
        page.task_list.setCurrentRow(1)
        self.assertEqual(set(), page.job.item(self.b).selected_attachment_types)
        widget = page.task_list.itemWidget(page.task_list.item(0))
        self.assertLessEqual(widget.sizeHint().height(), page.task_list.item(0).sizeHint().height())
        task_name = next(label for label in widget.findChildren(QLabel) if 'A配网' in label.text())
        self.assertGreater(task_name.width(), task_name.fontMetrics().horizontalAdvance(task_name.text()))
        widget.findChild(QPushButton, 'removeProjectFromWord').click()
        self.assertEqual([self.b], page.task_list.person_ids())
        self.assertEqual(self.b, page.current_id())
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).digest())

    def test_long_text_summary_and_missing_preview(self):
        long = '工程内容完整说明。' * 150
        self.service.save(self.a, {'项目名称': 'A配网', '项目主要内容': long}, None)
        with runtime_connection(self.db, write=True) as connection:
            connection.execute('INSERT INTO 公司业绩图表(业绩ID,文件类型,路径,备注) VALUES(?,?,?,1)',
                               (self.a, '合同', 'Images/missing.jpg'))
        page = self.show_search()
        self.double_add(page, 0)
        self.assertIn('图片文件尚未就位', page.preview.text())
        self.assertEqual('—', page.info_model.rows[-1]['值'])
        row = next(i for i, r in enumerate(page.info_model.rows) if r['字段'] == '项目主要内容')
        self.assertEqual(long, page.info_model.rows[row]['原值'])
        self.assertGreater(page.info_view.rowHeight(row), page.info_view.verticalHeader().defaultSectionSize())
        self.assertLessEqual(page.info_view.height(), int(page.right.height() * .45) + 1)
        self.assertGreater(page.info_view.verticalScrollBar().maximum(), 0)

    def test_project_settings_merge_drag_save_reset_compatibility(self):
        from gui.settings_page import SettingsPage
        self.settings.save(PdfSettings(dpi=300, project_attachment_type_order=('A', 'B', 'C')))
        saved = []
        original_save = self.settings.save
        def record_save(value):
            saved.append(value)
            original_save(value)
        self.settings.save = record_save
        page = SettingsPage(self.settings, lambda _: None, lambda: ('人员类型',), lambda: ('A', 'D', 'E'))
        self.addCleanup(page.close)
        self.assertEqual(('A', 'B', 'C', 'D', 'E'), page.project_order.values())
        self.assertEqual([], saved)
        moved = page.project_order.takeItem(4)
        page.project_order.insertItem(0, moved)
        page.project_order.order_changed.emit()
        self.assertEqual(1, len(saved))
        self.assertEqual(('E', 'A', 'B', 'C', 'D'), self.settings.load().project_attachment_type_order)
        self.assertEqual(300, self.settings.load().dpi)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            page.restore_defaults()
        self.assertEqual(2, len(saved))
        self.assertEqual(('A', 'D', 'E'), self.settings.load().project_attachment_type_order)
        self.settings.path.write_text('{"dpi":150,"person_name_style":"人员标题"}', encoding='utf-8')
        self.assertEqual((), self.settings.load().project_attachment_type_order)
        self.assertEqual('人员标题', self.settings.load().person_name_style)

    def test_main_window_navigation_and_search_errors(self):
        from gui.main_window import build_main_window
        from services.people import PeopleService
        window = build_main_window(PeopleService(self.db), self.db, settings_service=self.settings,
                                    project_service=self.service, project_attachment_service=self.publisher,
                                    project_word_service=ProjectWordOutputService(self.service.projects,
                                        data_root=self.root, word_factory=lambda: FakeWord()))
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        window.findChild(QPushButton, 'navProjectManage').click()
        self.assertIs(window.findChild(QStackedWidget, 'workspace').currentWidget(), window.project_manage_page)
        window.findChild(QPushButton, 'navProjectSearch').click()
        page = window.project_search_page
        self.assertIs(window.findChild(QStackedWidget, 'workspace').currentWidget(), page)
        page.filters['minimum_amount'].setText('invalid')
        page.search()
        self.assertIn('搜索失败', page.error_label.text())
        page.clear_search()
        self.assertEqual(2, page.project_model.rowCount())

    def test_manage_gui_save_failure_unsaved_switch_and_delete(self):
        from gui.project_manage import ProjectManagePage
        page = ProjectManagePage(self.service, settings_service=self.settings,
                                 attachment_service=self.publisher, notify=lambda _: None)
        self.addCleanup(page.close)
        page.resize(1100, 850)
        page.show()
        self.app.processEvents()
        page.new_project()
        page.inputs['项目名称'].setText('新工程')
        page.inputs['合同金额_scaled'].setText('123.4567')
        page.personnel.add_entry()
        _, _, role, person, _ = page.personnel.rows[0]
        role.setCurrentText('项目负责人')
        person.setCurrentIndex(person.findData(3))
        page.save_project()
        new_id = page.project_id
        self.assertEqual(3, self.service.projects.get(new_id)['负责人ID'])
        page.set_mode('edit')
        page.inputs['开工时间'].setText('2025-02-30')
        page.save_project()
        self.assertIn('保存失败', page.error_label.text())
        self.assertEqual('2025-02-30', page.inputs['开工时间'].text())
        self.assertIsNone(self.service.projects.get(new_id)['开工时间'])
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            page.projects_view.selectRow(0)
        self.assertEqual(new_id, page.project_id)
        self.assertEqual('2025-02-30', page.inputs['开工时间'].text())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            page.cancel()
        page.set_mode('edit')
        page.personnel.remove_entry(page.personnel.entries[0])
        page.save_project()
        self.assertIsNone(self.service.projects.get(new_id)['负责人ID'])
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            page.delete_project()
        self.assertIsNone(self.service.projects.get(new_id))

    def test_gui_reorder_preserves_independent_types_and_current_selection(self):
        self.publisher.save_pages((self.a, '合同'), self.pages)
        self.publisher.save_pages((self.b, '合同'), self.pages[:1])
        page = self.show_search()
        self.double_add(page, 0)
        self.double_add(page, 1)
        page.job.item(self.a).selected_attachment_types.add('合同')
        moved = page.task_list.takeItem(1)
        page.task_list.insertItem(0, moved)
        page.task_list.order_changed.emit()
        self.assertEqual([self.b, self.a], [item.project_id for item in page.job.projects])
        page.task_list.setCurrentRow(1)
        self.assertEqual({'合同'}, page.type_model.checked)
        page.task_list.setCurrentRow(0)
        self.assertEqual(set(), page.type_model.checked)
        self.assertTrue(all(page.task_list.itemWidget(page.task_list.item(i)) is not None
                            for i in range(page.task_list.count())))


if __name__ == '__main__':
    unittest.main()
