"""Award and finance workspaces sharing the established V1 widgets and PDF editor."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFormLayout, QHeaderView, QHBoxLayout, QLabel,
    QComboBox, QLayout, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

from gui.common import CertificateTextDelegate, CheckBoxDelegate, ImagePreview, RowsModel, StyledComboBox, table_view
from gui.project_attachments import ProjectAttachmentEditor
from gui.word_styles import confirm_style_fallback
from services.report_word import ReportWordPreflightError, ReportWordWriteError
from services.word_service import WordNoActiveDocumentError, WordNotRunningError, WordServiceError


class ReportSearchPage(QWidget):
    """Checkbox output selection and current viewing are separate session states."""

    def __init__(self, service, output_service, settings_service, notify, copy_to_clipboard=None):
        super().__init__()
        self.service, self.repository = service, service.repository
        self.output_service, self.settings_service, self.notify = output_service, settings_service, notify
        self.copy_to_clipboard = copy_to_clipboard or QGuiApplication.clipboard().setText
        self.selected_ids, self.current_record_id = set(), None
        self.is_award = self.repository.key == '获奖ID'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel(self.repository.label + '选择')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        subtitle = QLabel('勾选本次输出；点击文字查看资料和附件，双击实际值复制。按年度最新优先输出。')
        subtitle.setObjectName('subtitle')
        layout.addWidget(subtitle)
        filters = QHBoxLayout()
        self.filters = {}
        definitions = (('name', '获奖名称'), ('year', '获奖年份'), ('grade', '获奖级别'),
                       ('project', '关联工程名称')) if self.is_award else (('year', '财务报告年度'),)
        for key, placeholder in definitions:
            editor = QLineEdit()
            editor.setPlaceholderText(placeholder)
            editor.returnPressed.connect(self.search)
            self.filters[key] = editor
            filters.addWidget(editor)
        search, clear = QPushButton('搜索'), QPushButton('清空')
        search.clicked.connect(self.search)
        clear.clicked.connect(self.clear_search)
        filters.addWidget(search)
        filters.addWidget(clear)
        layout.addLayout(filters)
        split = QSplitter(Qt.Horizontal)
        columns = [('选择', ''), ('获奖名称', '获奖名称'), ('年份', '获奖年份')] if self.is_award else [
            ('选择', ''), ('财务报告年度', '财务报告年度')]
        self.model = RowsModel(columns, self, check_key=self.repository.key, checked=self.selected_ids)
        self.records_view = table_view(self.model)
        self.records_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.records_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.records_view.setAlternatingRowColors(False)
        self.records_view.setItemDelegate(CertificateTextDelegate(self.records_view))
        self.records_view.setItemDelegateForColumn(0, CheckBoxDelegate(self.records_view))
        self.records_view.horizontalHeader().setStretchLastSection(False)
        self.records_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.records_view.setColumnWidth(0, 55)
        if self.is_award:
            self.records_view.setColumnWidth(2, 85)
        split.addWidget(self.records_view)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.addWidget(QLabel(self.repository.label + '信息'))
        self.info_model = RowsModel([('字段', 'field'), ('值', 'value')], self)
        self.info_view = table_view(self.info_model)
        self.info_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.info_view.setWordWrap(True)
        self.info_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.info_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.info_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.info_view.setMinimumHeight(0)
        self.info_view.setMaximumHeight(self.info_view.horizontalHeader().sizeHint().height() +
                                        len(self.repository.info_fields) * self.info_view.verticalHeader().defaultSectionSize() + 12)
        rl.addWidget(self.info_view)
        self.current_label = QLabel('选择记录以查看附件')
        self.current_label.setWordWrap(True)
        rl.addWidget(self.current_label)
        self.attachment_model = RowsModel([('页序', '备注'), ('路径', '路径')], self)
        self.attachments_view = table_view(self.attachment_model)
        self.attachments_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.attachments_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.attachments_view.setMinimumHeight(0)
        self.attachments_view.setMaximumHeight(self.attachments_view.horizontalHeader().sizeHint().height() +
                                              3 * self.attachments_view.verticalHeader().defaultSectionSize() + 12)
        rl.addWidget(self.attachments_view)
        self.preview = ImagePreview(data_root=output_service.data_root, large_view_enabled=True)
        self.preview.setMinimumHeight(90)
        rl.addWidget(self.preview, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        layout.addWidget(split, 1)
        actions = QHBoxLayout()
        self.selected_count = QLabel()
        self.clear_selection_button = QPushButton('清空本次选择')
        self.insert_title = QCheckBox('插入获奖名称' if self.is_award else '插入财务报告标题')
        self.output_button = QPushButton('插入到 Word')
        for widget in (self.selected_count, self.clear_selection_button, self.insert_title):
            actions.addWidget(widget)
        actions.addStretch()
        actions.addWidget(self.output_button)
        layout.addLayout(actions)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #ae3131')
        layout.addWidget(self.error_label)
        self.records_view.selectionModel().currentRowChanged.connect(self.record_changed)
        self.records_view.clicked.connect(lambda index: self.record_changed(index, None))
        self.attachments_view.selectionModel().currentRowChanged.connect(self.attachment_changed)
        self.model.dataChanged.connect(self.update_count)
        self.clear_selection_button.clicked.connect(self.clear_selection)
        self.output_button.clicked.connect(self.insert_to_word)
        self.info_view.viewport().installEventFilter(self)
        self.records_view.viewport().installEventFilter(self)
        self.search()

    def search(self):
        target = self.current_record_id
        self.model.set_rows(self.service.search(**{key: editor.text() for key, editor in self.filters.items()}))
        self.clear_preview()
        # Keep independent, stable ID selections across filtering and page switches.
        index = next((i for i, row in enumerate(self.model.rows) if row[self.repository.key] == target), 0)
        if self.model.rows:
            self.records_view.setCurrentIndex(self.model.index(index, 1))
            self.record_changed(self.model.index(index, 1), None)
        self.update_count()

    def clear_search(self):
        for editor in self.filters.values():
            editor.clear()
        self.search()

    def update_count(self, *_):
        self.selected_count.setText(f'已选 {len(self.selected_ids)} 项')

    def clear_selection(self):
        self.selected_ids.clear()
        if self.model.rows:
            self.model.dataChanged.emit(self.model.index(0, 0), self.model.index(len(self.model.rows) - 1, 0), [Qt.CheckStateRole])
        self.update_count()

    def clear_preview(self):
        self.current_record_id = None
        self.model.set_active_id(None)
        self.info_model.set_rows([])
        self.attachment_model.set_rows([])
        self.preview.show_path(None)
        self.current_label.setText('选择记录以查看附件')

    def record_changed(self, current, _previous):
        if current.isValid() and current.column() == 0:
            return
        row = self.model.record(current)
        if row is None:
            self.clear_preview()
            return
        self.current_record_id = row[self.repository.key]
        self.model.set_active_id(self.current_record_id)
        self.info_model.set_rows([{'field': field, 'value': '—' if row[field] in (None, '') else str(row[field]),
                                   'raw': row[field]} for field in self.repository.info_fields])
        self.info_view.resizeRowsToContents()
        self.current_label.setText('当前查看：' + self.repository.title(row))
        pages = self.repository.attachments(self.current_record_id)
        self.attachment_model.set_rows(pages)
        self.preview.show_path(None)
        if pages:
            self.attachments_view.selectRow(0)

    def attachment_changed(self, current, _previous):
        row = self.attachment_model.record(current)
        self.preview.show_path(row['路径'] if row else None)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            value = None
            if watched is self.info_view.viewport():
                index = self.info_view.indexAt(event.position().toPoint())
                row = self.info_model.record(index)
                if row and index.column() == 1:
                    value = row['raw']
            elif watched is self.records_view.viewport():
                index = self.records_view.indexAt(event.position().toPoint())
                row = self.model.record(index)
                if row and index.column() != 0:
                    value = row[self.model.columns[index.column()][1]]
            if value is not None and value != '':
                self.copy_to_clipboard(str(value))
        return super().eventFilter(watched, event)

    def insert_to_word(self):
        self.output_button.setEnabled(False)
        try:
            plan = self.output_service.insert(self.selected_ids, self.settings_service.load(),
                insert_title=self.insert_title.isChecked(),
                confirm_style_fallback=lambda missing: confirm_style_fallback(self, missing))
        except WordNotRunningError:
            self.error_label.setText('未检测到正在运行的 Microsoft Word，请先打开 Word 文档并将光标放到需要插入的位置。')
        except WordNoActiveDocumentError:
            self.error_label.setText('Microsoft Word 当前没有活动文档，请先打开目标文档。')
        except (ReportWordPreflightError, ReportWordWriteError, WordServiceError) as error:
            self.error_label.setText(str(error))
        except Exception as error:
            self.error_label.setText(f'Word 输出失败：{error}')
        else:
            self.error_label.clear()
            self.notify(f'已插入 {len(plan.blocks)} 项{self.repository.label}，共 {plan.image_count} 张附件图片')
        finally:
            self.output_button.setEnabled(True)


class ReportManagePage(QWidget):
    def __init__(self, service, *, settings_service, attachment_service, notify):
        super().__init__()
        self.service, self.repository, self.notify = service, service.repository, notify
        self.record_id, self.original = None, None
        self.mode, self.dirty, self.loading = 'view', False, False
        self.is_award = self.repository.key == '获奖ID'
        layout = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索获奖名称' if self.is_award else '搜索财务报告年度')
        self.search_button = QPushButton('搜索')
        row.addWidget(self.search_input, 1)
        row.addWidget(self.search_button)
        ll.addLayout(row)
        columns = [('获奖名称', '获奖名称'), ('年份', '获奖年份')] if self.is_award else [('财务报告年度', '财务报告年度')]
        self.model = RowsModel(columns, self)
        self.records_view = table_view(self.model)
        self.records_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        ll.addWidget(self.records_view, 1)
        self.new_button = QPushButton('新增' + self.repository.label)
        ll.addWidget(self.new_button)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        detail = QWidget()
        dl = QVBoxLayout(detail)
        self.state_label = QLabel()
        self.state_label.setObjectName('stateLabel')
        dl.addWidget(self.state_label)
        form = QFormLayout()
        self.project = None
        if self.is_award:
            self.project = StyledComboBox()
            self.project.currentIndexChanged.connect(self.mark_dirty)
            form.addRow('关联工程', self.project)
        self.inputs = {}
        for field in self.repository.fields:
            if field == '业绩ID':
                continue
            editor = QLineEdit()
            if field in ('营业收入', '净利润'):
                editor.setPlaceholderText('填写报告中的原始文字')
            editor.textChanged.connect(self.mark_dirty)
            self.inputs[field] = editor
            form.addRow(field, editor)
        dl.addLayout(form)
        actions = QHBoxLayout()
        self.edit_button, self.save_button = QPushButton('编辑'), QPushButton('保存')
        self.cancel_button, self.delete_button = QPushButton('取消'), QPushButton('删除记录')
        for button in (self.edit_button, self.save_button, self.cancel_button, self.delete_button):
            actions.addWidget(button)
        dl.addLayout(actions)
        dl.addWidget(QLabel('当前记录附件 · 一份 PDF 的全部页面'))
        self.attachments = ProjectAttachmentEditor(
            self.repository, attachment_service, settings_service, notify, describe_group=self.describe_group,
            delete_button_text='删除当前记录整份附件', group_error='请先选择已保存记录', large_view_enabled=True)
        dl.addWidget(self.attachments, 1)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #ae3131')
        dl.addWidget(self.error_label)
        scroll.setWidget(detail)
        if self.is_award:
            # Keep the editor's content requirements inside this scroll area.
            # Its viewport can shrink without advertising the content's preferred
            # size to the splitter/tab/stack. Only the content's vertical minimum
            # follows its layout; horizontal space follows the available viewport.
            scroll.setObjectName('awardDetailScroll')
            scroll.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            detail.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
            dl.setHorizontalSizeConstraint(QLayout.SetNoConstraint)
            dl.setVerticalSizeConstraint(QLayout.SetMinimumSize)
            self.project.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.project.setMinimumContentsLength(12)
        split.addWidget(left)
        split.addWidget(scroll)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 5)
        layout.addWidget(split, 1)
        self.records_view.selectionModel().currentRowChanged.connect(self.record_changed)
        self.search_input.returnPressed.connect(self.search)
        self.search_button.clicked.connect(self.search)
        self.new_button.clicked.connect(self.new_record)
        self.edit_button.clicked.connect(lambda: self.set_mode('edit'))
        self.save_button.clicked.connect(self.save_record)
        self.cancel_button.clicked.connect(self.cancel)
        self.delete_button.clicked.connect(self.delete_record)
        self.attachments.pending_changed.connect(self.pending_changed)
        self.refresh_records()

    def describe_group(self, group):
        row = self.repository.get(group[0])
        return f'{self.repository.label}“{self.repository.title(row)}”（ID {group[0]}）' if row else f'ID {group[0]}'

    def mark_dirty(self, *_):
        if not self.loading and self.mode != 'view':
            self.dirty = True

    def set_mode(self, mode):
        self.mode, self.dirty = mode, False
        self.state_label.setText({'view': '查看状态', 'edit': '编辑 · 未保存', 'new': '新增 · 未保存'}[mode])
        if self.project:
            self.project.setEnabled(mode != 'view')
        for editor in self.inputs.values():
            editor.setReadOnly(mode == 'view')
        self.save_button.setEnabled(mode != 'view')
        self.cancel_button.setEnabled(mode != 'view')
        self.edit_button.setEnabled(mode == 'view' and self.record_id is not None)
        self.delete_button.setEnabled(mode == 'view' and self.record_id is not None)
        self.new_button.setEnabled(mode == 'view')
        self.attachments.setEnabled(mode == 'view' and self.record_id is not None)

    def pending_changed(self, pending):
        for widget in (self.records_view, self.search_input, self.search_button):
            widget.setEnabled(not pending)
        self.new_button.setEnabled(not pending and self.mode == 'view')
        self.edit_button.setEnabled(not pending and self.record_id is not None)
        self.delete_button.setEnabled(not pending and self.record_id is not None)

    def can_leave(self):
        if not self.attachments.can_leave():
            return False
        return not self.dirty or QMessageBox.question(
            self, '未保存的修改', '当前资料尚未保存，确定放弃？',
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Discard

    def load(self, row):
        self.loading = True
        try:
            self.original = row
            if self.project:
                self.project.clear()
                self.project.addItem('请选择关联工程', None)
                for project in self.repository.projects():
                    self.project.addItem(f"{project['项目名称']}（ID {project['业绩ID']}）", project['业绩ID'])
                self.project.setCurrentIndex(max(0, self.project.findData(row['业绩ID'] if row else None)))
            for field, editor in self.inputs.items():
                value = row[field] if row else None
                editor.setText('' if value is None else str(value))
            self.attachments.set_group((self.record_id,) if self.record_id is not None else None)
        finally:
            self.loading = False

    def discard_changes(self):
        self.load(self.repository.get(self.record_id) if self.record_id is not None else None)
        self.set_mode('view')

    def refresh_records(self):
        target = self.record_id
        self.loading = True
        try:
            self.model.set_rows(self.service.search(**{('name' if self.is_award else 'year'): self.search_input.text()}))
            index = next((i for i, row in enumerate(self.model.rows) if row[self.repository.key] == target), 0)
            self.record_id = self.model.rows[index][self.repository.key] if self.model.rows else None
            if self.model.rows:
                self.records_view.selectRow(index)
        finally:
            self.loading = False
        self.load(self.repository.get(self.record_id) if self.record_id is not None else None)
        self.set_mode('view')

    def record_changed(self, current, _previous):
        if self.loading:
            return
        row = self.model.record(current)
        target = row[self.repository.key] if row else None
        if target == self.record_id and self.mode == 'view':
            return
        if not self.can_leave():
            self.loading = True
            index = next((i for i, value in enumerate(self.model.rows) if value[self.repository.key] == self.record_id), -1)
            self.records_view.setCurrentIndex(self.model.index(index, 0))
            self.loading = False
            return
        self.record_id = target
        self.load(self.repository.get(target) if target is not None else None)
        self.set_mode('view')

    def search(self):
        if self.can_leave():
            self.discard_changes()
            self.refresh_records()

    def new_record(self):
        if not self.can_leave():
            return
        self.record_id = None
        self.load(None)
        self.set_mode('new')
        self.inputs[self.repository.name_field].setFocus()

    def save_record(self):
        if self.mode == 'view':
            return
        try:
            values = {'业绩ID': self.project.currentData()} if self.project else {}
            for field, editor in self.inputs.items():
                value = editor.text()
                original = self.original[field] if self.original else None
                values[field] = value if value != '' or original == '' else None
            self.record_id = self.service.save(self.record_id, values)
        except Exception as error:
            self.error_label.setText(f'保存失败：{error}')
            return
        self.error_label.clear()
        self.search_input.clear()
        self.refresh_records()
        self.notify(self.repository.label + '已保存')

    def cancel(self):
        if self.can_leave():
            self.discard_changes()
            self.refresh_records()

    def delete_record(self):
        if self.record_id is None:
            return
        if QMessageBox.question(self, '确认删除记录', f'确定删除{self.describe_group((self.record_id,))}？',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.service.delete(self.record_id)
        except Exception as error:
            self.error_label.setText(str(error))
            return
        self.error_label.clear()
        self.record_id = None
        self.refresh_records()
        self.notify(self.repository.label + '已删除')


class AwardFinanceManagePage(QWidget):
    """One existing navigation area; protect edits/imports when changing tabs."""

    def __init__(self, award_page, finance_page):
        super().__init__()
        self.pages = (award_page, finance_page)
        self.active_tab = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel('获奖及财务管理')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        subtitle = QLabel('分别维护获奖证明包与年度财务报告；附件只归属当前记录。')
        subtitle.setObjectName('subtitle')
        layout.addWidget(subtitle)
        self.tabs = QTabWidget()
        self.tabs.addTab(award_page, '获奖工程')
        self.tabs.addTab(finance_page, '财务报告')
        layout.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(self.tab_changed)

    @property
    def mode(self):
        return self.pages[self.active_tab].mode

    def tab_changed(self, index):
        previous = self.pages[self.active_tab]
        if not previous.can_leave():
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(self.active_tab)
            self.tabs.blockSignals(False)
            return
        previous.discard_changes()
        self.active_tab = index
        self.pages[index].refresh_records()

    def can_leave(self):
        return all(page.can_leave() for page in self.pages)

    def discard_changes(self):
        for page in self.pages:
            page.discard_changes()

    def refresh_records(self):
        for page in self.pages:
            page.refresh_records()
