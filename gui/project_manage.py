"""Engineering maintenance with atomic leader relations and scoped PDF groups."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from gui.common import RowsModel, StyledComboBox, table_view
from gui.project_attachments import ProjectAttachmentEditor
from gui.project_personnel import ProjectPersonnelEditor
from repositories.project_repository import PROJECT_FIELDS
from services.projects import amount_text, ProjectPersonnelEntry


class ProjectManagePage(QWidget):
    def __init__(self, service, *, settings_service, attachment_service, notify):
        super().__init__()
        self.service, self.notify = service, notify
        self.project_id = None
        self.original = None
        self.mode, self.dirty, self.loading = 'view', False, False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel('工程业绩管理')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        subtitle = QLabel('维护工程资料、项目管理人员及按文件类型分组的附件。金额单位：元。')
        subtitle.setObjectName('subtitle')
        layout.addWidget(subtitle)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索工程名称')
        ll.addWidget(self.search_input)
        self.model = RowsModel([('工程名称', '项目名称')], self)
        self.projects_view = table_view(self.model)
        self.projects_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        ll.addWidget(self.projects_view, 1)
        self.new_button = QPushButton('新建工程')
        ll.addWidget(self.new_button)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        detail = QWidget()
        dl = QVBoxLayout(detail)
        dl.setSpacing(10)
        self.state_label = QLabel('查看状态')
        self.state_label.setObjectName('stateLabel')
        dl.addWidget(self.state_label)
        self.form_widget = QWidget()
        form = QGridLayout(self.form_widget)
        form.setContentsMargins(0, 0, 0, 0)
        self.inputs = {}
        for number, field in enumerate(PROJECT_FIELDS):
            label = '合同金额（元）' if field == '合同金额_scaled' else field
            editor = QTextEdit() if field == '项目主要内容' else QLineEdit()
            if isinstance(editor, QTextEdit):
                editor.setMinimumHeight(editor.fontMetrics().lineSpacing() * 4)
                editor.setMaximumHeight(editor.fontMetrics().lineSpacing() * 7)
            elif field in ('开工时间', '竣工时间'):
                editor.setPlaceholderText('YYYY-MM-DD；留空为未填写')
            editor.textChanged.connect(self.mark_dirty)
            self.inputs[field] = editor
            form.addWidget(QLabel(label), number, 0)
            form.addWidget(editor, number, 1)
        dl.addWidget(self.form_widget)
        self.personnel = ProjectPersonnelEditor()
        self.personnel.changed.connect(self.mark_dirty)
        dl.addWidget(self.personnel, 1)
        actions = QHBoxLayout()
        self.edit_button, self.save_button = QPushButton('编辑工程'), QPushButton('保存工程')
        self.cancel_button, self.delete_button = QPushButton('取消'), QPushButton('删除工程')
        for button in (self.edit_button, self.save_button, self.cancel_button, self.delete_button):
            actions.addWidget(button)
        dl.addLayout(actions)
        dl.addWidget(QLabel('工程附件 · 当前工程 + 文件类型'))
        self.file_type = StyledComboBox()
        self.file_type.setEditable(True)
        self.file_type.setInsertPolicy(StyledComboBox.NoInsert)
        self.file_type.setPlaceholderText('选择已有类型，或输入新类型')
        dl.addWidget(self.file_type)
        self.attachments = ProjectAttachmentEditor(service.projects, attachment_service, settings_service, notify)
        dl.addWidget(self.attachments)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #ae3131')
        dl.addWidget(self.error_label)
        scroll.setWidget(detail)
        split.addWidget(left)
        split.addWidget(scroll)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 5)
        layout.addWidget(split, 1)
        self.projects_view.selectionModel().currentRowChanged.connect(self.project_changed)
        self.search_input.returnPressed.connect(self.search)
        self.new_button.clicked.connect(self.new_project)
        self.edit_button.clicked.connect(lambda: self.set_mode('edit'))
        self.save_button.clicked.connect(self.save_project)
        self.cancel_button.clicked.connect(self.cancel)
        self.delete_button.clicked.connect(self.delete_project)
        self.file_type.currentTextChanged.connect(self.type_changed)
        self.attachments.saved.connect(self.refresh_types)
        self.attachments.pending_changed.connect(self.pending_changed)
        self.refresh_projects()

    def pending_changed(self, pending):
        self.projects_view.setEnabled(not pending)
        self.search_input.setEnabled(not pending)
        self.file_type.setEnabled(not pending)
        self.new_button.setEnabled(not pending)
        self.edit_button.setEnabled(not pending and self.project_id is not None)
        self.delete_button.setEnabled(not pending and self.project_id is not None)

    def mark_dirty(self, *_):
        if not self.loading and self.mode != 'view':
            self.dirty = True

    def set_mode(self, mode):
        self.mode, self.dirty = mode, False
        self.state_label.setText({'view': '查看状态', 'edit': '编辑工程 · 未保存', 'new': '新建工程 · 未保存'}[mode])
        for editor in self.inputs.values():
            editor.setReadOnly(mode == 'view')
        self.personnel.set_read_only(mode == 'view')
        self.save_button.setEnabled(mode != 'view')
        self.cancel_button.setEnabled(mode != 'view')
        self.edit_button.setEnabled(mode == 'view' and self.project_id is not None)
        self.delete_button.setEnabled(mode == 'view' and self.project_id is not None)
        self.new_button.setEnabled(mode == 'view')
        self.file_type.setEnabled(mode == 'view' and self.project_id is not None)
        self.attachments.setEnabled(mode == 'view' and self.project_id is not None)

    def can_leave(self):
        if not self.attachments.can_leave():
            return False
        return not self.dirty or QMessageBox.question(
            self, '未保存的修改', '当前修改尚未保存，确定放弃？', QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel) == QMessageBox.Discard

    def discard_changes(self):
        self.load(self.service.projects.get(self.project_id) if self.project_id else None)
        self.set_mode('view')

    def load(self, row):
        self.loading = True
        self.original = row
        for field, editor in self.inputs.items():
            value = None if row is None else row[field]
            text = amount_text(value) if field == '合同金额_scaled' else ('' if value is None else str(value))
            editor.setPlainText(text) if isinstance(editor, QTextEdit) else editor.setText(text)
        relations = self.service.projects.project_personnel(row['业绩ID']) if row else []
        self.personnel.reset(self.service.people.search(), [
            ProjectPersonnelEntry(r['relation_id'], r['person_id'], r['role']) for r in relations])
        self.loading = False
        self.refresh_types()

    def refresh_projects(self, select_id=None):
        target = self.project_id if select_id is None else select_id
        self.loading = True
        self.model.set_rows(self.service.projects.search(self.search_input.text()))
        self.loading = False
        row = next((i for i, value in enumerate(self.model.rows) if value['业绩ID'] == target), 0)
        if self.model.rows:
            self.projects_view.selectRow(row)
            self.project_changed(self.model.index(row, 0), None)
            if self.mode == 'view':
                self.load(self.service.projects.get(self.project_id))
        else:
            self.project_id = None
            self.load(None)
            self.set_mode('view')

    def project_changed(self, current, _previous):
        if self.loading:
            return
        row = self.model.record(current)
        target = row['业绩ID'] if row else None
        if target == self.project_id and self.mode == 'view':
            return
        if not self.can_leave():
            self.loading = True
            previous = next((i for i, value in enumerate(self.model.rows) if value['业绩ID'] == self.project_id), -1)
            self.projects_view.setCurrentIndex(self.model.index(previous, 0))
            self.loading = False
            return
        self.project_id = target
        self.load(self.service.projects.get(target) if target is not None else None)
        self.set_mode('view')

    def search(self):
        if self.can_leave():
            self.discard_changes()
            self.refresh_projects()

    def new_project(self):
        if not self.can_leave():
            return
        self.project_id = None
        self.load(None)
        self.set_mode('new')
        self.inputs['项目名称'].setFocus()

    def save_project(self):
        if self.mode == 'view':
            return
        try:
            values = {}
            for field, editor in self.inputs.items():
                value = editor.toPlainText() if isinstance(editor, QTextEdit) else editor.text()
                old = self.original[field] if self.original else None
                values['合同金额' if field == '合同金额_scaled' else field] = value if value != '' or old == '' else None
            self.project_id = self.service.save(self.project_id, values, personnel=self.personnel.entries)
        except Exception as error:
            self.error_label.setText(f'保存失败：{error}')
            return
        self.error_label.clear()
        self.search_input.clear()
        self.load(self.service.projects.get(self.project_id))
        self.set_mode('view')
        self.refresh_projects()
        self.notify('工程资料已保存')

    def cancel(self):
        if self.can_leave():
            self.discard_changes()
            self.refresh_projects()

    def delete_project(self):
        if self.project_id is None:
            return
        if QMessageBox.question(self, '确认删除工程', f"确定删除工程“{self.original['项目名称']}”？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.service.delete(self.project_id)
        except Exception as error:
            self.error_label.setText(str(error))
            return
        self.project_id = None
        self.refresh_projects()

    def refresh_types(self):
        previous = self.file_type.currentText()
        values = self.service.projects.list_attachment_types()
        actual = [row['文件类型'] for row in self.service.projects.attachment_types(self.project_id)] if self.project_id else []
        blocked = self.file_type.blockSignals(True)
        self.file_type.clear()
        self.file_type.addItems(sorted(set(values + actual)))
        self.file_type.setCurrentText(previous if previous else actual[0] if actual else '')
        self.file_type.blockSignals(blocked)
        self.type_changed()

    def type_changed(self, *_):
        raw = self.file_type.currentText()
        actual = {row['文件类型'] for row in self.service.projects.attachment_types(self.project_id)} if self.project_id else set()
        value = raw if raw in actual else raw.strip()
        self.attachments.set_group((self.project_id, value) if self.project_id is not None and value.strip() else None)
