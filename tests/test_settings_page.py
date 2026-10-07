"""Focused SettingsPage tests using a temporary JSON file, without main.py."""

import os
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QListWidget

from gui.settings_page import QUALITY_VALUES, SettingsPage
from database.initializer import create_empty_database
from repositories.certificate_repository import CertificateRepository
from services.settings import PdfSettings, SettingsService, merge_certificate_type_order


class CountingSettingsService(SettingsService):
    def __init__(self, path):
        super().__init__(path)
        self.saved = []

    def save(self, settings):
        self.saved.append(settings)
        super().save(settings)


class SettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="TenderSystem_settings_")
        self.addCleanup(folder.cleanup)
        self.service = CountingSettingsService(Path(folder.name) / "settings.json")
        self.messages = []
        self.page = SettingsPage(self.service, self.messages.append)
        self.addCleanup(self.page.close)
        self.page.resize(850, 720)
        self.page.show()
        self.app.processEvents()

    def test_autofill_styles_defaults_legacy_and_independent_persistence(self):
        keys = ('autofill_title_style', 'autofill_note_style', 'autofill_person_name_style')
        for key in keys:
            self.assertEqual(getattr(PdfSettings(), key), '')
            self.assertEqual(getattr(self.page, key).text(), '')
        self.assertEqual(self.service.saved, [])
        legacy = {'person_name_style': 'ordinary text', 'image_style': 'ordinary image',
                  'future_key': 'preserved'}
        self.service.path.write_text(json.dumps(legacy), encoding='utf-8')
        original = self.service.path.read_bytes()
        self.page.show_settings(self.service.load())
        self.assertEqual(self.service.path.read_bytes(), original)
        self.assertEqual(self.service.saved, [])
        for key, name in zip(keys, (' AF title ', ' AF note ', ' AF name ')):
            getattr(self.page, key).setText(name)
            getattr(self.page, key).editingFinished.emit()
            self.assertEqual(getattr(self.service.load(), key), name.strip())
        self.assertEqual(self.service.load().person_name_style, 'ordinary text')
        self.assertEqual(self.service.load().image_style, 'ordinary image')
        self.assertEqual(json.loads(self.service.path.read_text(encoding='utf-8'))['future_key'], 'preserved')
        self.page.person_name_style.setText('changed ordinary')
        self.page.person_name_style.editingFinished.emit()
        self.assertEqual(tuple(getattr(self.service.load(), key) for key in keys),
                         ('AF title', 'AF note', 'AF name'))
        saved_count = len(self.service.saved)
        self.page.show_settings(self.service.load())
        self.assertEqual(len(self.service.saved), saved_count)

    def test_structure_defaults_and_loading_do_not_save(self):
        self.assertEqual([], self.service.saved)
        self.assertFalse(self.service.path.exists())
        self.assertEqual((150, 200, 300), tuple(self.page.dpi.itemData(i) for i in range(3)))
        self.assertEqual(200, self.page.dpi.currentData())
        self.assertEqual(2, self.page.quality.value())
        self.assertEqual("当前：90", self.page.quality_value.text())
        self.assertEqual("RGB", self.page.color.currentText())
        self.assertEqual((0, 3, 1, 1, 1), (
            self.page.quality.minimum(), self.page.quality.maximum(), self.page.quality.singleStep(),
            self.page.quality.pageStep(), self.page.quality.tickInterval(),
        ))
        self.assertEqual(self.page.dpi.width(), self.page.color.width())
        self.assertLessEqual(self.page.dpi.width(), 130)
        self.assertTrue(self.page.theme.isEnabled())
        self.assertEqual("跟随系统", self.page.theme.currentText())
        for name in ("accessImport", "backupDatabase", "restoreDatabase"):
            self.assertFalse(self.page.findChild(type(self.page.defaults_button), name).isEnabled())
        self.page.show_settings(PdfSettings(300, 85, "Grayscale"))
        self.assertEqual([], self.service.saved)
        self.assertFalse(self.service.path.exists())
        self.assertEqual("当前：85", self.page.quality_value.text())

    def test_each_pdf_control_saves_immediately_without_success_toast(self):
        self.page.dpi.setCurrentIndex(self.page.dpi.findData(150))
        self.assertEqual(PdfSettings(150, 90, "RGB"), self.service.load())
        self.page.color.setCurrentText("Grayscale")
        self.assertEqual(PdfSettings(150, 90, "Grayscale"), self.service.load())
        for position, expected in enumerate(QUALITY_VALUES):
            self.page.quality.setValue(position)
            self.assertEqual(expected, self.service.load().jpeg_quality)
            self.assertEqual(f"当前：{expected}", self.page.quality_value.text())
        self.assertEqual([], self.messages)
        self.assertEqual("", self.page.error_label.text())

    def test_failed_save_shows_error_and_next_success_clears_it(self):
        with patch.object(self.service, "save", side_effect=OSError("readonly")):
            self.page.dpi.setCurrentIndex(self.page.dpi.findData(300))
        self.assertEqual("保存设置失败：readonly", self.page.error_label.text())
        self.assertEqual(200, self.page.dpi.currentData())
        self.page.dpi.setCurrentIndex(self.page.dpi.findData(150))
        self.assertEqual("", self.page.error_label.text())
        self.assertEqual(150, self.service.load().dpi)

    def test_restore_confirmation_saves_only_once(self):
        self.page.dpi.setCurrentIndex(self.page.dpi.findData(300))
        self.page.quality.setValue(3)
        self.page.color.setCurrentText("Grayscale")
        saved_before = len(self.service.saved)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            self.page.defaults_button.click()
        self.assertEqual(saved_before, len(self.service.saved))
        self.assertEqual([], self.messages)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.page.defaults_button.click()
        self.assertEqual(saved_before + 1, len(self.service.saved))
        self.assertEqual(PdfSettings(), self.service.load())
        self.assertEqual((200, 2, "RGB"), (self.page.dpi.currentData(), self.page.quality.value(),
                                             self.page.color.currentText()))
        self.assertEqual(["已恢复默认设置"], self.messages)

    def test_short_page_scrolls_and_cards_stay_within_width(self):
        self.page.resize(590, 330)
        self.app.processEvents()
        self.assertGreater(self.page.scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(0, self.page.scroll.horizontalScrollBar().maximum())

    def test_legacy_pdf_json_and_word_defaults(self):
        self.service.path.write_text(json.dumps({"dpi": 300, "jpeg_quality": 85,
                                                 "color_mode": "Grayscale"}), encoding="utf-8")
        loaded = self.service.load()
        self.assertEqual((300, 85, "Grayscale"), (loaded.dpi, loaded.jpeg_quality, loaded.color_mode))
        self.assertEqual(("图片", "标题 4", True, False, ()),
                         (loaded.image_style, loaded.person_name_style,
                          loaded.shrink_oversized_images, loaded.enlarge_small_images,
                          loaded.person_certificate_type_order))

    def test_word_preferences_persist_and_blank_styles_reset(self):
        self.page.image_style.setText("  附件图片  ")
        self.page.image_style.editingFinished.emit()
        self.page.person_name_style.setText("    ")
        self.page.person_name_style.editingFinished.emit()
        self.page.shrink_images.setChecked(False)
        self.page.enlarge_images.setChecked(True)
        loaded = SettingsService(self.service.path).load()
        self.assertEqual("附件图片", loaded.image_style)
        self.assertEqual("标题 4", loaded.person_name_style)
        self.assertFalse(loaded.shrink_oversized_images)
        self.assertTrue(loaded.enlarge_small_images)
        self.assertEqual("标题 4", self.page.person_name_style.text())

    def test_type_merge_preserves_missing_saved_types_and_appends_new(self):
        self.assertEqual(("A", "B", "C", "D", "E"), merge_certificate_type_order(
            ("A", "B", "C"), (" E ", "D", "A", None, "", "D")))
        self.assertEqual(("A", "B", "C"), merge_certificate_type_order(
            ("A", "B", "C"), ("A", "C")))
        self.page.certificate_types = lambda: ("E", "A", "D")
        self.page.show_settings(replace(PdfSettings(), person_certificate_type_order=("A", "B", "C")))
        self.assertEqual(("A", "B", "C", "D", "E"), self.page.certificate_order.values())
        self.assertEqual([], self.service.saved)

    def test_order_move_persists_once_and_reset_uses_database_types(self):
        self.page.certificate_types = lambda: ("C", "A", "B")
        self.page.refresh_certificate_types()
        self.assertEqual(("A", "B", "C"), self.page.certificate_order.values())
        self.assertEqual(QListWidget.InternalMove, self.page.certificate_order.dragDropMode())
        item = self.page.certificate_order.takeItem(2)
        self.page.certificate_order.insertItem(0, item)
        self.page.certificate_order.order_changed.emit()  # One completed drop, not drag movement.
        self.assertEqual(1, len(self.service.saved))
        self.assertEqual(("C", "A", "B"), self.service.load().person_certificate_type_order)
        self.page.certificate_types = lambda: ("Z", "B", "A")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.page.defaults_button.click()
        self.assertEqual(2, len(self.service.saved))
        self.assertEqual(("A", "B", "Z"), self.service.load().person_certificate_type_order)
        self.assertEqual(("A", "B", "Z"), self.page.certificate_order.values())

    def test_invalid_json_fallback_and_unknown_fields_preserved(self):
        self.service.path.write_text("{bad", encoding="utf-8")
        self.assertEqual(PdfSettings(), self.service.load())
        self.service.path.write_text(json.dumps({"dpi": 200, "jpeg_quality": 90,
                                                 "color_mode": "RGB", "future": 12}), encoding="utf-8")
        self.service.save(replace(self.service.load(), image_style="图片2"))
        self.assertEqual(12, json.loads(self.service.path.read_text(encoding="utf-8"))["future"])

    def test_long_type_list_scrolls_inside_card(self):
        self.page.certificate_types = lambda: tuple(f"类型{i:02d}" for i in range(50))
        self.page.refresh_certificate_types()
        self.app.processEvents()
        self.assertGreater(self.page.certificate_order.verticalScrollBar().maximum(), 0)
        self.assertEqual(190, self.page.certificate_order.height())

    def test_certificate_types_are_read_only_from_isolated_v1_database(self):
        with tempfile.TemporaryDirectory(prefix="TenderSystem_settings_v1_") as folder:
            target = Path(folder) / "types.db"
            create_empty_database(target)
            with closing(sqlite3.connect(target)) as connection:
                with connection:
                    connection.execute("INSERT INTO 人员表(人员ID,姓名) VALUES(1,'测试')")
                    for index, kind in enumerate((" B ", "A", "B", None, " "), 1):
                        connection.execute(
                            "INSERT INTO 人员证书表(证书ID,人员ID,证书名称,证书类型) VALUES(?,1,?,?)",
                            (index, f"证书{index}", kind),
                        )
            repository = CertificateRepository(target)
            self.assertEqual(["A", "B"], repository.list_certificate_types())
            self.page.certificate_types = repository.list_certificate_types
            self.page.refresh_certificate_types()
            self.assertEqual(("A", "B"), self.page.certificate_order.values())
            self.assertEqual([], self.service.saved)
