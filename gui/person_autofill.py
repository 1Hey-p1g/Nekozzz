"""Experimental personnel auto-fill; widgets edit an explicit session task."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QCheckBox, QPushButton, QSplitter, QTabWidget, QListWidgetItem, QScrollArea,
    QSizePolicy, QMessageBox,
)
from gui.common import RowsModel, table_view, CheckBoxDelegate, task_row_widget, format_person_summary
from gui.person_word import PersonOrderList
from gui.word_styles import confirm_style_fallback
from services.autofill.person_task import PersonAutoFillTask
from services.autofill.person_service import AutoFillWriteError
from services.person_word import PersonWordPreflightError
from services.word_service import WordNotRunningError, WordNoActiveDocumentError, WordServiceError


class PersonAutoFillPage(QWidget):
    def __init__(self, people_service, output_service, settings_service, notify):
        super().__init__()
        self.people_service, self.output_service = people_service, output_service
        self.settings_service, self.notify = settings_service, notify
        self.task = PersonAutoFillTask()
        self.setStyleSheet('''
            QPushButton#removePersonFromWord { border: 0; border-radius: 5px;
                background: transparent; color: #ad6c70; padding: 0; }
            QPushButton#removePersonFromWord:hover { background: #fbecee; color: #923e47; }
            QPushButton#removePersonFromWord:pressed { background: #f4dce0; color: #7d303a; }
            QListWidget#personWordTaskList::item { padding: 0; margin: 0; }
        ''')
        self.people_model = RowsModel([('姓名', '姓名')], self)
        columns = [('选择', ''), ('类型', '证书类型'), ('证书名称', '证书名称'), ('证书编号', '证书编号')]
        self.table_certificates = RowsModel(columns, self, check_key='证书ID')
        self.attachment_certificates = RowsModel(columns, self, check_key='证书ID')
        self.project_model = RowsModel([('选择', ''), ('项目名称', '项目名称'), ('历史担任角色', '担任角色')], self, check_key='ID')
        self._build()
        self.search()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        title = QLabel('自动填表（实验性） · 人员表')
        title.setObjectName('pageTitle')
        root.addWidget(title)
        description = QLabel('模板：人员表（实验模板） · 每表 3 人 · 本次角色和选择仅保存在内存，不写回资料。')
        description.setObjectName('subtitle')
        description.setWordWrap(True)
        root.addWidget(description)
        title_row = QHBoxLayout()
        self.include_title = QCheckBox('插入标题')
        self.title_text = QLineEdit()
        self.title_text.setPlaceholderText('每个表格 Block 的表前标题')
        title_row.addWidget(self.include_title)
        title_row.addWidget(self.title_text, 1)
        root.addLayout(title_row)
        note_row = QHBoxLayout()
        self.include_note = QCheckBox('插入注释')
        self.note_text = QPlainTextEdit()
        self.note_text.setPlaceholderText('每个表格 Block 的表后注释（可多行）')
        self.note_text.setMaximumHeight(self.fontMetrics().height()*3 + 24)
        note_row.addWidget(self.include_note)
        note_row.addWidget(self.note_text, 1)
        root.addLayout(note_row)
        self.shrink_table = QCheckBox('超宽表格自动缩小（只缩不放，不缩字体）')
        self.shrink_table.setChecked(True)
        root.addWidget(self.shrink_table)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        layout = QVBoxLayout(left)
        layout.setContentsMargins(0, 0, 8, 0)
        search_row = QHBoxLayout()
        self.name_filter = QLineEdit()
        self.name_filter.setPlaceholderText('搜索人员姓名，双击结果添加')
        search = QPushButton('搜索')
        search_row.addWidget(self.name_filter, 1)
        search_row.addWidget(search)
        layout.addLayout(search_row)
        self.people_view = table_view(self.people_model)
        layout.addWidget(self.people_view, 1)
        layout.addWidget(QLabel('本次人员（拖动排序，× 移除）'))
        self.task_list = PersonOrderList()
        self.task_list.setObjectName('personWordTaskList')
        layout.addWidget(self.task_list, 2)
        right = QWidget()
        detail = QVBoxLayout(right)
        self.summary = QLabel('请添加并选择人员')
        self.summary.setWordWrap(True)
        self.summary.setObjectName('detailSummary')
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail.addWidget(self.summary)
        detail.addWidget(QLabel('本次拟担任工作（不是历史业绩角色）'))
        self.role = QLineEdit()
        self.role.setPlaceholderText('默认空，表中显示 /')
        detail.addWidget(self.role)
        tabs = QTabWidget()
        self.views = []
        for model, label in ((self.table_certificates, '表格注册证书'),
                             (self.project_model, '表格人员业绩'),
                             (self.attachment_certificates, '附件证书')):
            view = table_view(model)
            view.setItemDelegateForColumn(0, CheckBoxDelegate(view))
            tabs.addTab(view, label)
            self.views.append(view)
        detail.addWidget(tabs, 1)
        hint = QLabel('三个勾选集合互相独立；性别从18位身份证派生，职称从全部职称证派生。未选附件的人员仍输出姓名。')
        hint.setWordWrap(True)
        detail.addWidget(hint)
        # Keep long summaries/details inside this region rather than raising MainWindow's minimum.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right)
        scroll.setMinimumSize(0, 0)
        scroll.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        split.addWidget(left)
        split.addWidget(scroll)
        split.setSizes([350, 650])
        root.addWidget(split, 1)
        buttons = QHBoxLayout()
        clear = QPushButton('清空任务')
        self.output_button = QPushButton('输出到 Word（实验性）')
        buttons.addWidget(clear)
        buttons.addStretch()
        buttons.addWidget(self.output_button)
        root.addLayout(buttons)
        search.clicked.connect(self.search)
        self.name_filter.returnPressed.connect(self.search)
        self.people_view.doubleClicked.connect(self.add_person)
        self.task_list.currentItemChanged.connect(lambda *_: self.show_person())
        self.task_list.order_changed.connect(self.reorder)
        self.role.textEdited.connect(self.role_changed)
        self.include_title.toggled.connect(lambda v: setattr(self.task, 'include_title', v))
        self.include_note.toggled.connect(lambda v: setattr(self.task, 'include_note', v))
        self.shrink_table.toggled.connect(lambda v: setattr(self.task, 'shrink_wide_tables', v))
        self.title_text.textChanged.connect(lambda v: setattr(self.task, 'title_text', v))
        self.note_text.textChanged.connect(lambda: setattr(self.task, 'note_text', self.note_text.toPlainText()))
        self.output_button.clicked.connect(self.output)
        clear.clicked.connect(self.clear)

    def current_id(self):
        item = self.task_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def search(self):
        self.people_model.set_rows(self.people_service.people.search(self.name_filter.text()))

    def add_person(self, index):
        record = self.people_model.record(index)
        if not record:
            return
        if not self.task.add(record['人员ID'], record['姓名']):
            self.notify('该人员已在本次输出列表中')
        self.refresh(record['人员ID'])

    def refresh(self, selected=None):
        previous = selected if selected is not None else self.current_id()
        self.task_list.blockSignals(True)
        try:
            self.task_list.clear()
            for number, entry in enumerate(self.task.people, 1):
                item = QListWidgetItem()
                item.setData(Qt.UserRole, entry.person_id)
                self.task_list.addItem(item)
                widget, size = task_row_widget(self.task_list, f'{number}  {entry.display_name}',
                    lambda _checked=False, i=entry.person_id: self.remove_person(i),
                    tooltip='移除此人员', button_name='removePersonFromWord', constrain_name=True)
                item.setSizeHint(size)
                self.task_list.setItemWidget(item, widget)
            row = next((i for i, p in enumerate(self.task.people) if p.person_id == previous), 0)
            if self.task.people:
                self.task_list.setCurrentRow(row)
        finally:
            self.task_list.blockSignals(False)
        self.show_person()

    def remove_person(self, person_id):
        current = self.current_id()
        index = next(i for i, p in enumerate(self.task.people) if p.person_id == person_id)
        self.task.remove(person_id)
        if current == person_id:
            current = self.task.people[min(index, len(self.task.people)-1)].person_id if self.task.people else None
        self.refresh(current)

    def reorder(self):
        current = self.current_id()
        self.task.reorder(self.task_list.person_ids())
        self.refresh(current)

    def show_person(self):
        entry = self.task.item(self.current_id())
        self.role.setEnabled(entry is not None)
        self.role.setText(entry.role_text if entry else '')
        if entry is None:
            self.summary.setText('请添加并选择人员')
            for model in (self.table_certificates, self.project_model, self.attachment_certificates):
                model.checked = set()
                model.set_rows([])
            return
        record = self.people_service.people.get(entry.person_id)
        self.summary.setText(format_person_summary(record) if record else '人员资料已不存在')
        certificates = self.output_service.certificates(entry.person_id)
        self.table_certificates.checked = entry.table_certificate_ids
        self.attachment_certificates.checked = entry.attachment_certificate_ids
        self.project_model.checked = entry.table_project_ids
        self.table_certificates.set_rows(certificates)
        self.attachment_certificates.set_rows(certificates)
        self.project_model.set_rows(self.output_service.projects(entry.person_id))

    def role_changed(self, text):
        entry = self.task.item(self.current_id())
        if entry:
            entry.role_text = text

    def clear(self):
        self.task.people.clear()
        self.refresh()

    def output(self):
        self.output_button.setEnabled(False)
        try:
            plan = self.output_service.insert(self.task, self.settings_service.load(),
                confirm_style_fallback=lambda missing: confirm_style_fallback(self, missing))
            self.notify(f'已输出 {len(self.task.people)} 人，{len(plan.blocks)} 张表，{plan.image_count} 张附件图片')
        except WordNotRunningError:
            QMessageBox.warning(self, 'Word 未运行', '请先打开 Microsoft Word 文档并放置光标。')
        except WordNoActiveDocumentError:
            QMessageBox.warning(self, '没有活动文档', 'Microsoft Word 当前没有活动文档。')
        except (ValueError, OSError, PersonWordPreflightError, AutoFillWriteError, WordServiceError) as error:
            QMessageBox.warning(self, '自动填表未完成', str(error))
        finally:
            self.output_button.setEnabled(True)
