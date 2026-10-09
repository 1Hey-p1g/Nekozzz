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
    def __init__(self, application, *, application_name='Microsoft Word'):
        """Accept an existing COM application (or a fake in isolated tests)."""
        self.application = application
        self.application_name = application_name

    def operation_error(self, action, error=None):
        detail = f'；COM：{error}' if error is not None else ''
        return WordOperationError(f'{self.application_name}：{action}{detail}')

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
                raise WordNoActiveDocumentError(f'{self.application_name} 当前没有活动文档')
            document = self.application.ActiveDocument
        except WordNoActiveDocumentError:
            raise
        except pywintypes.com_error as error:
            raise self.operation_error('无法读取活动文档', error) from error
        if document is None:
            raise WordNoActiveDocumentError(f'{self.application_name} 当前没有活动文档')
        return document

    def selection(self):
        self.active_document()
        try:
            selection = self.application.Selection
        except pywintypes.com_error as error:
            raise self.operation_error('无法获取光标位置', error) from error
        if selection is None:
            raise self.operation_error('无法获取当前光标位置')
        return selection

    @staticmethod
    def _style_name(name):
        if not isinstance(name, str) or not name.strip():
            raise WordStyleError(f'样式名称必须是非空文本：{name!r}')
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
            raise WordStyleError(f'{self.application_name} 内置正文样式不可用；COM：{error}') from error

    def resolve_style(self, name=None, *, use_normal=False):
        """Resolve the requested style; fallback requires explicit caller intent."""
        if use_normal:
            return self.normal_style()
        name = self._style_name(name)
        try:
            return self.active_document().Styles.Item(name)
        except pywintypes.com_error as error:
            raise WordStyleError(f'{self.application_name} 样式不可用：{name!r}；COM：{error}') from error

    def set_selection_style(self, name=None, *, use_normal=False):
        style = self.resolve_style(name, use_normal=use_normal)
        try:
            self.selection().Paragraphs(1).Style = style
        except pywintypes.com_error as error:
            raise self.operation_error('无法设置段落样式', error) from error

    def insert_text(self, text):
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        try:
            self.selection().TypeText(text)
        except pywintypes.com_error as error:
            raise self.operation_error('文字插入失败，可能已有部分内容写入', error) from error

    def insert_paragraph(self):
        try:
            self.selection().TypeParagraph()
        except pywintypes.com_error as error:
            raise self.operation_error('段落插入失败，可能已有部分内容写入', error) from error

    def available_page_width(self):
        """Current Selection Section width in Word points."""
        try:
            setup = self.selection().Sections(1).PageSetup
            width = setup.PageWidth - setup.LeftMargin - setup.RightMargin
        except pywintypes.com_error as error:
            raise self.operation_error('无法读取当前节的页面尺寸', error) from error
        if width <= 0:
            raise self.operation_error(f'当前节的可用宽度无效：{width!r}')
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
            raise self.operation_error(f'图片插入失败：{image_path}，可能已有部分内容写入', error) from error

    def insert_page_break(self):
        try:
            self.selection().InsertBreak(WD_PAGE_BREAK)
        except pywintypes.com_error as error:
            raise self.operation_error('分页插入失败，可能已有部分内容写入', error) from error

    def insert_open_xml(self, insertion_range, xml):
        """Insert at an explicitly collapsed Range; no business/template knowledge."""
        try:
            if insertion_range.Start != insertion_range.End:
                raise self.operation_error('Open XML 插入位置必须为折叠光标')
            insertion_range.InsertXML(xml)
        except pywintypes.com_error as error:
            raise self.operation_error('InsertXML 插入失败，可能已有部分内容写入', error) from error
