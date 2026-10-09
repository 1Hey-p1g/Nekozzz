from gui.word_styles import confirm_style_fallback
"""Multi-person Word task inside the existing person business workspace."""

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from gui.common import (
    CertificateTextDelegate, CheckBoxDelegate, ImagePreview, RowsModel, TaskRowsModel,
    format_person_summary, table_view, task_row_widget,
)
from services.person_word import PersonWordJob, PersonWordPreflightError, PersonWordWriteError
from services.word_service import WordNoActiveDocumentError, WordNotRunningError, WordServiceError
from services.office_writer import writer_error_message


class PersonOrderList(QListWidget):
    order_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def person_ids(self):
        return [self.item(index).data(Qt.UserRole) for index in range(self.count())]

    def dropEvent(self, event):
        before = self.person_ids()
        super().dropEvent(event)
        if self.person_ids() != before:
            self.order_changed.emit()


class PersonWordPage(QWidget):
    def __init__(self, service, output_service, settings_service, notify, copy_to_clipboard=None):
        super().__init__()
        self.service = service
        self.output_service = output_service
        self.settings_service = settings_service
        self.notify = notify
        self.copy_to_clipboard = copy_to_clipboard or QGuiApplication.clipboard().setText
        self.job = PersonWordJob()
        self.viewed_person_id = None
        self.people_model = RowsModel([("姓名", "姓名")], self)
        self.certificate_model = TaskRowsModel(
            [("选择", ""), ("证书类型", "证书类型"), ("证书名称", "证书名称"),
             ("证书编号", "证书编号")], self, check_key="证书ID",
        )
        self._build()
        self.search_people()
        QTimer.singleShot(0, self._fit_certificate_rows)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(12)
        title = QLabel("多人资料输出")
        title.setObjectName("pageTitle")
        title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        root.addWidget(title)
        subtitle = QLabel("按输出顺序添加人员，为每个人分别勾选证书；本次选择仅保存在内存中。")
        subtitle.setObjectName("subtitle")
        root.addWidget(subtitle)

        finder = QHBoxLayout()
        self.name_filter = QLineEdit()
        self.name_filter.setPlaceholderText("搜索人员姓名")
        search = QPushButton("搜索")
        finder.addWidget(self.name_filter, 1)
        finder.addWidget(search)
        root.addLayout(finder)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.addWidget(QLabel("搜索结果 · 单击查看，双击加入输出序列"))
        self.people_view = table_view(self.people_model)
        self.people_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        left_layout.addWidget(self.people_view, 2)
        left_layout.addWidget(QLabel("本次输出人员（拖动调整顺序）"))
        self.task_list = PersonOrderList()
        self.task_list.setObjectName("personWordTaskList")
        left_layout.addWidget(self.task_list, 2)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(QLabel("人员信息"))
        self.person_info = QLabel("请从左侧选择人员查看")
        self.person_info.setObjectName("detailSummary")
        self.person_info.setWordWrap(True)
        self.person_info.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.person_info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        right_layout.addWidget(self.person_info)
        self.current_person = QLabel("请从左侧选择人员查看")
        self.current_person.setObjectName("settingName")
        right_layout.addWidget(self.current_person)
        right_layout.addWidget(QLabel("该人员的证书（仅勾选列改变输出选择）"))
        self.certificates_view = table_view(self.certificate_model)
        self.certificates_view.setStyleSheet(
            "QTableView::item:selected { background: white; color: #1e293b; }"
        )
        self.certificates_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.certificates_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.certificates_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.certificates_view.setAlternatingRowColors(False)
        self.certificates_view.setItemDelegate(CertificateTextDelegate(self.certificates_view))
        self.certificates_view.setItemDelegateForColumn(0, CheckBoxDelegate(self.certificates_view))
        self.certificates_view.setColumnWidth(0, 58)
        self.certificates_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.certificates_view.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)
        right_layout.addWidget(self.certificates_view)
        self.viewing_certificate = QLabel("选择证书以查看当前项")
        right_layout.addWidget(self.viewing_certificate)
        right_layout.addWidget(QLabel("当前证书的附件"))
        self.attachment_model = RowsModel([("页序", "备注"), ("路径", "路径")], self)
        self.attachments_view = table_view(self.attachment_model)
        self.attachments_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_layout.addWidget(self.attachments_view)
        self.preview = ImagePreview(data_root=self.output_service.data_root, large_view_enabled=True)
        self.preview.setMinimumHeight(90)
        right_layout.addWidget(self.preview, 1)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        root.addWidget(split, 1)

        bottom = QHBoxLayout()
        self.insert_name = QCheckBox("插入人员姓名")
        bottom.addWidget(self.insert_name)
        bottom.addStretch()
        self.output_button = QPushButton("插入资料")
        self.output_button.setObjectName("personWordInsert")
        bottom.addWidget(self.output_button)
        root.addLayout(bottom)
        self.error_label = QLabel("")
        self.error_label.setObjectName("settingsError")
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)
        self.setStyleSheet("""
            QListWidget#personWordTaskList { background: white; border: 1px solid #d1dbe7;
                border-radius: 6px; padding: 5px; color: #23405d; }
            QListWidget#personWordTaskList::item { background: #f1f5f9; border-radius: 4px; }
            QListWidget#personWordTaskList::item:selected { background: #dceafa; color: #23405d; }
            QPushButton#removePersonFromWord { border: 0; border-radius: 5px;
                background: transparent; color: #ad6c70; padding: 0; }
            QPushButton#removePersonFromWord:hover { background: #fbecee; color: #923e47; }
            QPushButton#removePersonFromWord:pressed { background: #f4dce0; color: #7d303a; }
            QLabel#settingsError { color: #ae3131; }
            QPushButton#personWordInsert { background: #345a8d; color: white; font-weight: 600; }
            QPushButton#personWordInsert:hover { background: #426da4; }
        """)

        search.clicked.connect(self.search_people)
        self.name_filter.returnPressed.connect(self.search_people)
        self.people_view.doubleClicked.connect(self.add_person)
        self.people_view.clicked.connect(self.view_search_person)
        self.people_view.selectionModel().currentRowChanged.connect(self.view_search_person)
        self.task_list.currentItemChanged.connect(self._person_changed)
        self.task_list.itemClicked.connect(lambda item: self._person_changed(item, None))
        self.task_list.order_changed.connect(self._order_changed)
        self.certificates_view.selectionModel().currentRowChanged.connect(self._certificate_changed)
        self.certificates_view.viewport().installEventFilter(self)
        self.attachments_view.selectionModel().currentRowChanged.connect(self._attachment_changed)
        self.insert_name.toggled.connect(lambda checked: setattr(self.job, "insert_person_name", checked))
        self.output_button.clicked.connect(self.insert_to_word)

    def _fit_certificate_rows(self):
        view = self.certificates_view
        height = (view.horizontalHeader().height() +
                  5 * view.verticalHeader().defaultSectionSize() + 2 * view.frameWidth())
        view.setFixedHeight(height)
        attachments = self.attachments_view
        attachment_height = (attachments.horizontalHeader().height() +
                             2 * attachments.verticalHeader().defaultSectionSize() +
                             2 * attachments.frameWidth())
        attachments.setFixedHeight(attachment_height)

    def search_people(self):
        rows = self.service.people.search(self.name_filter.text())
        self.people_model.set_rows(rows)
        self.view_person(self.viewed_person_id)

    def add_person(self, index=None):
        person = self.people_model.record(index if index is not None else self.people_view.currentIndex())
        if person is None:
            return
        person_id = person["人员ID"]
        if not self.job.add(person_id):
            self.view_person(person_id)
            self._select_person(person_id)
            self.notify("该人员已在本次输出列表中")
            return
        self.viewed_person_id = person_id
        self._refresh_task_list(select_id=person_id)
        self.error_label.clear()

    def remove_person(self, person_id):
        index = next((i for i, item in enumerate(self.job.persons) if item.person_id == person_id), None)
        if index is None:
            return
        current_id = self._current_person_id()
        successor = (current_id if current_id != person_id else
                     self.job.persons[index + 1].person_id if index + 1 < len(self.job.persons) else
                     self.job.persons[index - 1].person_id if index > 0 else None)
        self.job.remove(person_id)
        self._refresh_task_list(select_id=successor)
        self.error_label.clear()

    def _current_person_id(self):
        item = self.task_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _select_person(self, person_id):
        for index in range(self.task_list.count()):
            if self.task_list.item(index).data(Qt.UserRole) == person_id:
                self.task_list.setCurrentRow(index)
                return

    def _refresh_task_list(self, *, select_id=None):
        previous = select_id if select_id is not None else self._current_person_id()
        blocked = self.task_list.blockSignals(True)
        try:
            self.task_list.clear()
            for index, person in enumerate(self.job.persons, 1):
                record = self.service.people.get(person.person_id)
                name = record["姓名"] if record else f"已删除人员 ID {person.person_id}"
                row = QListWidgetItem()
                row.setData(Qt.UserRole, person.person_id)
                self.task_list.addItem(row)
                row_widget, size = task_row_widget(
                    self.task_list, f"{index}  {name}",
                    lambda _checked=False, pid=person.person_id: self.remove_person(pid),
                    tooltip="移除此人员", button_name="removePersonFromWord",
                )
                row.setSizeHint(size)
                self.task_list.setItemWidget(row, row_widget)
            selected = next((index for index, item in enumerate(self.job.persons)
                             if item.person_id == previous), 0)
            if self.job.persons:
                self.task_list.setCurrentRow(selected)
        finally:
            self.task_list.blockSignals(blocked)
        self.view_person(self.viewed_person_id)

    def _order_changed(self):
        current = self._current_person_id()
        self.job.reorder(self.task_list.person_ids())
        self._refresh_task_list(select_id=current)

    def _person_changed(self, current, _previous):
        if current is not None:
            self.view_person(current.data(Qt.UserRole))

    def view_search_person(self, index, _previous=None):
        record = self.people_model.record(index)
        if record is not None and record['人员ID'] != self.viewed_person_id:
            self.view_person(record['人员ID'])

    def view_person(self, person_id):
        record = self.service.people.get(person_id) if person_id is not None else None
        if record is None:
            person_id = None
        self.viewed_person_id = person_id
        item = self.job.item(person_id)
        self.certificate_model.checks_enabled = item is not None
        self.certificates_view.setToolTip('勾选用于本次输出' if item else '双击搜索结果加入输出序列后可勾选证书')
        if record is None:
            self.person_info.setText("请从左侧选择人员查看")
            self.current_person.setText("请从左侧选择人员查看")
            self.certificate_model.checked = set()
            self.certificate_model.set_active_id(None)
            self.certificate_model.set_rows([])
            self.viewing_certificate.setText("选择证书以查看当前项")
            self.attachment_model.set_rows([])
            self.preview.show_path(None)
            return
        self.person_info.setText(format_person_summary(record) if record else "人员资料已不存在")
        self.current_person.setText(f"当前人员：{record['姓名'] if record else person_id}")
        self.certificate_model.checked = item.selected_certificate_ids if item else set()
        self.certificate_model.set_active_id(None)
        rows = self.service.certificates.for_person(person_id)
        self.certificate_model.set_rows(rows)
        self.viewing_certificate.setText("选择证书以查看当前项")
        self.attachment_model.set_rows([])
        self.preview.show_path(None)
        if rows:
            self.certificates_view.setCurrentIndex(self.certificate_model.index(0, 1))
            self._certificate_changed(self.certificates_view.currentIndex(), None)

    def _certificate_changed(self, current, _previous):
        certificate = self.certificate_model.record(current)
        self.certificate_model.set_active_id(certificate["证书ID"] if certificate else None)
        self.viewing_certificate.setText(
            f"当前查看：{certificate['证书名称']}（ID {certificate['证书ID']}）"
            if certificate else "选择证书以查看当前项"
        )
        attachments = self.service.certificates.attachments(certificate["证书ID"]) if certificate else []
        self.attachment_model.set_rows(attachments)
        self.preview.show_path(None)
        if attachments:
            self.attachments_view.selectRow(0)

    def _attachment_changed(self, current, _previous):
        attachment = self.attachment_model.record(current)
        self.preview.show_path(attachment["路径"] if attachment else None)

    def eventFilter(self, watched, event):
        if watched is self.certificates_view.viewport() and event.type() == QEvent.MouseButtonDblClick:
            if event.button() == Qt.LeftButton:
                index = self.certificates_view.indexAt(event.position().toPoint())
                if index.isValid() and index.column() != 0:
                    record = self.certificate_model.record(index)
                    field = self.certificate_model.columns[index.column()][1]
                    value = record.get(field) if record else None
                    if value is not None and value != "":
                        self.copy_to_clipboard(str(value))
        return super().eventFilter(watched, event)

    def insert_to_word(self):
        try:
            plan = self.output_service.insert(self.job, self.settings_service.load(),
                confirm_style_fallback=lambda missing: confirm_style_fallback(self, missing))
        except (PersonWordPreflightError, PersonWordWriteError, WordServiceError) as error:
            message = writer_error_message(error, self.settings_service.load().writer_target)
        else:
            self.error_label.clear()
            self.notify(f"已插入 {len(plan.blocks)} 名人员，共 {plan.image_count} 张证书附件图片")
            return
        self.error_label.setText(message)
