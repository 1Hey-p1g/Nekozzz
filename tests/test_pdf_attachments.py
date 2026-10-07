"""Isolated PDF, settings, attachment rollback and inline GUI tests."""

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QStackedWidget

from database.initializer import create_empty_database
from database.runtime import runtime_connection
from gui.main_window import build_main_window
from repositories.attachment_repository import CertificateAttachmentRepository
from services.attachments import CertificateAttachmentService
from services.pdf_import import render_pdf, rotate_temporary_page
from services.people import PeopleService
from services.settings import PdfSettings, SettingsService


class PdfAttachmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="TenderSystem_pdf_test_")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.db = self.root / "v1.db"
        self.settings = SettingsService(self.root / "config" / "settings.json")
        create_empty_database(self.db)
        self.people = PeopleService(self.db)
        person = self.people.add_person({"姓名": "附件测试", "身份证号": None, "联系电话": None,
                                         "学历": None, "毕业院校": None, "专业": None, "进入系统日期": None})
        self.cert = self.people.add_certificate({"人员ID": person, "证书类型": "执业证", "证书名称": "测试证书",
                                                 "证书编号": "A1", "有效期": None})
        self.other_cert = self.people.add_certificate({"人员ID": person, "证书类型": "职称证", "证书名称": "共享证书",
                                                       "证书编号": "A2", "有效期": None})
        self.attachments = CertificateAttachmentService(self.db, data_root=self.root)

    def pdf(self, name="source.pdf", count=3):
        path = self.root / name
        document = pymupdf.open()
        for number in range(1, count + 1):
            page = document.new_page(width=72 * number, height=72)
            page.draw_rect(pymupdf.Rect(2, 2, 20, 20), color=(1, 0, 0), fill=(1, 0, 0))
            page.insert_text((10, 30), f"PAGE {number}")
        document.save(str(path))
        document.close()
        return path

    def test_settings_defaults_persist_and_recover_from_invalid_json(self):
        self.assertEqual(PdfSettings(), self.settings.load())
        custom = PdfSettings(300, 85, "Grayscale")
        self.settings.save(custom)
        self.assertEqual(custom, SettingsService(self.settings.path).load())
        for invalid in ('{', '{"dpi":200}', '{"dpi":false,"jpeg_quality":90,"color_mode":"RGB"}',
                        '{"dpi":200,"jpeg_quality":76,"color_mode":"RGB"}'):
            self.settings.path.write_text(invalid, encoding="utf-8")
            self.assertEqual(PdfSettings(), self.settings.load())
        with self.assertRaises(ValueError):
            self.settings.save(PdfSettings(72, 90, "RGB"))

    def test_render_one_and_multiple_pages_rgb_grayscale_and_rotation(self):
        source = self.pdf(count=1)
        with render_pdf(source) as pages:
            self.assertEqual([1], [page.number for page in pages])
            self.assertEqual((200, 200), (QImage(str(pages[0].path)).width(), QImage(str(pages[0].path)).height()))
            rgb = QImage(str(pages[0].path)).pixelColor(15, 15)
            self.assertGreater(rgb.red(), rgb.green() + 100)
            self.assertGreater(rgb.red(), rgb.blue() + 100)
            temporary = pages[0].path
        self.assertFalse(temporary.exists())
        source = self.pdf("multi.pdf", 3)
        with render_pdf(source, PdfSettings(150, 90, "Grayscale")) as pages:
            self.assertEqual([1, 2, 3], [page.number for page in pages])
            self.assertEqual([150, 300, 450], [QImage(str(page.path)).width() for page in pages])
            pixel = QImage(str(pages[0].path)).pixelColor(15, 15)
            self.assertEqual(pixel.red(), pixel.green())
            self.assertEqual(pixel.green(), pixel.blue())
            rotate_temporary_page(pages[1], 90, quality=90)
            self.assertEqual((150, 300), (QImage(str(pages[1].path)).width(), QImage(str(pages[1].path)).height()))
            moved_mark = QImage(str(pages[1].path)).pixelColor(135, 15)
            self.assertLess(moved_mark.red(), 200)  # Gray red patch moved to the upper right.
            self.assertGreater(QImage(str(pages[1].path)).pixelColor(15, 15).red(), 230)
        self.assertFalse(pages[0].path.parent.exists())

    def test_render_failure_cleans_temporary_directory(self):
        before = set(Path(tempfile.gettempdir()).glob("TenderSystem_pdf_*"))
        bad = self.root / "broken.pdf"
        bad.write_bytes(b"not a PDF")
        with self.assertRaises(Exception):
            with render_pdf(bad):
                pass
        self.assertEqual(before, set(Path(tempfile.gettempdir()).glob("TenderSystem_pdf_*")))

    def test_import_replace_delete_and_shared_path(self):
        with render_pdf(self.pdf(count=3)) as pages:
            result = self.attachments.save_pages(self.cert, pages)
        self.assertEqual(3, result.page_count)
        old = self.people.certificates.attachments(self.cert)
        self.assertEqual(["1", "2", "3"], [row["备注"] for row in old])
        self.assertTrue(all(re.fullmatch(r"Images/[0-9a-f-]{36}\.jpg", row["路径"]) for row in old))
        self.assertTrue(all((self.root / row["路径"]).is_file() for row in old))
        with runtime_connection(self.db, write=True) as connection:
            connection.execute('INSERT INTO 人员证书图表 (证书ID,路径,备注) VALUES (?,?,?)',
                               (self.other_cert, old[0]["路径"], "1"))
        with render_pdf(self.pdf("replacement.pdf", 2)) as pages:
            result = self.attachments.save_pages(self.cert, pages, replace=True)
        self.assertEqual(2, result.page_count)
        self.assertEqual(["1", "2"], [row["备注"] for row in self.people.certificates.attachments(self.cert)])
        self.assertTrue((self.root / old[0]["路径"]).exists())  # Still referenced by another certificate.
        self.assertFalse((self.root / old[1]["路径"]).exists())
        self.assertFalse((self.root / old[2]["路径"]).exists())
        self.attachments.delete_all(self.other_cert)
        self.assertFalse((self.root / old[0]["路径"]).exists())
        new = self.people.certificates.attachments(self.cert)
        self.attachments.delete_all(self.cert)
        self.assertFalse(self.people.certificates.attachments(self.cert))
        self.assertTrue(all(not (self.root / row["路径"]).exists() for row in new))

    def test_failure_rolls_back_database_and_new_files(self):
        with render_pdf(self.pdf(count=1)) as pages:
            self.attachments.save_pages(self.cert, pages)
        original = self.people.certificates.attachments(self.cert)
        image_paths = {path.name for path in (self.root / "Images").iterdir()}
        with render_pdf(self.pdf("new.pdf", 2)) as pages:
            with patch.object(CertificateAttachmentRepository, "replace_rows", side_effect=RuntimeError("injected")):
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    self.attachments.save_pages(self.cert, pages, replace=True)
        self.assertEqual(original, self.people.certificates.attachments(self.cert))
        self.assertEqual(image_paths, {path.name for path in (self.root / "Images").iterdir()})
        with render_pdf(self.pdf("bad_order.pdf", 2)) as pages:
            with self.assertRaises(ValueError):
                self.attachments.save_pages(self.other_cert, tuple(reversed(pages)))
        self.assertFalse(self.people.certificates.attachments(self.other_cert))

    def test_image_copy_failure_removes_partial_file_and_preserves_pdf(self):
        source = self.pdf("copy_error.pdf", 2)
        original_pdf = source.read_bytes()
        with render_pdf(source) as pages:
            with patch("services.attachments.shutil.copyfileobj", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    self.attachments.save_pages(self.cert, pages)
        self.assertFalse(self.people.certificates.attachments(self.cert))
        self.assertEqual([], list((self.root / "Images").iterdir()))
        self.assertEqual(original_pdf, source.read_bytes())

    def test_inline_preview_cancel_confirm_replace_and_settings_navigation(self):
        window = build_main_window(self.people, self.db, settings_service=self.settings,
                                   attachment_service=self.attachments)
        self.addCleanup(window.close)
        window.show()
        window.findChild(QPushButton, "navSettings").click()
        self.assertIs(window.findChild(QStackedWidget, "workspace").currentWidget(), window.settings_page)
        window.settings_page.dpi.setCurrentText("150 DPI")
        self.assertEqual(150, self.settings.load().dpi)
        window.findChild(QPushButton, "navPersonManage").click()
        manage = window.manage_page
        self.assertEqual(self.cert, manage.certificate_id)
        source = self.pdf("preview.pdf", 3)
        manage.start_pdf_import(source)
        QTest.qWait(20)
        self.assertTrue(manage.import_preview.isVisible())
        self.assertGreater(manage.detail_scroll.verticalScrollBar().value(), 0)
        self.assertEqual("第 1 / 3 页", manage.import_page_label.text())
        manage.next_page_button.click()
        self.assertEqual("第 2 / 3 页", manage.import_page_label.text())
        manage.rotate_right_button.click()
        self.assertEqual((150, 300), (QImage(str(manage._pending_pages[1].path)).width(),
                                      QImage(str(manage._pending_pages[1].path)).height()))
        manage.cancel_import_button.click()
        self.assertFalse(manage.import_preview.isVisible())
        self.assertFalse((self.root / "Images").exists())
        self.assertFalse(self.people.certificates.attachments(self.cert))
        manage.start_pdf_import(source)
        manage.confirm_import_button.click()
        self.assertEqual(3, len(manage.attachment_model.rows))
        self.assertNotIn("尚未就位", manage.preview.text())
        old_paths = [row["路径"] for row in manage.attachment_model.rows]
        manage.start_pdf_import(self.pdf("second.pdf", 1), replace=True)
        manage.confirm_import_button.click()
        self.assertEqual(1, len(manage.attachment_model.rows))
        self.assertTrue(all(not (self.root / path).exists() for path in old_paths))
        window.close()
        second_window = build_main_window(self.people, self.db, settings_service=self.settings,
                                          attachment_service=self.attachments)
        self.addCleanup(second_window.close)
        second_window.show()
        second_window.findChild(QPushButton, "navPersonManage").click()
        self.assertEqual(1, len(second_window.manage_page.attachment_model.rows))
        self.assertNotIn("尚未就位", second_window.manage_page.preview.text())
