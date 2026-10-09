"""Company fields shared by qualification viewing and maintenance pages."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)
from gui.common import StyledComboBox
from repositories.qualification_repository import COMPANY_FIELDS


class CompanyInfoView(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel('公司基本信息'))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setMinimumHeight(90)
        self.scroll.setMaximumHeight(210)
        body = QWidget()
        grid = QGridLayout(body)
        self.inputs = {}
        display_fields = ('公司名称', '统一社会信用代码') + tuple(
            field for field in COMPANY_FIELDS if field not in ('公司名称', '统一社会信用代码'))
        for index, field in enumerate(display_fields):
            editor = QLineEdit()
            editor.setReadOnly(True)
            editor.setPlaceholderText('未填写')
            editor.setObjectName('company_' + field)
            self.inputs[field] = editor
            row, column = divmod(index, 2)
            grid.addWidget(QLabel(field), row, column * 2)
            grid.addWidget(editor, row, column * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self.scroll.setWidget(body)
        layout.addWidget(self.scroll)

    def display(self, record):
        for field, editor in self.inputs.items():
            value = record.get(field) if record else None
            editor.setText('' if value is None else str(value))
            editor.setCursorPosition(0)
            editor.setToolTip(editor.text())


class CompanyInfoEditor(CompanyInfoView):
    editing_changed = Signal(bool)
    def __init__(self, service, notify, saved):
        super().__init__()
        self.service, self.notify, self.saved = service, notify, saved
        self.company_id = None
        self.original = None
        self.editing = self.dirty = self.loading = False
        self.selector = StyledComboBox()
        self.layout().insertWidget(1, self.selector)
        actions = QHBoxLayout()
        self.new_button = QPushButton('新增公司')
        self.edit_button = QPushButton('编辑公司')
        self.save_button = QPushButton('保存公司')
        self.cancel_button = QPushButton('取消公司修改')
        for button in (self.new_button, self.edit_button, self.save_button, self.cancel_button):
            actions.addWidget(button)
        self.layout().addLayout(actions)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.layout().addWidget(self.error)
        self.selector.currentIndexChanged.connect(self.selected)
        for editor in self.inputs.values():
            editor.textChanged.connect(self.changed)
        self.inputs['成立日期'].setPlaceholderText('YYYY-MM-DD；留空为未填写')
        self.new_button.clicked.connect(self.new)
        self.edit_button.clicked.connect(lambda: self.set_editing(True))
        self.save_button.clicked.connect(self.save)
        self.cancel_button.clicked.connect(self.cancel)
        self.reload()

    def set_editing(self, enabled):
        self.editing, self.dirty = enabled, False
        for editor in self.inputs.values():
            editor.setReadOnly(not enabled)
        self.selector.setEnabled(not enabled)
        self.new_button.setEnabled(not enabled)
        self.edit_button.setEnabled(not enabled and self.original is not None)
        self.save_button.setEnabled(enabled)
        self.cancel_button.setEnabled(enabled)
        self.editing_changed.emit(enabled)

    def changed(self, *_):
        if self.editing and not self.loading:
            self.dirty = True

    def reload(self, company_id=None):
        self.loading = True
        self.display(None)
        self.original = None
        try:
            rows = self.service.qualifications.companies()
            target = self.company_id if company_id is None else company_id
            self.selector.clear()
            for row in rows:
                self.selector.addItem(f"{row['公司名称']}（ID {row['公司ID']}）", row['公司ID'])
            index = self.selector.findData(target)
            self.selector.setCurrentIndex(index if index >= 0 else (0 if rows else -1))
            self.company_id = self.selector.currentData()
            self.original = self.service.qualifications.company_info(self.company_id) if self.company_id is not None else None
            self.display(self.original)
            self.error.clear()
        except Exception as error:
            self.company_id = None
            self.selector.clear()
            self.error.setText(f'公司信息加载失败：{error}')
        finally:
            self.loading = False
            self.set_editing(False)

    def selected(self, *_):
        if not self.loading:
            self.company_id = self.selector.currentData()
            self.reload(self.company_id)

    def new(self):
        self.company_id = None
        self.original = None
        self.display(None)
        self.error.clear()
        self.set_editing(True)
        self.inputs['公司名称'].setFocus()

    def save(self):
        if not self.editing:
            return
        values = {}
        for field, editor in self.inputs.items():
            value = editor.text()
            prior = self.original.get(field) if self.original else None
            values[field] = value if value != '' or prior == '' else None
        try:
            target = self.service.save_company(self.company_id, values)
        except Exception as error:
            self.error.setText(f'公司信息保存失败：{error}')
            return
        self.company_id = target
        self.reload(target)
        self.saved()
        self.notify('公司基本信息已保存')

    def cancel(self):
        self.reload(self.company_id)

    def can_leave(self):
        return not self.dirty or QMessageBox.question(
            self, '未保存的公司信息', '公司基本信息修改尚未保存，确定放弃？',
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Discard
