"""Company qualification maintenance with an inline, shared PDF editor."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from gui.common import RowsModel, StyledComboBox, table_view
from gui.project_attachments import ProjectAttachmentEditor
from repositories.qualification_repository import QUALIFICATION_FIELDS
from services.people import expiry_status


class QualificationManagePage(QWidget):
    def __init__(self, service, *, settings_service, attachment_service, notify):
        super().__init__()
        self.service, self.notify = service, notify
        self.qualification_id = None
        self.original = None
        self.mode, self.dirty, self.loading = 'view', False, False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel('公司资质管理')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        subtitle = QLabel('维护所属公司、资质证书及整份 PDF 附件。')
        subtitle.setObjectName('subtitle')
        layout.addWidget(subtitle)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索资质证书名称')
        search_button = QPushButton('搜索')
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(search_button)
        ll.addLayout(search_row)
        self.model = RowsModel([('证书名称', '资质证书名称')], self)
        self.qualifications_view = table_view(self.model)
        self.qualifications_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        ll.addWidget(self.qualifications_view, 1)
        self.new_button = QPushButton('新增公司资质')
        ll.addWidget(self.new_button)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        detail = QWidget()
        dl = QVBoxLayout(detail)
        self.state_label = QLabel('查看状态')
        self.state_label.setObjectName('stateLabel')
        dl.addWidget(self.state_label)
        form = QFormLayout()
        self.company = StyledComboBox()
        self.company.currentIndexChanged.connect(self.mark_dirty)
        form.addRow('所属公司', self.company)
        self.inputs = {}
        for field in QUALIFICATION_FIELDS[1:]:
            editor = QLineEdit()
            if field in ('发证日期', '有效期'):
                editor.setPlaceholderText('YYYY-MM-DD；留空为未填写' if field == '发证日期' else
                                          'YYYY-MM-DD；留空表示长期有效')
            editor.textChanged.connect(self.mark_dirty)
            self.inputs[field] = editor
            form.addRow(field, editor)
        self.expiry_label = QLabel()
        form.addRow('有效期状态', self.expiry_label)
        dl.addLayout(form)
        actions = QHBoxLayout()
        self.edit_button, self.save_button = QPushButton('编辑资质'), QPushButton('保存资质')
        self.cancel_button, self.delete_button = QPushButton('取消'), QPushButton('删除资质')
        for button in (self.edit_button, self.save_button, self.cancel_button, self.delete_button):
            actions.addWidget(button)
        dl.addLayout(actions)
        dl.addWidget(QLabel('当前资质附件 · 一份 PDF 的全部页面'))
        self.attachments = ProjectAttachmentEditor(
            service.qualifications, attachment_service, settings_service, notify,
            describe_group=self.describe_group, delete_button_text='删除当前资质整份附件',
            group_error='请先选择已保存的公司资质')
        dl.addWidget(self.attachments, 1)
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
        self.qualifications_view.selectionModel().currentRowChanged.connect(self.qualification_changed)
        self.search_input.returnPressed.connect(self.search)
        search_button.clicked.connect(self.search)
        self.new_button.clicked.connect(self.new_qualification)
        self.edit_button.clicked.connect(lambda: self.set_mode('edit'))
        self.save_button.clicked.connect(self.save_qualification)
        self.cancel_button.clicked.connect(self.cancel)
        self.delete_button.clicked.connect(self.delete_qualification)
        self.attachments.pending_changed.connect(self.pending_changed)
        self.refresh_qualifications()

    def describe_group(self, group):
        row = self.service.qualifications.get(group[0])
        return f"公司资质“{row['资质证书名称']}”（ID {group[0]}）" if row else f'公司资质 ID {group[0]}'

    def mark_dirty(self, *_):
        if not self.loading and self.mode != 'view':
            self.dirty = True

    def set_mode(self, mode):
        self.mode, self.dirty = mode, False
        self.state_label.setText({'view': '查看状态', 'edit': '编辑资质 · 未保存', 'new': '新增资质 · 未保存'}[mode])
        self.company.setEnabled(mode != 'view')
        for editor in self.inputs.values():
            editor.setReadOnly(mode == 'view')
        self.save_button.setEnabled(mode != 'view')
        self.cancel_button.setEnabled(mode != 'view')
        self.edit_button.setEnabled(mode == 'view' and self.qualification_id is not None)
        self.delete_button.setEnabled(mode == 'view' and self.qualification_id is not None)
        self.new_button.setEnabled(mode == 'view')
        self.attachments.setEnabled(mode == 'view' and self.qualification_id is not None)

    def pending_changed(self, pending):
        self.qualifications_view.setEnabled(not pending)
        self.search_input.setEnabled(not pending)
        self.new_button.setEnabled(not pending and self.mode == 'view')
        self.edit_button.setEnabled(not pending and self.qualification_id is not None)
        self.delete_button.setEnabled(not pending and self.qualification_id is not None)

    def can_leave(self):
        if not self.attachments.can_leave():
            return False
        return not self.dirty or QMessageBox.question(
            self, '未保存的修改', '当前资质修改尚未保存，确定放弃？',
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Discard

    def load(self, row):
        self.loading = True
        try:
            self.original = row
            self.company.clear()
            self.company.addItem('请选择所属公司', None)
            for company in self.service.qualifications.companies():
                self.company.addItem(f"{company['公司名称']}（ID {company['公司ID']}）", company['公司ID'])
            target = row['公司ID'] if row else None
            self.company.setCurrentIndex(max(0, self.company.findData(target)))
            for field, editor in self.inputs.items():
                value = row[field] if row else None
                editor.setText('' if value is None else str(value))
            self.expiry_label.setText(expiry_status(row['有效期']) if row else '—')
            self.attachments.set_group((self.qualification_id,) if self.qualification_id is not None else None)
        finally:
            self.loading = False

    def discard_changes(self):
        self.load(self.service.qualifications.get(self.qualification_id) if self.qualification_id is not None else None)
        self.set_mode('view')

    def refresh_qualifications(self, select_id=None):
        target = self.qualification_id if select_id is None else select_id
        self.loading = True
        try:
            self.model.set_rows(self.service.qualifications.search(self.search_input.text()))
            index = next((i for i, row in enumerate(self.model.rows) if row['资质ID'] == target), 0)
            if self.model.rows:
                self.qualifications_view.selectRow(index)
                self.qualification_id = self.model.rows[index]['资质ID']
            else:
                self.qualification_id = None
        finally:
            self.loading = False
        self.load(self.service.qualifications.get(self.qualification_id) if self.qualification_id is not None else None)
        self.set_mode('view')

    def qualification_changed(self, current, _previous):
        if self.loading:
            return
        row = self.model.record(current)
        target = row['资质ID'] if row else None
        if target == self.qualification_id and self.mode == 'view':
            return
        if not self.can_leave():
            self.loading = True
            index = next((i for i, value in enumerate(self.model.rows) if value['资质ID'] == self.qualification_id), -1)
            self.qualifications_view.setCurrentIndex(self.model.index(index, 0))
            self.loading = False
            return
        self.qualification_id = target
        self.load(self.service.qualifications.get(target) if target is not None else None)
        self.set_mode('view')

    def search(self):
        if self.can_leave():
            self.discard_changes()
            self.refresh_qualifications()

    def new_qualification(self):
        if not self.can_leave():
            return
        self.qualification_id = None
        self.load(None)
        self.set_mode('new')
        self.inputs['资质证书名称'].setFocus()

    def save_qualification(self):
        if self.mode == 'view':
            return
        try:
            values = {'公司ID': self.company.currentData()}
            for field, editor in self.inputs.items():
                value = editor.text()
                original = self.original[field] if self.original else None
                values[field] = value if value != '' or original == '' else None
            self.qualification_id = self.service.save(self.qualification_id, values)
        except Exception as error:
            self.error_label.setText(f'保存失败：{error}')
            return
        self.error_label.clear()
        self.search_input.clear()
        self.refresh_qualifications()
        self.notify('公司资质已保存')

    def cancel(self):
        if self.can_leave():
            self.discard_changes()
            self.refresh_qualifications()

    def delete_qualification(self):
        if self.qualification_id is None:
            return
        if QMessageBox.question(self, '确认删除资质', f"确定删除{self.describe_group((self.qualification_id,))}？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.service.delete(self.qualification_id)
        except Exception as error:
            self.error_label.setText(str(error))
            return
        self.qualification_id = None
        self.refresh_qualifications()
