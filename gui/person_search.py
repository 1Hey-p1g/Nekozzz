"""Read-only bidding workflow: search people, check certificates, preview pages."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSplitter, QVBoxLayout, QWidget,
)

from gui.common import CertificateTextDelegate, CheckBoxDelegate, ImagePreview, RowsModel, format_person_summary, table_view
from services.people import expiry_status


class PersonSearchPage(QWidget):
    def __init__(self, service, copy_to_clipboard=None):
        super().__init__()
        self.service = service
        self.copy_to_clipboard = copy_to_clipboard or QGuiApplication.clipboard().setText
        self.current_person_id = None
        self.checked_ids = set()
        self.person_model = RowsModel([("姓名", "姓名")], self)
        self.certificate_model = RowsModel(
            [("选择", ""), ("证书类型", "证书类型"), ("证书名称", "证书名称"),
             ("证书编号", "证书编号"), ("有效期", "有效期"), ("状态", "状态")],
            self, check_key="证书ID", checked=self.checked_ids,
        )
        self.attachment_model = RowsModel([("页序", "备注"), ("路径", "路径")], self)
        self._build()
        self.search_people()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(14)
        heading = QLabel("人员搜索与选择")
        heading.setObjectName("pageTitle")
        heading.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(heading)
        subtitle = QLabel("查找人员与证书，勾选本次投标需要的资料。勾选只保存在当前界面会话。")
        subtitle.setObjectName("subtitle")
        subtitle.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(subtitle)
        filters = QHBoxLayout()
        self.name_filter = QLineEdit()
        self.name_filter.setPlaceholderText("搜索人员姓名")
        self.cert_filter = QLineEdit()
        self.cert_filter.setPlaceholderText("筛选证书名称")
        find = QPushButton("搜索")
        clear = QPushButton("清空")
        filters.addWidget(self.name_filter, 2)
        filters.addWidget(self.cert_filter, 2)
        filters.addWidget(find)
        filters.addWidget(clear)
        layout.addLayout(filters)
        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        self.people_view = table_view(self.person_model)
        left_layout.addWidget(self.people_view)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        self.person_info = QLabel("选择人员以查看资料")
        self.person_info.setObjectName("detailSummary")
        self.person_info.setWordWrap(True)
        self.person_info.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.person_info.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        right_layout.addWidget(self.person_info)
        self.selected_count = QLabel("已选 0 张证书")
        right_layout.addWidget(self.selected_count)
        right_layout.addWidget(QLabel("证书（勾选后可供未来 Word 模块读取）"))
        self.certificates_view = table_view(self.certificate_model)
        self.certificates_view.setObjectName("certificateSelectionTable")
        # Cell selection tracks the current record; copying uses double-click.
        # Only the model's first-column BackgroundRole is visually highlighted.
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
        right_layout.addWidget(self.certificates_view, 3)
        right_layout.addWidget(QLabel("当前证书的附件"))
        self.attachments_view = table_view(self.attachment_model)
        right_layout.addWidget(self.attachments_view, 2)
        self.preview = ImagePreview(large_view_enabled=True)
        right_layout.addWidget(self.preview, 2)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([190, 850])
        layout.addWidget(splitter, 1)
        find.clicked.connect(self.search_people)
        clear.clicked.connect(self.clear_search)
        self.name_filter.returnPressed.connect(self.search_people)
        self.cert_filter.returnPressed.connect(self.search_people)
        self.people_view.selectionModel().currentRowChanged.connect(self._person_changed)
        self.certificates_view.selectionModel().currentRowChanged.connect(self._certificate_changed)
        self.certificates_view.viewport().installEventFilter(self)
        self.attachments_view.selectionModel().currentRowChanged.connect(self._attachment_changed)
        self.certificate_model.dataChanged.connect(self._update_selected_count)

    def clear_search(self):
        self.name_filter.clear()
        self.cert_filter.clear()
        self.search_people()

    def search_people(self):
        # A certificate may have been deleted on the separate maintenance page.
        existing = self.service.certificates.existing_ids(self.checked_ids)
        self.checked_ids.intersection_update(existing)
        self._update_selected_count()
        previous = self.current_person_id
        people = self.service.people.search(self.name_filter.text(), self.cert_filter.text())
        self.person_model.set_rows(people)
        chosen = next((i for i, row in enumerate(people) if row["人员ID"] == previous), 0)
        if people:
            self.people_view.selectRow(chosen)
        else:
            self._clear_person()

    def _clear_person(self):
        self.current_person_id = None
        self.person_info.setText("没有匹配的人员")
        self.certificate_model.set_active_id(None)
        self.certificate_model.set_rows([])
        self.attachment_model.set_rows([])
        self.preview.show_path(None)

    def _person_changed(self, current, _previous):
        row = self.person_model.record(current)
        if not row:
            self._clear_person()
            return
        self.current_person_id = row["人员ID"]
        detail = self.service.people.get(self.current_person_id)
        if not detail:
            self._clear_person()
            return
        self.person_info.setText(format_person_summary(detail))
        rows = self.service.certificates.for_person(self.current_person_id, self.cert_filter.text())
        self.certificate_model.set_active_id(None)
        self.certificate_model.set_rows([{**item, "状态": expiry_status(item["有效期"])} for item in rows])
        self.attachment_model.set_rows([])
        self.preview.show_path(None)
        if rows:
            self.certificates_view.setCurrentIndex(self.certificate_model.index(0, 1))
            self._certificate_changed(self.certificates_view.currentIndex(), None)

    def _certificate_changed(self, current, _previous):
        row = self.certificate_model.record(current)
        self.certificate_model.set_active_id(row["证书ID"] if row else None)
        attachments = self.service.certificates.attachments(row["证书ID"]) if row else []
        self.attachment_model.set_rows(attachments)
        self.preview.show_path(None)
        if attachments:
            self.attachments_view.selectRow(0)

    def _copy_certificate_cell(self, index):
        if not index.isValid() or index.column() == 0:
            return
        record = self.certificate_model.record(index)
        if record is None:
            return
        field = self.certificate_model.columns[index.column()][1]
        value = (self.certificate_model.data(index, Qt.DisplayRole)
                 if field == "状态" else record.get(field))
        if value is None or value == "":
            return
        self.copy_to_clipboard(str(value))

    def eventFilter(self, watched, event):
        if watched is self.certificates_view.viewport() and event.type() == QEvent.MouseButtonDblClick:
            if event.button() == Qt.LeftButton:
                self._copy_certificate_cell(self.certificates_view.indexAt(event.position().toPoint()))
        return super().eventFilter(watched, event)

    def _attachment_changed(self, current, _previous):
        row = self.attachment_model.record(current)
        self.preview.show_path(row["路径"] if row else None)

    def _update_selected_count(self, *_):
        self.selected_count.setText(f"已选 {len(self.checked_ids)} 张证书")

    def selected_certificate_ids(self):
        return frozenset(self.checked_ids)

    def selected_certificates(self):
        """Future Word integration point; stable IDs with current rows and ordered pages."""
        return self.service.selected_certificates(sorted(self.checked_ids))
