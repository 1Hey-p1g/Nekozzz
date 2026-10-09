from gui.word_styles import confirm_style_fallback
"""Engineering search, independent output task, metadata copy and attachment preview."""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidgetItem, QPushButton, QSizePolicy, QSplitter, QVBoxLayout, QWidget,
    QScrollArea, QFrame, QLayout, QStyle,
)

from gui.common import CertificateTextDelegate, CheckBoxDelegate, ImagePreview, RowsModel, TaskRowsModel, table_view, task_row_widget
from gui.person_word import PersonOrderList
from services.project_word import ProjectWordJob, ProjectWordPreflightError, ProjectWordWriteError
from services.word_service import WordNoActiveDocumentError, WordNotRunningError, WordServiceError
from services.office_writer import writer_error_message


class ProjectSearchPage(QWidget):
    def __init__(self, service, output_service, settings_service, notify, copy_to_clipboard=None):
        super().__init__()
        self.service, self.output_service, self.settings_service = service, output_service, settings_service
        self.notify = notify
        self.copy_to_clipboard = copy_to_clipboard or QGuiApplication.clipboard().setText
        self.job = ProjectWordJob()
        self.viewed_project_id = None
        self.project_model = RowsModel([('工程名称', '项目名称')], self)
        self.info_model = RowsModel([('字段', '字段'), ('值', '值')], self)
        self.personnel_model = RowsModel([('担任职务', 'role'), ('姓名', 'person_name')], self)
        self.type_model = TaskRowsModel([('选择', ''), ('文件类型', '文件类型'), ('页数', '页数')], self, check_key='文件类型')
        self.attachment_model = RowsModel([('页序', '备注'), ('路径', '路径')], self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel('工程业绩搜索与选择')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        filters = QGridLayout()
        self.filters = {}
        for i, (key, label, hint) in enumerate((
            ('name', '工程名称', '关键字'), ('minimum_amount', '合同金额 ≥（元）', '留空不筛选'),
            ('completed_before', '竣工时间 ≤', 'YYYY-MM-DD；留空不筛选'),
            ('started_after', '开工时间 ≥', 'YYYY-MM-DD；留空不筛选'),
            ('leader', '项目负责人', '姓名关键字'),
        )):
            editor = QLineEdit()
            editor.setPlaceholderText(hint)
            editor.returnPressed.connect(self.search)
            self.filters[key] = editor
            row, group = divmod(i, 3)
            filters.addWidget(QLabel(label), row * 2, group)
            filters.addWidget(editor, row * 2 + 1, group)
        buttons = QHBoxLayout()
        search, clear = QPushButton('搜索'), QPushButton('清空')
        buttons.addWidget(search)
        buttons.addWidget(clear)
        filters.addLayout(buttons, 3, 2)
        layout.addLayout(filters)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        ll.addWidget(QLabel('搜索结果 · 单击查看，双击加入本次输出'))
        self.projects_view = table_view(self.project_model)
        self.projects_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        ll.addWidget(self.projects_view, 1)
        ll.addWidget(QLabel('本次输出工程 · 拖动调整顺序'))
        self.task_list = PersonOrderList()
        self.task_list.setObjectName('projectWordTaskList')
        ll.addWidget(self.task_list, 1)
        right = QWidget()
        self.right = right
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.setSpacing(5)
        rl.setSizeConstraint(QLayout.SetMinimumSize)
        rl.addWidget(QLabel('工程基本信息 · 双击值复制'))
        self.info_view = table_view(self.info_model)
        self.info_view.setWordWrap(True)
        self.info_view.setTextElideMode(Qt.ElideNone)
        self.info_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.info_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.info_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.info_view.setColumnWidth(0, 145)
        rl.addWidget(self.info_view)
        rl.addWidget(QLabel('项目管理人员 · 双击单元格复制'))
        self.personnel_view = table_view(self.personnel_model)
        self.personnel_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.personnel_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.personnel_view.setWordWrap(True)
        self.personnel_view.setTextElideMode(Qt.ElideNone)
        self.personnel_view.setColumnWidth(0, 145)
        self.personnel_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        rl.addWidget(self.personnel_view)
        rl.addWidget(QLabel('附件类型 · 勾选状态与当前查看独立'))
        self.types_view = table_view(self.type_model)
        self.types_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.types_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.types_view.setAlternatingRowColors(False)
        self.types_view.setItemDelegate(CertificateTextDelegate(self.types_view))
        self.types_view.setItemDelegateForColumn(0, CheckBoxDelegate(self.types_view))
        self.types_view.setColumnWidth(0, 58)
        self.types_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        rl.addWidget(self.types_view)
        self.viewing_type = QLabel('选择文件类型以预览')
        rl.addWidget(self.viewing_type)
        self.attachments_view = table_view(self.attachment_model)
        rl.addWidget(self.attachments_view)
        self.preview = ImagePreview(data_root=output_service.data_root, large_view_enabled=True)
        self.preview.setMinimumHeight(90)
        rl.addWidget(self.preview, 3)
        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setFrameShape(QFrame.NoFrame)
        self.right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.right_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.right_scroll.setWidget(right)
        split.addWidget(left)
        split.addWidget(self.right_scroll)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, 1)
        bottom = QHBoxLayout()
        self.insert_name = QCheckBox('插入工程名称')
        bottom.addWidget(self.insert_name)
        bottom.addStretch()
        self.output_button = QPushButton('插入资料')
        bottom.addWidget(self.output_button)
        layout.addLayout(bottom)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #ae3131')
        layout.addWidget(self.error_label)
        self.setStyleSheet('''
            QListWidget#projectWordTaskList { background: white; border: 1px solid #d1dbe7;
                border-radius: 6px; padding: 5px; color: #23405d; }
            QListWidget#projectWordTaskList::item { background: #f1f5f9; border-radius: 4px; }
            QListWidget#projectWordTaskList::item:selected { background: #dceafa; color: #23405d; }
            QPushButton#removeProjectFromWord { border: 0; border-radius: 5px;
                background: transparent; color: #ad6c70; padding: 0; }
            QPushButton#removeProjectFromWord:hover { background: #fbecee; color: #923e47; }
            QPushButton#removeProjectFromWord:pressed { background: #f4dce0; color: #7d303a; }
        ''')
        search.clicked.connect(self.search)
        clear.clicked.connect(self.clear_search)
        self.projects_view.doubleClicked.connect(self.add_project)
        self.projects_view.clicked.connect(self.view_search_project)
        self.projects_view.selectionModel().currentRowChanged.connect(self.view_search_project)
        self.task_list.currentItemChanged.connect(self.project_changed)
        self.task_list.itemClicked.connect(lambda item: self.project_changed(item, None))
        self.task_list.order_changed.connect(self.order_changed)
        self.types_view.selectionModel().currentRowChanged.connect(self.type_changed)
        self.types_view.clicked.connect(lambda index: self.type_changed(index, None))
        self.attachments_view.selectionModel().currentRowChanged.connect(self.attachment_changed)
        self.info_view.viewport().installEventFilter(self)
        self.right_scroll.viewport().installEventFilter(self)
        self.personnel_view.viewport().installEventFilter(self)
        self.personnel_view.horizontalHeader().sectionResized.connect(lambda *_: self.schedule_fit())
        self.info_view.horizontalHeader().sectionResized.connect(lambda *_: self.schedule_fit())
        self.insert_name.toggled.connect(lambda value: setattr(self.job, 'insert_project_name', value))
        self.output_button.clicked.connect(self.insert_to_word)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self.fit_tables)
        for view in (self.info_view, self.personnel_view, self.types_view, self.attachments_view):
            view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            view.setMinimumHeight(0)
        self.info_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.search()
        self.schedule_fit()

    def search(self):
        try:
            rows = self.service.search(**{key: editor.text().strip() for key, editor in self.filters.items()})
        except Exception as error:
            self.error_label.setText(f'搜索失败：{error}')
            return
        self.project_model.set_rows(rows)
        self.view_project(self.viewed_project_id)
        self.error_label.clear()

    def clear_search(self):
        for editor in self.filters.values():
            editor.clear()
        self.search()

    def current_id(self):
        return self.viewed_project_id

    def task_current_id(self):
        item = self.task_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def add_project(self, index):
        record = self.project_model.record(index)
        if not record:
            return
        value = record['业绩ID']
        if not self.job.add(value):
            self.view_project(value)
            for i in range(self.task_list.count()):
                if self.task_list.item(i).data(Qt.UserRole) == value:
                    self.task_list.setCurrentRow(i)
            self.notify('该工程已在本次输出列表中')
            return
        self.viewed_project_id = value
        self.refresh_task(value)

    def refresh_task(self, selected=None, *, preserve_view=False):
        blocked = self.task_list.blockSignals(True)
        try:
            self.task_list.clear()
            for i, value in enumerate(self.job.projects, 1):
                record = self.service.projects.get(value.project_id)
                name = record['项目名称'] if record else f'已删除工程 ID {value.project_id}'
                item = QListWidgetItem()
                item.setData(Qt.UserRole, value.project_id)
                self.task_list.addItem(item)
                widget, size = task_row_widget(self.task_list, f'{i}  {name}',
                    lambda _=False, pid=value.project_id: self.remove_project(pid),
                    tooltip='移除此工程', button_name='removeProjectFromWord', constrain_name=True)
                item.setSizeHint(size)
                self.task_list.setItemWidget(item, widget)
            if self.job.projects:
                row = next((i for i, value in enumerate(self.job.projects) if value.project_id == selected), 0)
                self.task_list.setCurrentRow(row)
        finally:
            self.task_list.blockSignals(blocked)
        self.view_project(self.viewed_project_id if preserve_view or selected is None else selected)

    def remove_project(self, project_id):
        ids = [item.project_id for item in self.job.projects]
        position = ids.index(project_id)
        selected = self.task_current_id()
        if selected == project_id:
            selected = ids[position + 1] if position + 1 < len(ids) else ids[position - 1] if position else None
        self.job.remove(project_id)
        self.refresh_task(selected, preserve_view=True)

    def order_changed(self):
        selected = self.task_current_id()
        self.job.reorder(self.task_list.person_ids())
        self.refresh_task(selected, preserve_view=True)

    def project_changed(self, current, _previous):
        if current is not None:
            self.view_project(current.data(Qt.UserRole))

    def view_search_project(self, index, _previous=None):
        record = self.project_model.record(index)
        if record is not None and record['业绩ID'] != self.viewed_project_id:
            self.view_project(record['业绩ID'])

    def view_project(self, project_id):
        if project_id is not None and self.service.projects.get(project_id) is None:
            project_id = None
        self.viewed_project_id = project_id
        self.personnel_model.set_rows([])
        self.info_model.set_rows([row for row in self.service.summary(project_id)
                                 if row['字段'] != '项目负责人'] if project_id is not None else [])
        if project_id is not None:
            self.personnel_model.set_rows(self.service.projects.project_personnel(project_id))
        item = self.job.item(project_id)
        self.type_model.checks_enabled = item is not None
        self.type_model.checked = item.selected_attachment_types if item else set()
        self.types_view.setToolTip('勾选用于本次输出' if item else '双击搜索结果加入输出序列后可勾选附件')
        self.type_model.set_active_id(None)
        rows = self.service.projects.attachment_types(project_id) if project_id is not None else []
        self.type_model.set_rows(rows)
        self.attachment_model.set_rows([])
        self.preview.show_path(None)
        self.viewing_type.setText('选择文件类型以预览')
        if rows:
            self.types_view.setCurrentIndex(self.type_model.index(0, 1))
            self.type_changed(self.type_model.index(0, 1), None)
        self.schedule_fit()

    def type_changed(self, current, _previous):
        # Checking a different row changes only its output selection, not the preview.
        if current.isValid() and current.column() == 0:
            return
        row = self.type_model.record(current)
        file_type = row['文件类型'] if row else None
        self.type_model.set_active_id(file_type)
        self.viewing_type.setText(f'当前查看：{file_type}' if file_type is not None else '选择文件类型以预览')
        pages = self.service.projects.attachments(self.current_id(), file_type) if row else []
        self.attachment_model.set_rows(pages)
        self.preview.show_path(None)
        if pages:
            self.attachments_view.selectRow(0)
        self.schedule_fit()

    def attachment_changed(self, current, _previous):
        row = self.attachment_model.record(current)
        self.preview.show_path(row['路径'] if row else None)

    def eventFilter(self, watched, event):
        if watched is self.right_scroll.viewport() and event.type() == QEvent.Resize:
            self.schedule_fit()
        if watched is self.info_view.viewport() and event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            index = self.info_view.indexAt(event.position().toPoint())
            record = self.info_model.record(index)
            if record is not None and index.column() == 1 and record['原值'] is not None and record['原值'] != '':
                self.copy_detail_value(record['原值'])
        elif watched is self.personnel_view.viewport() and event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            index = self.personnel_view.indexAt(event.position().toPoint())
            self.copy_detail_value(self.personnel_model.data(index))
        return super().eventFilter(watched, event)

    def copy_detail_value(self, value):
        if value is not None and value != '':
            self.copy_to_clipboard(str(value))

    def fit_info(self):
        self.info_view.resizeRowsToContents()
        self._fix_visible_rows(self.info_view, 4)

    @staticmethod
    def table_height_for_rows(view, rows):
        """A stable font/style row budget, independent of current record content."""
        view.ensurePolished()
        header = view.horizontalHeader()
        header.ensurePolished()
        margin = view.style().pixelMetric(QStyle.PM_FocusFrameVMargin, None, view)
        row_height = max(view.verticalHeader().defaultSectionSize(),
                         view.fontMetrics().lineSpacing() + 2 * margin)
        row_height += int(view.showGrid())
        return header.height() + 2 * view.frameWidth() + rows * row_height

    def _fix_visible_rows(self, view, rows):
        # AlwaysOff prevents content-dependent horizontal bars moving later sections.
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        height = self.table_height_for_rows(view, rows)
        if view.minimumHeight() != height or view.maximumHeight() != height:
            view.setFixedHeight(height)

    def fit_tables(self):
        # Three stable sections; only the preview and existing page-list strategy
        # absorb remaining space. Outer overflow remains available in small windows.
        self.personnel_view.resizeRowsToContents()
        self._fix_visible_rows(self.personnel_view, 3)
        self._fix_visible_rows(self.types_view, 3)
        for view, minimum_rows, maximum_rows in ((self.attachments_view, 2, 2),):
            header = view.horizontalHeader().height() + 2 * view.frameWidth()
            count = view.model().rowCount()
            heights = [view.rowHeight(i) for i in range(min(count, maximum_rows))]
            horizontal = view.horizontalScrollBar().sizeHint().height() if view.horizontalScrollBar().isVisible() else 0
            minimum = header + sum(heights[:minimum_rows]) + horizontal
            maximum = header + sum(heights) + horizontal
            if view.minimumHeight() != minimum:
                view.setMinimumHeight(minimum)
            if view.maximumHeight() != maximum:
                view.setMaximumHeight(maximum)
        for index in range(self.right.layout().count()):
            widget = self.right.layout().itemAt(index).widget()
            if isinstance(widget, QLabel) and widget is not self.preview:
                widget.setMinimumHeight(widget.sizeHint().height())
        # Keep the existing compact preview floor, scaled up for larger fonts;
        # source image dimensions must never feed back into the layout budget.
        preview_minimum = max(90, self.preview.fontMetrics().lineSpacing() * 4 + 2 * self.preview.frameWidth())
        self.preview.setMinimumHeight(preview_minimum)
        self.fit_info()

    def schedule_fit(self):
        if hasattr(self, "_fit_timer") and not self._fit_timer.isActive():
            self._fit_timer.start(0)

    def showEvent(self, event):
        super().showEvent(event)
        self.schedule_fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.schedule_fit()

    def insert_to_word(self):
        self.output_button.setEnabled(False)
        try:
            plan = self.output_service.insert(self.job, self.settings_service.load(),
                confirm_style_fallback=lambda missing: confirm_style_fallback(self, missing))
        except (ProjectWordPreflightError, ProjectWordWriteError, WordServiceError) as error:
            self.error_label.setText(writer_error_message(error, self.settings_service.load().writer_target))
        except Exception as error:
            self.error_label.setText('文档输出失败：' + writer_error_message(error, self.settings_service.load().writer_target))
        else:
            self.error_label.clear()
            self.notify(f'已插入 {len(plan.blocks)} 项工程，共 {plan.image_count} 张附件图片')
        finally:
            self.output_button.setEnabled(True)
