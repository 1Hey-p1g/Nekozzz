"""Small, business-neutral primitives for the user's running Microsoft Word.

No document is opened, created, saved, closed, or selected by this module.
The caller chooses when to insert each paragraph, image, and page break.
"""

from pathlib import Path

import pywintypes
from win32com.client import GetActiveObject, constants


# Word's named enum values are stable even when pywin32 has not loaded the Word
# type library (which is common for a dynamic GetActiveObject connection).
WD_STYLE_NORMAL = getattr(constants, "wdStyleNormal", -1)
WD_PAGE_BREAK = getattr(constants, "wdPageBreak", 7)


class WordServiceError(Exception):
    """Base error for Word automation."""


class WordNotRunningError(WordServiceError):
    pass


class WordNoActiveDocumentError(WordServiceError):
    pass


class WordStyleError(WordServiceError):
    pass


class WordImageNotFoundError(WordServiceError):
    pass


class WordOperationError(WordServiceError):
    pass


class WordService:
    def __init__(self, application):
        """Accept an existing COM application (or a fake in isolated tests)."""
        self.application = application

    @classmethod
    def connect_existing_word(cls, get_active_object=None):
        """Attach only to an already running Word.Application instance."""
        get_active_object = get_active_object or GetActiveObject
        try:
            application = get_active_object("Word.Application")
        except pywintypes.com_error as error:
            raise WordNotRunningError("Word.Application is not running or unavailable") from error
        if application is None:
            raise WordNotRunningError("Word.Application is not running or unavailable")
        return cls(application)

    def active_document(self):
        try:
            if self.application.Documents.Count == 0:
                raise WordNoActiveDocumentError("Word has no active document")
            document = self.application.ActiveDocument
        except WordNoActiveDocumentError:
            raise
        except pywintypes.com_error as error:
            raise WordOperationError("Failed to read Word ActiveDocument") from error
        if document is None:
            raise WordNoActiveDocumentError("Word has no active document")
        return document

    def selection(self):
        self.active_document()
        try:
            selection = self.application.Selection
        except pywintypes.com_error as error:
            raise WordOperationError("Failed to read Word Selection") from error
        if selection is None:
            raise WordOperationError("Word has no current Selection")
        return selection

    @staticmethod
    def _style_name(name):
        if not isinstance(name, str) or not name.strip():
            raise WordStyleError(f"Invalid Word style name: {name!r}")
        return name.strip()

    def style_exists(self, name):
        name = self._style_name(name)
        try:
            self.active_document().Styles.Item(name)
        except pywintypes.com_error:
            return False
        return True

    def missing_styles(self, names):
        """Return missing names in input order, without changing the document."""
        return [name for name in names if not self.style_exists(name)]

    def normal_style(self):
        """Resolve Word's built-in Normal style by ID, not its localized name."""
        try:
            return self.active_document().Styles.Item(WD_STYLE_NORMAL)
        except pywintypes.com_error as error:
            raise WordStyleError("Word built-in Normal style is unavailable") from error

    def resolve_style(self, name=None, *, use_normal=False):
        """Resolve the requested style; fallback requires explicit caller intent."""
        if use_normal:
            return self.normal_style()
        name = self._style_name(name)
        try:
            return self.active_document().Styles.Item(name)
        except pywintypes.com_error as error:
            raise WordStyleError(f"Word style is unavailable: {name!r}") from error

    def set_selection_style(self, name=None, *, use_normal=False):
        style = self.resolve_style(name, use_normal=use_normal)
        try:
            self.selection().Paragraphs(1).Style = style
        except pywintypes.com_error as error:
            raise WordOperationError("Failed to set Selection paragraph style") from error

    def insert_text(self, text):
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        try:
            self.selection().TypeText(text)
        except pywintypes.com_error as error:
            raise WordOperationError("Failed to insert text") from error

    def insert_paragraph(self):
        try:
            self.selection().TypeParagraph()
        except pywintypes.com_error as error:
            raise WordOperationError("Failed to insert paragraph") from error

    def available_page_width(self):
        """Current Selection Section width in Word points."""
        try:
            setup = self.selection().Sections(1).PageSetup
            width = setup.PageWidth - setup.LeftMargin - setup.RightMargin
        except pywintypes.com_error as error:
            raise WordOperationError("Failed to read current Section PageSetup") from error
        if width <= 0:
            raise WordOperationError(f"Current Section has invalid usable width: {width!r}")
        return width

    def insert_inline_image(self, path, *, shrink_oversized=True, enlarge_small=False):
        """Insert one image only; use Word's inserted Width and preserve aspect ratio."""
        image_path = Path(path)
        if not image_path.is_absolute() or not image_path.is_file():
            raise WordImageNotFoundError(str(image_path))
        try:
            shape = self.selection().InlineShapes.AddPicture(
                FileName=str(image_path), LinkToFile=False, SaveWithDocument=True,
            )
            original_width = shape.Width
            shape.LockAspectRatio = True
            if shrink_oversized or enlarge_small:
                usable_width = self.available_page_width()
                if ((shrink_oversized and original_width > usable_width)
                        or (enlarge_small and original_width < usable_width)):
                    shape.Width = usable_width
            return shape
        except pywintypes.com_error as error:
            raise WordOperationError(f"Failed to insert inline image: {image_path}") from error

    def insert_page_break(self):
        try:
            self.selection().InsertBreak(WD_PAGE_BREAK)
        except pywintypes.com_error as error:
            raise WordOperationError("Failed to insert page break") from error

    def insert_open_xml(self, insertion_range, xml):
        """Insert at an explicitly collapsed Range; no business/template knowledge."""
        try:
            if insertion_range.Start != insertion_range.End:
                raise WordOperationError("Open XML insertion requires a collapsed Range")
            insertion_range.InsertXML(xml)
        except pywintypes.com_error as error:
            raise WordOperationError("Failed to insert Word Open XML") from error
