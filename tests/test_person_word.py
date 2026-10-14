"""Isolated V1 data and fake Word for multi-person task/output tests."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QColor, QGuiApplication, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QStackedWidget

from database.initializer import create_empty_database
from gui.main_window import build_main_window
from services.people import PeopleService
from services.person_word import (
    PersonWordJob, PersonWordOutputService, PersonWordPreflightError, PersonWordWriteError,
)
from services.settings import PdfSettings, SettingsService
from services.word_service import WordNoActiveDocumentError, WordNotRunningError, WordOperationError


class FakeWord:
    def __init__(self):
        self.calls = []
        self.missing = []
        self.fail_image = False

    def active_document(self):
        self.calls.append(("document",))
        return object()

    def selection(self):
        self.calls.append(("selection",))
        return object()

    def missing_styles(self, names):
        self.calls.append(("styles", tuple(names)))
        return self.missing

    def set_selection_style(self, name):
        self.calls.append(("style", name))

    def insert_text(self, text):
        self.calls.append(("text", text))

    def insert_paragraph(self):
        self.calls.append(("paragraph",))

    def insert_inline_image(self, path, **options):
        self.calls.append(("image", Path(path).name, options))
        if self.fail_image:
            raise WordOperationError("simulated failure")

    def insert_page_break(self):
        self.calls.append(("pagebreak",))


class PersonWordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="TenderSystem_person_word_")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.db = self.root / "v1.db"
        create_empty_database(self.db)
        images = self.root / "Images"
        images.mkdir()
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.executemany("INSERT INTO 人员表(人员ID,姓名) VALUES(?,?)",
                                       ((1, "张三"), (2, "李四"), (3, "王五")))
                connection.executemany(
                    "INSERT INTO 人员证书表(证书ID,人员ID,证书类型,证书名称,证书编号) "
                    "VALUES(?,?,?,?,?)",
                    ((9, 1, "职称证", "职称", "Z9"), (5, 1, "身份证", "身份证", "Z5"),
                     (12, 1, "注册证书", "注册乙", "Z12"), (8, 1, "注册证书", "注册甲", "Z8"),
                     (2, 2, "身份证", "身份证", "L2"), (3, 2, "职称证", "职称", "L3"),
                     (99, 3, "其他", "无附件", "W99")),
                )
                pages = []
                for cert_id, remarks in ((5, ("10", "2", "1")), (8, ("1",)), (12, ("1",)),
                                         (9, ("1",)), (2, ("1",)), (3, ("1",))):
                    for remark in remarks:
                        filename = f"{cert_id}-{remark}.jpg"
                        picture = QImage(12, 12, QImage.Format_RGB32)
                        picture.fill(QColor("#b8d0ea"))
                        picture.save(str(images / filename), "JPEG")
                        pages.append((cert_id, f"Images/{filename}", remark))
                connection.executemany("INSERT INTO 人员证书图表(证书ID,路径,备注) VALUES(?,?,?)", pages)
        self.people = PeopleService(self.db)
        self.word = FakeWord()
        self.settings = PdfSettings(person_certificate_type_order=("身份证", "注册证书", "职称证"))
        self.output = PersonWordOutputService(self.people, data_root=self.root,
                                              word_factory=lambda: self.word)

    def _show_multi_page(self):
        settings_service = SettingsService(self.root / "settings.json")
        window = build_main_window(self.people, self.db, settings_service=settings_service,
                                   person_word_service=self.output)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        self.assertIs(window.workspace.currentWidget(), window.person_word_page)
        self.assertEqual([], window.findChildren(QPushButton, "personModeButton"))
        return window, window.person_word_page

    def _double_click_person(self, page, row):
        point = page.people_view.visualRect(page.people_model.index(row, 0)).center()
        QTest.mouseClick(page.people_view.viewport(), Qt.LeftButton, pos=point)
        QTest.mouseDClick(page.people_view.viewport(), Qt.LeftButton, pos=point)

    def test_task_order_and_independent_certificate_selections(self):
        job = PersonWordJob()
        for person_id in (1, 2, 3):
            self.assertTrue(job.add(person_id))
        self.assertFalse(job.add(1))
        job.item(1).selected_certificate_ids.update((5, 8))
        job.item(2).selected_certificate_ids.add(2)
        job.reorder([3, 1, 2])
        self.assertEqual([3, 1, 2], [item.person_id for item in job.persons])
        self.assertEqual({5, 8}, job.item(1).selected_certificate_ids)
        self.assertEqual({2}, job.item(2).selected_certificate_ids)
        job.remove(1)
        self.assertIsNone(job.item(1))
        self.assertEqual({2}, job.item(2).selected_certificate_ids)

    def test_plan_uses_settings_type_then_id_and_repository_numeric_pages(self):
        job = PersonWordJob()
        job.add(1)
        job.item(1).selected_certificate_ids.update((9, 12, 5, 8))
        plan = self.output.build_plan(job, self.settings)
        self.assertEqual(["5-1.jpg", "5-2.jpg", "5-10.jpg", "8-1.jpg", "12-1.jpg", "9-1.jpg"],
                         [image.path.name for image in plan.blocks[0].images])

    def test_unconfigured_types_follow_configured_types_stably(self):
        job = PersonWordJob()
        job.add(1)
        job.item(1).selected_certificate_ids.update((9, 5, 8))
        plan = self.output.build_plan(job, PdfSettings(person_certificate_type_order=("身份证",)))
        self.assertEqual([5, 5, 5, 8, 9], [image.certificate_id for image in plan.blocks[0].images])

    def test_no_name_and_name_output_call_order_and_repeat(self):
        job = PersonWordJob()
        job.add(1)
        job.add(2)
        job.item(1).selected_certificate_ids.add(5)
        job.item(2).selected_certificate_ids.add(2)
        job.reorder([2, 1])
        plan = self.output.insert(job, self.settings)
        self.assertEqual([2, 1], [block.person_id for block in plan.blocks])
        writes = [call[:2] for call in self.word.calls if call[0] not in ("document", "selection", "styles")]
        self.assertEqual([
            ("style", "图片"), ("image", "2-1.jpg"), ("pagebreak",),
            ("style", "图片"), ("image", "5-1.jpg"), ("image", "5-2.jpg"),
            ("image", "5-10.jpg"), ("pagebreak",),
        ], writes)
        self.assertEqual({5}, job.item(1).selected_certificate_ids)
        self.word.calls.clear()
        job.insert_person_name = True
        self.output.insert(job, self.settings)
        writes = [call[:2] for call in self.word.calls if call[0] not in ("document", "selection", "styles")]
        self.assertEqual([
            ("style", "标题 4"), ("text", "李四"), ("paragraph",),
            ("style", "图片"), ("image", "2-1.jpg"), ("pagebreak",),
            ("style", "标题 4"), ("text", "张三"), ("paragraph",),
            ("style", "图片"), ("image", "5-1.jpg"), ("image", "5-2.jpg"),
            ("image", "5-10.jpg"), ("pagebreak",),
        ], writes)
        self.assertEqual(("styles", ("标题 4", "图片")),
                         next(call for call in self.word.calls if call[0] == "styles"))
        self.assertEqual(4, plan.image_count)

    def test_missing_selection_or_attachment_or_file_never_writes_word(self):
        job = PersonWordJob()
        with self.assertRaisesRegex(PersonWordPreflightError, "至少一名"):
            self.output.insert(job, self.settings)
        self.assertEqual([], self.word.calls)
        job.add(1)
        job.add(2)
        job.item(1).selected_certificate_ids.add(5)
        with self.assertRaisesRegex(PersonWordPreflightError, "李四.*尚未选择"):
            self.output.insert(job, self.settings)
        self.assertEqual([], self.word.calls)
        job.item(2).selected_certificate_ids.add(2)
        (self.root / "Images" / "2-1.jpg").unlink()
        with self.assertRaisesRegex(PersonWordPreflightError, "图片不存在"):
            self.output.insert(job, self.settings)
        self.assertEqual([], self.word.calls)
        job.remove(2)
        job.add(3)
        job.item(3).selected_certificate_ids.add(99)
        with self.assertRaisesRegex(PersonWordPreflightError, "没有附件"):
            self.output.insert(job, self.settings)
        self.assertEqual([], self.word.calls)

    def test_stale_certificate_and_style_preflight(self):
        job = PersonWordJob()
        job.add(1)
        job.item(1).selected_certificate_ids.add(2000)
        with self.assertRaisesRegex(PersonWordPreflightError, "已不存在"):
            self.output.insert(job, self.settings)
        self.assertEqual([], self.word.calls)
        job.item(1).selected_certificate_ids = {5}
        self.word.missing = ["图片"]
        with self.assertRaisesRegex(PersonWordPreflightError, "图片"):
            self.output.insert(job, self.settings)
        self.assertFalse(any(call[0] in ("style", "text", "image", "pagebreak")
                             for call in self.word.calls))
        self.word.calls.clear()
        self.word.missing = ["标题 4"]
        job.insert_person_name = True
        with self.assertRaisesRegex(PersonWordPreflightError, "标题 4"):
            self.output.insert(job, self.settings)
        self.assertFalse(any(call[0] in ("style", "text", "image", "pagebreak")
                             for call in self.word.calls))

    def test_attachment_read_error_is_preflight_failure(self):
        job = PersonWordJob()
        job.add(1)
        job.item(1).selected_certificate_ids.add(5)
        with patch.object(self.people.certificates, "attachments", side_effect=sqlite3.DatabaseError("read failed")):
            with self.assertRaisesRegex(PersonWordPreflightError, "读取附件失败"):
                self.output.insert(job, self.settings)
        self.assertEqual([], self.word.calls)

    def test_word_connection_errors_and_partial_write_context(self):
        job = PersonWordJob()
        job.add(1)
        job.item(1).selected_certificate_ids.add(5)
        for exception in (WordNotRunningError("not running"), WordNoActiveDocumentError("no document")):
            self.output.word_factory = lambda error=exception: (_ for _ in ()).throw(error)
            with self.assertRaises(type(exception)):
                self.output.insert(job, self.settings)
        self.output.word_factory = lambda: self.word
        self.word.fail_image = True
        with self.assertRaisesRegex(PersonWordWriteError, "张三 / 身份证"):
            self.output.insert(job, self.settings)
        self.assertFalse(any(call[0] == "pagebreak" for call in self.word.calls))

    def test_gui_mode_task_checkbox_and_error_messages(self):
        settings_service = SettingsService(self.root / "settings.json")
        window = build_main_window(self.people, self.db, settings_service=settings_service,
                                   person_word_service=self.output)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        stack = window.findChild(QStackedWidget, "workspace")
        self.assertIs(stack.currentWidget(), window.person_word_page)
        self.assertIs(window.workspace.currentWidget(), window.person_word_page)
        self.assertEqual([], window.findChildren(QPushButton, "personModeButton"))
        page = window.person_word_page
        self.assertIs(stack.currentWidget(), page)
        first = page.people_view.visualRect(page.people_model.index(0, 0)).center()
        QTest.mouseClick(page.people_view.viewport(), Qt.LeftButton, pos=first)
        QTest.mouseDClick(page.people_view.viewport(), Qt.LeftButton, pos=first)
        self.assertEqual([1], page.task_list.person_ids())
        page.people_view.selectRow(1)
        second = page.people_view.visualRect(page.people_model.index(1, 0)).center()
        QTest.mouseClick(page.people_view.viewport(), Qt.LeftButton, pos=second)
        QTest.mouseDClick(page.people_view.viewport(), Qt.LeftButton, pos=second)
        self.assertEqual([1, 2], page.task_list.person_ids())
        page.task_list.setCurrentRow(0)
        rect = page.certificates_view.visualRect(page.certificate_model.index(0, 0))
        QTest.mouseClick(page.certificates_view.viewport(), Qt.LeftButton, pos=rect.center())
        self.assertEqual(1, len(page.job.item(1).selected_certificate_ids))
        text_cell = page.certificates_view.visualRect(page.certificate_model.index(1, 2))
        QTest.mouseClick(page.certificates_view.viewport(), Qt.LeftButton, pos=text_cell.center())
        self.assertEqual(1, len(page.job.item(1).selected_certificate_ids))
        self.assertEqual(page.certificate_model.rows[1]["证书ID"], page.certificate_model.active_id)
        page.task_list.setCurrentRow(1)
        self.assertEqual(set(), page.job.item(2).selected_certificate_ids)
        page.task_list.setCurrentRow(0)
        self.assertEqual(1, len(page.job.item(1).selected_certificate_ids))
        moved = page.task_list.takeItem(1)
        page.task_list.insertItem(0, moved)
        page.task_list.order_changed.emit()
        self.assertEqual([2, 1], [item.person_id for item in page.job.persons])
        self.assertTrue(all(page.task_list.itemWidget(page.task_list.item(i)) is not None
                            for i in range(page.task_list.count())))
        page.insert_to_word()
        self.assertIn("李四", page.error_label.text())
        self.assertEqual([], self.word.calls)
        page.task_list.setCurrentRow(0)
        rect = page.certificates_view.visualRect(page.certificate_model.index(0, 0))
        QTest.mouseClick(page.certificates_view.viewport(), Qt.LeftButton, pos=rect.center())
        self.output.word_factory = lambda: (_ for _ in ()).throw(WordNotRunningError())
        page.insert_to_word()
        self.assertIn("未检测到正在运行", page.error_label.text())
        self.output.word_factory = lambda: (_ for _ in ()).throw(WordNoActiveDocumentError())
        page.insert_to_word()
        self.assertIn("没有活动文档", page.error_label.text())
        page.insert_name.setChecked(True)
        window.findChild(QPushButton, "navSettings").click()
        window.findChild(QPushButton, "navPersonSearch").click()
        self.assertIs(stack.currentWidget(), page)
        self.assertEqual(1, len(page.job.item(1).selected_certificate_ids))
        self.assertTrue(page.insert_name.isChecked())
        self.assertNotIn("search_page", window.created_pages)

    def test_double_click_duplicate_and_row_delete_selects_neighbor(self):
        window, page = self._show_multi_page()
        self.assertEqual(1, page.people_model.columnCount())
        self.assertFalse(hasattr(page, "add_button"))
        self.assertFalse(hasattr(page, "remove_button"))
        first = page.people_view.visualRect(page.people_model.index(0, 0)).center()
        QTest.mouseClick(page.people_view.viewport(), Qt.LeftButton, pos=first)
        self.assertEqual([], page.task_list.person_ids())
        self._double_click_person(page, 0)
        self._double_click_person(page, 1)
        self._double_click_person(page, 2)
        self.assertEqual([1, 2, 3], page.task_list.person_ids())
        page.job.item(1).selected_certificate_ids.add(5)
        page.job.item(3).selected_certificate_ids.add(99)
        self._double_click_person(page, 1)
        self.assertEqual([1, 2, 3], page.task_list.person_ids())
        self.assertEqual(2, page.task_list.currentItem().data(Qt.UserRole))
        self.assertEqual("该人员已在本次输出列表中", window.copy_toast.text())
        row_widget = page.task_list.itemWidget(page.task_list.item(1))
        remove = row_widget.findChild(QPushButton, "removePersonFromWord")
        self.assertEqual("移除此人员", remove.toolTip())
        remove.click()
        self.assertEqual([1, 3], page.task_list.person_ids())
        self.assertEqual(3, page.task_list.currentItem().data(Qt.UserRole))
        self.assertEqual({5}, page.job.item(1).selected_certificate_ids)
        self.assertEqual({99}, page.job.item(3).selected_certificate_ids)
        self.assertIsNone(page.job.item(2))
        self.assertTrue(all(page.task_list.itemWidget(page.task_list.item(i)) is not None
                            for i in range(page.task_list.count())))
        page.task_list.itemWidget(page.task_list.item(1)).findChild(
            QPushButton, "removePersonFromWord").click()
        self.assertEqual([1], page.task_list.person_ids())
        self.assertEqual(1, page.task_list.currentItem().data(Qt.UserRole))
        page.task_list.itemWidget(page.task_list.item(0)).findChild(
            QPushButton, "removePersonFromWord").click()
        self.assertEqual([], page.task_list.person_ids())
        self.assertIn("李四", page.person_info.text())
        self.assertEqual(2, page.viewed_person_id)
        self.assertFalse(page.certificate_model.checks_enabled)

    def test_delete_button_removes_its_row_without_selecting_it_first(self):
        _, page = self._show_multi_page()
        for row in range(3):
            self._double_click_person(page, row)
        page.task_list.setCurrentRow(0)
        page.task_list.itemWidget(page.task_list.item(1)).findChild(
            QPushButton, "removePersonFromWord").click()
        self.assertEqual([1, 3], page.task_list.person_ids())
        self.assertEqual(1, page.task_list.currentItem().data(Qt.UserRole))

    def test_task_row_geometry_and_remove_glyph(self):
        _, page = self._show_multi_page()
        self._double_click_person(page, 0)
        item = page.task_list.item(0)
        row_widget = page.task_list.itemWidget(item)
        remove = row_widget.findChild(QPushButton, "removePersonFromWord")
        self.assertLessEqual(row_widget.sizeHint().height(), item.sizeHint().height())
        self.assertLessEqual(row_widget.sizeHint().height(), page.task_list.visualItemRect(item).height())
        self.assertEqual("×", remove.text())
        self.assertEqual("移除此人员", remove.toolTip())
        self.assertGreaterEqual(remove.width(), 24)
        self.assertGreaterEqual(remove.height(), 24)

    def test_summary_preview_numeric_order_missing_file_and_copy(self):
        window, page = self._show_multi_page()
        self._double_click_person(page, 0)
        self.assertIn(self.people.people.get(1)["姓名"], page.person_info.text())
        self.assertTrue(page.person_info.textInteractionFlags() & Qt.TextSelectableByMouse)
        first_id = page.certificate_model.rows[0]["证书ID"]
        self.assertEqual(first_id, page.certificate_model.active_id)
        self.assertEqual(first_id, page.attachment_model.rows[0]["证书ID"])
        self.assertFalse(page.preview.pixmap().isNull())
        cert_row = next(i for i, cert in enumerate(page.certificate_model.rows) if cert["证书ID"] == 5)
        cell = page.certificates_view.visualRect(page.certificate_model.index(cert_row, 2)).center()
        QTest.mouseClick(page.certificates_view.viewport(), Qt.LeftButton, pos=cell)
        self.assertEqual(5, page.certificate_model.active_id)
        self.assertEqual(sorted(row['ID'] for row in page.attachment_model.rows),
                         [row['ID'] for row in page.attachment_model.rows])
        self.assertEqual(["1", "2", "10"], [row['备注'] for row in self.people.certificates.attachments(5)])
        self.assertEqual(set(), page.job.item(1).selected_certificate_ids)
        QGuiApplication.clipboard().setText("unchanged")
        for column, field in ((1, "证书类型"), (2, "证书名称"), (3, "证书编号")):
            point = page.certificates_view.visualRect(page.certificate_model.index(cert_row, column)).center()
            QTest.mouseClick(page.certificates_view.viewport(), Qt.LeftButton, pos=point)
            QTest.mouseDClick(page.certificates_view.viewport(), Qt.LeftButton, pos=point)
            self.assertEqual(str(page.certificate_model.rows[cert_row][field]),
                             QGuiApplication.clipboard().text())
            self.assertIn("已复制", window.copy_toast.text())
        QGuiApplication.clipboard().setText("unchanged")
        checkbox = page.certificates_view.visualRect(page.certificate_model.index(cert_row, 0)).center()
        QTest.mouseClick(page.certificates_view.viewport(), Qt.LeftButton, pos=checkbox)
        QTest.mouseDClick(page.certificates_view.viewport(), Qt.LeftButton, pos=checkbox)
        self.assertEqual("unchanged", QGuiApplication.clipboard().text())
        (self.root / "Images" / "5-2.jpg").unlink()
        page.attachments_view.selectRow(1)
        self.assertIn("图片文件尚未就位", page.preview.text())

    def test_certificate_table_five_row_height_and_wheel_scroll(self):
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.executemany(
                    "INSERT INTO 人员证书表(证书ID,人员ID,证书名称) VALUES(?,1,?)",
                    ((100 + i, f"额外证书{i}") for i in range(12)),
                )
        _, page = self._show_multi_page()
        self._double_click_person(page, 0)
        self.app.processEvents()
        view = page.certificates_view
        expected = (view.horizontalHeader().height() +
                    5 * view.verticalHeader().defaultSectionSize() + 2 * view.frameWidth())
        self.assertEqual(expected, view.height())
        self.assertGreater(view.verticalScrollBar().maximum(), 0)
        wheel = QWheelEvent(QPointF(30, 60), QPointF(30, 60), QPoint(0, 0), QPoint(0, -120),
                            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False)
        QApplication.sendEvent(view.viewport(), wheel)
        self.assertGreater(view.verticalScrollBar().value(), 0)


if __name__ == "__main__":
    unittest.main()
