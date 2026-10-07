"""Explicit Range tracking; Selection bridge reuses accepted Word image sizing."""
import pywintypes
from win32com.client import constants
from services.word_service import WordOperationError

WD_MAIN_STORY = getattr(constants, 'wdMainTextStory', 1)
WD_WITHIN_TABLE = getattr(constants, 'wdWithInTable', 12)
WD_NO_PROTECTION = getattr(constants, 'wdNoProtection', -1)


class WordTableCursor:
    def __init__(self, word):
        self.word = word
        try:
            self.document = word.active_document()
            selection = word.selection()
            if selection.StoryType != WD_MAIN_STORY or selection.Start != selection.End:
                raise WordOperationError('请将 Word 光标置于正文，且不要选中文字。')
            if selection.Information(WD_WITHIN_TABLE):
                raise WordOperationError('自动填表光标必须位于表格外。')
            if self.document.ProtectionType != WD_NO_PROTECTION or self.document.TrackRevisions or self.document.ReadOnly:
                raise WordOperationError('请使用可编辑、未保护且关闭修订的 Word 文档。')
            self.position = int(selection.Range.Duplicate.Start)
            self.original_position = self.position
            self.original_end = int(self.document.Content.End)
            self.name = self.document.FullName
        except pywintypes.com_error as error:
            raise WordOperationError('无法检查 Word 光标或文档编辑状态') from error

    def range(self):
        return self.document.Range(self.position, self.position)

    def available_width(self):
        return self.word.available_page_width()

    def assert_unchanged(self):
        selection = self.word.selection()
        if (self.word.active_document().FullName != self.name or selection.Start != self.original_position
                or selection.End != self.original_position or selection.StoryType != WD_MAIN_STORY
                or int(self.document.Content.End) != self.original_end):
            raise WordOperationError('预检查期间 Word 文档或光标已变化，请重新输出。')

    def outside(self):
        if self.range().Information(WD_WITHIN_TABLE):
            raise WordOperationError('插入位置意外进入表格单元格，已停止。')

    def mutate(self, operation):
        self.outside()
        start, before = self.position, int(self.document.Content.End)
        self.range().Select()
        operation()
        delta = int(self.document.Content.End) - before
        if delta <= 0:
            raise WordOperationError('Word 插入没有产生预期内容。')
        self.position = start + delta
        self.outside()

    def boundary(self):
        p = self.range().Paragraphs.Item(1).Range
        adjacent = self.position > 0 and self.document.Range(self.position-1, self.position).Information(WD_WITHIN_TABLE)
        if self.position != int(p.Start) or adjacent:
            self.mutate(self.word.insert_paragraph)

    def text(self, text, style, normal):
        # Soft breaks keep a multi-line note in one external paragraph. Apply its
        # style after creating that paragraph, without restyling the original tail.
        start = self.position
        text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\v')
        self.mutate(lambda: self.word.insert_text(text))
        self.mutate(self.word.insert_paragraph)
        self.document.Range(start, self.position-1).Paragraphs.Item(1).Style = self.word.resolve_style(style, use_normal=normal)

    def table(self, xml):
        start, before = self.position, int(self.document.Content.End)
        count = int(self.document.Tables.Count)
        self.word.insert_open_xml(self.range(), xml)
        end = start + int(self.document.Content.End) - before
        if int(self.document.Tables.Count) != count + 1:
            raise WordOperationError('表格可能与周围表格合并，已停止。')
        self.position = int(self.document.Range(start, end).Tables.Item(1).Range.End)
        self.outside()

    def image_style(self, name, normal):
        self.outside()
        self.range().Select()
        self.word.set_selection_style(name, use_normal=normal)

    def attachment_start(self, position):
        self.position = position
        self.outside()
        self.range().Select()

    def insert_inline_image(self, path, **options):
        self.outside()
        self.range().Select()
        shape = self.word.insert_inline_image(path, **options)
        self.position = int(shape.Range.End)  # Never trust Selection drift after AddPicture.
        self.outside()
        self.range().Select()
        return shape

    def page_break(self):
        self.mutate(self.word.insert_page_break)

    def finish(self):
        self.outside()
        self.range().Select()
