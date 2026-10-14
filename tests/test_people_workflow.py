"""Isolated V1 person/certificate data and essential single-window interactions."""

import hashlib
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractItemView, QGroupBox, QMessageBox, QPushButton, QSplitter, QStackedWidget

from config.paths import DATABASE_FILE
from database.initializer import create_empty_database
from database.runtime import runtime_connection, validate_runtime_path
from gui.common import ImagePreview
from gui.main_window import build_main_window
from services.people import PeopleService, age_from_identity, expiry_status, work_years


class PeopleWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="TenderSystem_people_")
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "people.db"
        create_empty_database(self.database)
        self.service = PeopleService(self.database)
        self.anna = self.service.add_person({
            "姓名": "安娜", "身份证号": "A", "联系电话": "100", "学历": "本科",
            "毕业院校": "甲校", "专业": "工程", "进入系统日期": "2020-01-01",
        })
        self.bo = self.service.add_person({
            "姓名": "波波", "身份证号": None, "联系电话": "", "学历": None,
            "毕业院校": None, "专业": None, "进入系统日期": None,
        })
        self.cert_low = self.service.add_certificate({
            "人员ID": self.anna, "证书类型": "职称证", "证书名称": "工程师证",
            "证书编号": "A-1", "有效期": "2030-12-31",
        })
        self.cert_high = self.service.add_certificate({
            "人员ID": self.anna, "证书类型": "执业证", "证书名称": "注册证",
            "证书编号": "A-2", "有效期": None,
        })
        self.cert_bo = self.service.add_certificate({
            "人员ID": self.bo, "证书类型": "历史新类别", "证书名称": "工程师证",
            "证书编号": "B-1", "有效期": None,
        })
        with runtime_connection(self.database, write=True) as connection:
            connection.executemany(
                'INSERT INTO 人员证书图表 (证书ID,路径,备注) VALUES (?,?,?)',
                [(self.cert_high, f"Images/missing_{page}.png", str(page)) for page in range(1, 11)],
            )

    def test_search_associations_priority_and_numeric_pages(self):
        people = self.service.people.search("安")
        self.assertEqual([self.anna], [row["人员ID"] for row in people])
        self.assertEqual([self.bo], [row["人员ID"] for row in self.service.people.search("波", "工程师")])
        self.assertEqual([], self.service.people.search("安", "不存在"))
        for _ in range(3):
            self.assertEqual([self.cert_low, self.cert_high], [
                row["证书ID"] for row in self.service.certificates.for_person(self.anna)
            ])
            self.assertEqual([self.cert_bo], [row["证书ID"] for row in self.service.certificates.for_person(self.bo)])
        self.assertEqual(list(range(1, 11)), [int(row["备注"]) for row in self.service.certificates.attachments(self.cert_high)])

    def test_expiry_and_input_validation(self):
        today = date(2026, 9, 29)
        self.assertEqual("长期有效", expiry_status(None, today))
        self.assertEqual("未填写或无法判断", expiry_status("", today))
        self.assertEqual("未填写或无法判断", expiry_status("not-a-date", today))
        self.assertEqual("已过期", expiry_status((today - timedelta(days=1)).isoformat(), today))
        self.assertEqual("即将到期", expiry_status((today + timedelta(days=29)).isoformat(), today))
        self.assertEqual("正常有效", expiry_status((today + timedelta(days=30)).isoformat(), today))
        with self.assertRaises(ValueError):
            self.service.add_person({"姓名": "非法", "进入系统日期": "2026-02-30"})

    def test_age_and_tenure_use_valid_dates_without_persisting(self):
        today = date(2026, 9, 29)
        self.assertEqual(76, age_from_identity("11010519491231002X", today))
        self.assertEqual(76, age_from_identity("110105491231002", today))
        self.assertIsNone(age_from_identity("110105194912310021", today))
        self.assertIsNone(age_from_identity("11010520260230002X", today))
        self.assertIsNone(age_from_identity("A", today))
        self.assertEqual(6, work_years("2020-09-29", today))
        self.assertEqual(5, work_years("2020-09-30", today))
        self.assertIsNone(work_years("2026-09-30", today))
        self.assertIsNone(work_years("2020-02-30", today))

    def test_crud_restrict_and_failed_save_rollback(self):
        person = self.service.add_person({"姓名": "测试", "联系电话": ""})
        self.assertEqual("", self.service.people.get(person)["联系电话"])
        values = self.service.people.get(person)
        values["姓名"] = "测试修改"
        self.service.update_person(person, values)
        self.assertEqual("测试修改", self.service.people.get(person)["姓名"])
        cert = self.service.add_certificate({"人员ID": person, "证书名称": "测试证书", "证书类型": "自定义"})
        update = self.service.certificates.get(cert)
        update["证书编号"] = "N-2"
        self.service.update_certificate(cert, update)
        self.assertEqual("N-2", self.service.certificates.get(cert)["证书编号"])
        with self.assertRaisesRegex(ValueError, "证书 1 条"):
            self.service.delete_person(person)
        with self.assertRaisesRegex(ValueError, "附件 10 条"):
            self.service.delete_certificate(self.cert_high)
        with self.assertRaises(Exception):
            bad = {**values, "姓名": ""}
            self.service.update_person(person, bad)
        self.assertEqual("测试修改", self.service.people.get(person)["姓名"])
        self.service.delete_certificate(cert)
        self.service.delete_person(person)
        self.assertIsNone(self.service.people.get(person))

    def test_gui_navigation_read_only_selection_and_missing_preview(self):
        before = hashlib.sha256(self.database.read_bytes()).digest()
        window = build_main_window(self.service, self.database)
        self.addCleanup(window.close)
        stack = window.findChild(QStackedWidget, "workspace")
        page = window.person_word_page
        self.assertIs(stack.currentWidget(), page)
        self.assertNotIn('search_page', window.created_pages)
        page.name_filter.setText('安')
        page.search_people()
        page.add_person(page.people_model.index(0, 0))
        self.assertEqual(self.anna, page.viewed_person_id)
        self.assertEqual([self.cert_low, self.cert_high], [r['证书ID'] for r in page.certificate_model.rows])
        page.certificates_view.setCurrentIndex(page.certificate_model.index(1, 1))
        page.certificate_model.setData(page.certificate_model.index(1, 0), Qt.Checked, Qt.CheckStateRole)
        self.assertEqual({self.cert_high}, page.job.item(self.anna).selected_certificate_ids)
        self.assertIn('图片文件尚未就位', page.preview.text())
        page.name_filter.setText('波')
        page.search_people()
        page.add_person(page.people_model.index(0, 0))
        self.assertEqual(self.bo, page.viewed_person_id)
        self.assertEqual(self.cert_bo, page.certificate_model.rows[0]['证书ID'])
        window.findChild(QPushButton, 'navPersonManage').click()
        self.assertIs(stack.currentWidget(), window.manage_page)
        window.findChild(QPushButton, 'navPersonSearch').click()
        self.assertIs(stack.currentWidget(), page)
        self.assertEqual('波', page.name_filter.text())
        self.assertEqual({self.cert_high}, page.job.item(self.anna).selected_certificate_ids)
        self.assertEqual(before, hashlib.sha256(self.database.read_bytes()).digest())

    def _legacy_search_window(self):
        """Retain standalone retired-component copy/paint regression coverage.

        This fixture is deliberately outside production navigation. Current
        navigation/multi-person behavior has its own assertions below.
        """
        from PySide6.QtWidgets import QMainWindow
        from gui.person_search import PersonSearchPage
        from gui.copy_toast import CopyToast
        from gui.main_window import STYLE
        window = QMainWindow()
        stack = QStackedWidget(window)
        window.setCentralWidget(stack)
        window.copy_toast = CopyToast(stack)
        window.legacy_search_page = PersonSearchPage(self.service, copy_to_clipboard=window.copy_toast.copy)
        stack.addWidget(window.legacy_search_page)
        window.setStyleSheet(STYLE)
        window.resize(1200, 850)
        return window

    def test_search_layout_copyable_summary_and_derived_fields(self):
        values = self.service.people.get(self.anna)
        values["身份证号"] = "11010519491231002X"
        self.service.update_person(self.anna, values)
        window = self._legacy_search_window()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        search = window.legacy_search_page
        self.assertEqual(1, search.person_model.columnCount())
        self.assertEqual("姓名", search.person_model.headerData(0, Qt.Horizontal))
        self.assertEqual(search.people_view.mapTo(search, QPoint(0, 0)).y(),
                         search.person_info.mapTo(search, QPoint(0, 0)).y())
        self.assertLess(search.findChild(QSplitter).sizes()[0], 250)
        self.assertTrue(search.person_info.textInteractionFlags() & Qt.TextSelectableByMouse)
        self.assertTrue(search.person_info.textInteractionFlags() & Qt.TextSelectableByKeyboard)
        search.person_info.setSelection(0, 2)
        QTest.keyClick(search.person_info, Qt.Key_C, Qt.ControlModifier)
        self.assertEqual(search.person_info.text()[:2], self.app.clipboard().text())
        self.assertIn(f"年龄：{age_from_identity(values['身份证号'])}", search.person_info.text())
        self.assertIn(f"工龄：{work_years(values['进入系统日期'])}", search.person_info.text())

    def test_mouse_checkbox_cell_copy_and_attachment_switch(self):
        before = hashlib.sha256(self.database.read_bytes()).digest()
        window = self._legacy_search_window()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        search = window.legacy_search_page
        search.name_filter.setText("安")
        search.search_people()
        view = search.certificates_view
        first = search.certificate_model.index(1, 0)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(first).center())
        self.app.processEvents()
        self.assertEqual(Qt.Checked, search.certificate_model.data(first, Qt.CheckStateRole))
        self.assertEqual(frozenset({self.cert_high}), search.selected_certificate_ids())
        self.assertIn("1", search.selected_count.text())
        other_cell = search.certificate_model.index(0, 2)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(other_cell).center())
        self.app.processEvents()
        self.assertEqual(0, view.currentIndex().row())
        self.assertEqual(0, len(search.attachment_model.rows))
        self.assertEqual(frozenset({self.cert_high}), search.selected_certificate_ids())
        self.assertEqual(view.selectionBehavior(), QAbstractItemView.SelectItems)
        self.assertEqual(1, len(view.selectedIndexes()))
        QTest.mouseDClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(other_cell).center())
        self.assertEqual("工程师证", self.app.clipboard().text())
        self.assertTrue(window.copy_toast.isVisible())
        self.assertEqual(frozenset({self.cert_high}), search.selected_certificate_ids())
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(first).center())
        self.app.processEvents()
        self.assertEqual(Qt.Unchecked, search.certificate_model.data(first, Qt.CheckStateRole))
        self.assertEqual(frozenset(), search.selected_certificate_ids())
        self.assertEqual(before, hashlib.sha256(self.database.read_bytes()).digest())

    def test_checkbox_remains_painted_and_only_active_first_cell_is_highlighted(self):
        window = self._legacy_search_window()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        search = window.legacy_search_page
        search.name_filter.setText("安")
        search.search_people()
        view = search.certificates_view
        model = search.certificate_model
        first = model.index(1, 0)
        second = model.index(0, 0)

        def checkbox_is_visible(index):
            cell = view.visualRect(index)
            image = view.viewport().grab().toImage()
            background = image.pixelColor(cell.left() + 4, cell.center().y())
            center = cell.center()
            indicator_pixels = (
                image.pixelColor(x, y).rgb()
                for x in range(center.x() - 8, center.x() + 8)
                for y in range(center.y() - 8, center.y() + 8)
            )
            self.assertTrue(any(pixel != background.rgb() for pixel in indicator_pixels))

        checkbox_is_visible(first)  # Initial unchecked state.
        checkbox_is_visible(second)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(first).center())
        self.app.processEvents()
        self.assertEqual(Qt.Checked, model.data(first, Qt.CheckStateRole))
        checkbox_is_visible(first)
        viewed_other = model.index(0, 2)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(viewed_other).center())
        self.app.processEvents()
        self.assertEqual(self.cert_low, model.active_id)
        self.assertEqual(frozenset({self.cert_high}), search.selected_certificate_ids())
        self.assertEqual([], search.attachment_model.rows)
        image = view.viewport().grab().toImage()
        active_rect = view.visualRect(second)
        text_rect = view.visualRect(viewed_other)
        self.assertEqual(QColor("#cfe3fa").rgb(),
                         image.pixelColor(active_rect.left() + 4, active_rect.center().y()).rgb())
        self.assertEqual(QColor("white").rgb(),
                         image.pixelColor(text_rect.right() - 4, text_rect.center().y()).rgb())
        self.assertIsNone(model.data(viewed_other, Qt.BackgroundRole))
        checkbox_is_visible(first)  # Checked box remains visible after changing record.
        checkbox_is_visible(second)
        search.name_filter.setFocus()
        self.app.processEvents()
        checkbox_is_visible(first)  # Losing focus does not hide it.
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(first).center())
        self.app.processEvents()
        self.assertEqual(Qt.Unchecked, model.data(first, Qt.CheckStateRole))
        checkbox_is_visible(first)

    def test_double_click_copies_raw_and_display_values_without_database_writes(self):
        before = hashlib.sha256(self.database.read_bytes()).digest()
        window = self._legacy_search_window()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        search = window.legacy_search_page
        search.name_filter.setText("安")
        search.search_people()
        view = search.certificates_view
        model = search.certificate_model
        self.assertEqual(QAbstractItemView.SingleSelection, view.selectionMode())
        for column, expected in ((1, "执业证"), (2, "注册证"), (3, "A-2"), (5, "长期有效")):
            index = model.index(1, column)
            QTest.mouseDClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(index).center())
            self.app.processEvents()
            self.assertEqual(expected, self.app.clipboard().text())
            self.assertEqual(f"✓ 已复制：{expected}", window.copy_toast.text())
            self.assertTrue(window.copy_toast.isVisible())
        self.app.clipboard().setText("sentinel")
        window.copy_toast.hide()
        empty = model.index(1, 4)
        QTest.mouseDClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(empty).center())
        self.assertEqual("sentinel", self.app.clipboard().text())
        self.assertFalse(window.copy_toast.isVisible())
        checkbox = model.index(1, 0)
        QTest.mouseDClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(checkbox).center())
        self.assertEqual("sentinel", self.app.clipboard().text())
        self.assertFalse(window.copy_toast.isVisible())
        dated = model.index(0, 4)
        QTest.mouseDClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(dated).center())
        self.assertEqual("2030-12-31", self.app.clipboard().text())
        self.assertEqual(self.cert_low, model.active_id)
        self.assertEqual([], search.attachment_model.rows)
        self.assertEqual(before, hashlib.sha256(self.database.read_bytes()).digest())

    def test_copy_toast_elides_text_and_restarts_its_timer(self):
        window = build_main_window(self.service, self.database)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        value = "证书" * 100
        self.assertTrue(window.copy_to_clipboard(value))
        self.assertEqual(value, self.app.clipboard().text())
        self.assertIn("…", window.copy_toast.text())
        self.assertLess(window.copy_toast.geometry().right(), window.findChild(QStackedWidget, "workspace").width())
        QTest.qWait(600)
        self.assertTrue(window.copy_to_clipboard("第二次"))
        QTest.qWait(600)
        self.assertTrue(window.copy_toast.isVisible())
        self.assertEqual("✓ 已复制：第二次", window.copy_toast.text())
        QTest.qWait(450)
        self.assertFalse(window.copy_toast.isVisible())

    def test_maintenance_header_combo_and_attachment_location(self):
        window = build_main_window(self.service, self.database)
        self.addCleanup(window.close)
        window.show()
        window.findChild(QPushButton, "navPersonManage").click()
        self.app.processEvents()
        manage = window.manage_page
        self.assertLessEqual(manage.findChild(type(manage.state_label), "pageTitle").height(), 40)
        self.assertLess(manage.findChild(QSplitter).y(), 130)
        section = manage.findChild(QGroupBox, "certificateAttachmentSection")
        self.assertIsNotNone(section)
        self.assertIs(section, manage.attachments_view.parentWidget())
        self.assertTrue(manage.type_input.isEditable())
        self.assertIn("QComboBox::drop-down", window.styleSheet())
        self.assertIn("QComboBox QAbstractItemView", window.styleSheet())

    def test_maintenance_cancel_preserves_unsaved_input(self):
        window = build_main_window(self.service, self.database)
        self.addCleanup(window.close)
        manage = window.manage_page
        manage.edit_person_button.click()
        manage.person_inputs["姓名"].setText("未保存")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel):
            self.assertFalse(manage.can_leave())
            manage.cancel()
        self.assertEqual("未保存", manage.person_inputs["姓名"].text())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Discard):
            manage.cancel()
        self.assertEqual("查看状态", manage.state_label.text())
        self.assertNotEqual("未保存", manage.person_inputs["姓名"].text())

    def test_maintenance_gui_save_failure_then_create_edit_delete(self):
        window = build_main_window(self.service, self.database)
        self.addCleanup(window.close)
        manage = window.manage_page
        manage.new_person_button.click()
        manage.person_inputs["姓名"].setText("GUI 新人员")
        manage.person_inputs["进入系统日期"].setText("2026-02-30")
        with patch.object(QMessageBox, "warning") as warning:
            manage.save_person_button.click()
            warning.assert_called_once()
        self.assertEqual("new_person", manage.mode)
        self.assertEqual("GUI 新人员", manage.person_inputs["姓名"].text())
        self.assertEqual([], self.service.people.search("GUI 新人员"))
        manage.person_inputs["进入系统日期"].setText("2026-02-28")
        manage.save_person_button.click()
        person_id = manage.person_id
        self.assertEqual("2026-02-28", self.service.people.get(person_id)["进入系统日期"])
        manage.edit_person_button.click()
        manage.person_inputs["姓名"].setText("GUI 修改人员")
        manage.save_person_button.click()
        self.assertEqual("GUI 修改人员", self.service.people.get(person_id)["姓名"])
        manage.new_certificate_button.click()
        manage.type_input.setCurrentText("历史新类别")
        manage.certificate_inputs["证书名称"].setText("GUI 证书")
        manage.save_certificate_button.click()
        certificate_id = manage.certificate_id
        self.assertEqual("历史新类别", self.service.certificates.get(certificate_id)["证书类型"])
        manage.edit_certificate_button.click()
        manage.certificate_inputs["证书编号"].setText("GUI-001")
        manage.save_certificate_button.click()
        self.assertEqual("GUI-001", self.service.certificates.get(certificate_id)["证书编号"])
        with patch.object(QMessageBox, "warning") as warning:
            manage.delete_person_button.click()
            warning.assert_called_once()
        self.assertIsNotNone(self.service.people.get(person_id))
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            manage.delete_certificate_button.click()
            manage.delete_person_button.click()
        self.assertIsNone(self.service.certificates.get(certificate_id))
        self.assertIsNone(self.service.people.get(person_id))

    def test_navigation_prompts_before_discarding_edits(self):
        window = build_main_window(self.service, self.database)
        self.addCleanup(window.close)
        stack = window.findChild(QStackedWidget, "workspace")
        window.findChild(QPushButton, "navPersonManage").click()
        manage = window.manage_page
        manage.edit_person_button.click()
        manage.person_inputs["姓名"].setText("尚未保存")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel):
            window.findChild(QPushButton, "navPersonSearch").click()
        self.assertIs(stack.currentWidget(), manage)
        self.assertEqual("尚未保存", manage.person_inputs["姓名"].text())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Discard):
            window.findChild(QPushButton, "navPersonSearch").click()
        self.assertIs(stack.currentWidget(), window.person_word_page)
        self.assertEqual("view", manage.mode)

    def test_preview_rejects_missing_image_without_deleting_record(self):
        preview = ImagePreview()
        preview.show_path("Images/missing.png")
        self.assertIn("图片文件尚未就位", preview.text())
        self.assertEqual(10, len(self.service.certificates.attachments(self.cert_high)))

    def test_runtime_refuses_old_formal_database(self):
        with self.assertRaisesRegex(ValueError, "尚未切换"):
            validate_runtime_path(DATABASE_FILE)


if __name__ == "__main__":
    unittest.main()
