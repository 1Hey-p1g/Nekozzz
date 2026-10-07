"""Pure fake-COM tests: never attach to or alter a real Word instance."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pywintypes

from services.word_service import (
    WD_PAGE_BREAK, WD_STYLE_NORMAL, WordImageNotFoundError,
    WordNoActiveDocumentError, WordNotRunningError, WordOperationError,
    WordService, WordStyleError,
)


def com_failure():
    return pywintypes.com_error(-1, "fake COM failure", None, None)


class FakeStyles:
    def __init__(self):
        self.seen = []

    def Item(self, key):
        self.seen.append(key)
        if key in ("图片", WD_STYLE_NORMAL):
            return f"style:{key}"
        raise com_failure()


class FakeSelection:
    def __init__(self, image_width=500):
        self.calls = []
        self.image_width = image_width
        self.PageSetup = SimpleNamespace(PageWidth=999, LeftMargin=1, RightMargin=1)
        self.section_setup = SimpleNamespace(PageWidth=595, LeftMargin=72, RightMargin=72)
        self.paragraph = SimpleNamespace(Style=None)
        self.InlineShapes = SimpleNamespace(AddPicture=self.add_picture)

    def Sections(self, index):
        assert index == 1
        return SimpleNamespace(PageSetup=self.section_setup)

    def Paragraphs(self, index):
        assert index == 1
        return self.paragraph

    def add_picture(self, **kwargs):
        self.calls.append(("image", kwargs))
        self.shape = SimpleNamespace(Width=self.image_width, Height=200, LockAspectRatio=False)
        return self.shape

    def TypeText(self, text):
        self.calls.append(("text", text))

    def TypeParagraph(self):
        self.calls.append(("paragraph",))

    def InsertBreak(self, kind):
        self.calls.append(("break", kind))


class WordServiceTests(unittest.TestCase):
    def setUp(self):
        self.selection = FakeSelection()
        self.styles = FakeStyles()
        self.document = SimpleNamespace(Styles=self.styles, PageSetup=SimpleNamespace(PageWidth=20))
        self.application = SimpleNamespace(
            Documents=SimpleNamespace(Count=1), ActiveDocument=self.document,
            Selection=self.selection,
        )
        self.service = WordService(self.application)

    def test_connection_only_uses_active_object(self):
        calls = []
        service = WordService.connect_existing_word(lambda progid: calls.append(progid) or self.application)
        self.assertIs(service.application, self.application)
        self.assertEqual(["Word.Application"], calls)
        with self.assertRaises(WordNotRunningError):
            WordService.connect_existing_word(lambda _progid: (_ for _ in ()).throw(com_failure()))

    def test_no_active_document_and_general_com_failure(self):
        self.application.Documents.Count = 0
        with self.assertRaises(WordNoActiveDocumentError):
            self.service.active_document()
        self.application.Documents.Count = 1
        self.application.Selection = None
        with self.assertRaises(WordOperationError):
            self.service.selection()

    def test_style_checks_and_localization_independent_normal(self):
        self.assertTrue(self.service.style_exists("图片"))
        self.assertFalse(self.service.style_exists("标题 4"))
        self.assertEqual(["标题 4"], self.service.missing_styles(["图片", "标题 4"]))
        self.assertEqual(f"style:{WD_STYLE_NORMAL}", self.service.normal_style())
        self.service.set_selection_style("图片")
        self.assertEqual("style:图片", self.selection.paragraph.Style)
        self.service.set_selection_style(use_normal=True)
        self.assertEqual(f"style:{WD_STYLE_NORMAL}", self.selection.paragraph.Style)
        self.assertIn(WD_STYLE_NORMAL, self.styles.seen)
        with self.assertRaises(WordStyleError):
            self.service.resolve_style(" ")
        with self.assertRaises(WordStyleError):
            self.service.resolve_style("不存在")

    def test_current_section_width(self):
        self.assertEqual(451, self.service.available_page_width())
        self.assertEqual(999, self.selection.PageSetup.PageWidth)

    def test_text_paragraph_and_break_are_separate(self):
        self.service.insert_text("张三")
        self.assertEqual([("text", "张三")], self.selection.calls)
        self.service.insert_paragraph()
        self.assertEqual([("text", "张三"), ("paragraph",)], self.selection.calls)
        self.service.insert_page_break()
        self.assertEqual(("break", WD_PAGE_BREAK), self.selection.calls[-1])
        self.assertEqual(3, len(self.selection.calls))

    def test_all_image_resize_combinations_and_no_other_insertions(self):
        self.selection.section_setup.PageWidth = 544  # 544 - 72 - 72 = 400 points.
        scenarios = (
            (500, True, False, 400), (300, True, False, 300),
            (300, False, True, 400), (500, False, True, 500),
            (300, True, True, 400), (500, True, True, 400),
            (300, False, False, 300), (500, False, False, 500),
        )
        with tempfile.TemporaryDirectory(prefix="TenderSystem_word_fake_") as folder:
            image = Path(folder) / "fake.jpg"
            image.write_bytes(b"test; fake COM never decodes this file")
            for original, shrink, enlarge, expected in scenarios:
                with self.subTest(original=original, shrink=shrink, enlarge=enlarge):
                    self.selection.image_width = original
                    self.selection.calls.clear()
                    shape = self.service.insert_inline_image(
                        image, shrink_oversized=shrink, enlarge_small=enlarge,
                    )
                    self.assertEqual(expected, shape.Width)
                    self.assertEqual(200, shape.Height)
                    self.assertIs(True, shape.LockAspectRatio)
                    self.assertEqual(1, len(self.selection.calls))
                    self.assertEqual("image", self.selection.calls[0][0])
                    self.assertEqual({"FileName": str(image), "LinkToFile": False,
                                      "SaveWithDocument": True}, self.selection.calls[0][1])
            self.selection.calls.clear()
            self.service.insert_inline_image(image)
            self.service.insert_inline_image(image)
            self.assertEqual(["image", "image"], [call[0] for call in self.selection.calls])

    def test_missing_image_and_com_error(self):
        with self.assertRaises(WordImageNotFoundError):
            self.service.insert_inline_image(Path(tempfile.gettempdir()) / "not-present-word-test.jpg")
        self.selection.TypeText = lambda _text: (_ for _ in ()).throw(com_failure())
        with self.assertRaises(WordOperationError):
            self.service.insert_text("text")


if __name__ == "__main__":
    unittest.main()
