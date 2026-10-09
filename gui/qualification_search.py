"""Read-only company qualification selection, preview and Word output."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from gui.common import CertificateTextDelegate, CheckBoxDelegate, ImagePreview, RowsModel, StyledComboBox, table_view
from gui.company_info import CompanyInfoView
from gui.word_styles import confirm_style_fallback
from services.people import expiry_status
from services.qualification_word import QualificationWordPreflightError, QualificationWordWriteError
from services.word_service import WordNoActiveDocumentError, WordNotRunningError, WordServiceError
from services.office_writer import writer_error_message


class QualificationSearchPage(QWidget):
    def __init__(self, service, output_service, settings_service, notify, copy_to_clipboard=None):
        super().__init__()
        self.service, self.output_service, self.settings_service = service, output_service, settings_service
        self.notify = notify
        self.copy_to_clipboard = copy_to_clipboard or QGuiApplication.clipboard().setText
        self.selected_ids = set()
        self.current_qualification_id = None
        self.company_list_available = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel('公司资质搜索与选择')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        subtitle = QLabel('勾选本次需要输出的资质；点击文字查看附件，双击文字复制。')
        subtitle.setObjectName('subtitle')
        layout.addWidget(subtitle)
        filters = QHBoxLayout()
        self.name_input, self.grade_input = QLineEdit(), QLineEdit()
        self.name_input.setPlaceholderText('资质证书名称')
        self.grade_input.setPlaceholderText('资质等级')
        self.company = StyledComboBox()
        self.status = StyledComboBox()
        self.status.addItem('全部有效期状态', '')
        for value in ('长期有效', '正常有效', '即将到期', '已过期', '未填写或无法判断'):
            self.status.addItem(value, value)
        search, clear = QPushButton('搜索'), QPushButton('清空')
        for widget in (self.name_input, self.grade_input, self.company, self.status, search, clear):
            filters.addWidget(widget)
        layout.addLayout(filters)
        split = QSplitter(Qt.Horizontal)
        self.model = RowsModel([
            ('选择', ''), ('资质证书名称', '资质证书名称'), ('资质等级', '资质等级'),
            ('所属公司', '公司名称'), ('有效期', '有效期'), ('状态', '有效期状态'),
        ], self, check_key='资质ID', checked=self.selected_ids)
        self.qualifications_view = table_view(self.model)
        self.qualifications_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.qualifications_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.qualifications_view.setAlternatingRowColors(False)
        self.qualifications_view.setItemDelegate(CertificateTextDelegate(self.qualifications_view))
        self.qualifications_view.setItemDelegateForColumn(0, CheckBoxDelegate(self.qualifications_view))
        self.qualifications_view.horizontalHeader().setStretchLastSection(False)
        self.qualifications_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for column, width in ((0, 55), (2, 70), (3, 100), (4, 100), (5, 120)):
            self.qualifications_view.setColumnWidth(column, width)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.company_info = CompanyInfoView()
        left_layout.addWidget(self.company_info)
        left_layout.addWidget(self.qualifications_view, 1)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.addWidget(QLabel('公司资质信息'))
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setStyleSheet('background: white; border: 1px solid #dce4ed; border-radius: 8px; padding: 8px;')
        self.summary.setMaximumHeight(self.summary.fontMetrics().lineSpacing() * 9 + 24)
        rl.addWidget(self.summary)
        self.current_label = QLabel('选择资质以查看附件')
        self.current_label.setWordWrap(True)
        rl.addWidget(self.current_label)
        self.attachment_model = RowsModel([('页序', '备注'), ('路径', '路径')], self)
        self.attachments_view = table_view(self.attachment_model)
        self.attachments_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.attachments_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.attachments_view.setMaximumHeight(self.attachments_view.horizontalHeader().sizeHint().height() +
                                              3 * self.attachments_view.verticalHeader().defaultSectionSize() + 2 * self.attachments_view.frameWidth())
        rl.addWidget(self.attachments_view)
        self.preview = ImagePreview(data_root=output_service.data_root, large_view_enabled=True)
        self.preview.setMinimumHeight(90)
        rl.addWidget(self.preview, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, 1)
        actions = QHBoxLayout()
        self.selected_count = QLabel()
        self.clear_selection_button = QPushButton('清空本次选择')
        self.output_button = QPushButton('插入资料')
        actions.addWidget(self.selected_count)
        actions.addWidget(self.clear_selection_button)
        self.insert_name = QCheckBox('插入资质证书名称')
        actions.addWidget(self.insert_name)
        actions.addStretch()
        actions.addWidget(self.output_button)
        layout.addLayout(actions)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #ae3131')
        layout.addWidget(self.error_label)
        search.clicked.connect(self.search)
        clear.clicked.connect(self.clear_search)
        self.name_input.returnPressed.connect(self.search)
        self.grade_input.returnPressed.connect(self.search)
        self.model.dataChanged.connect(self.update_count)
        self.qualifications_view.selectionModel().currentRowChanged.connect(self.qualification_changed)
        self.qualifications_view.clicked.connect(lambda index: self.qualification_changed(index, None))
        self.qualifications_view.viewport().installEventFilter(self)
        self.attachments_view.selectionModel().currentRowChanged.connect(self.attachment_changed)
        self.clear_selection_button.clicked.connect(self.clear_selection)
        self.output_button.clicked.connect(self.insert_to_word)
        self.company.currentIndexChanged.connect(self.refresh_company_info)
        self.refresh_companies()
        self.search()
        self.update_count()

    def refresh_companies(self):
        selected = self.company.currentData()
        self.company.blockSignals(True)
        try:
            self.company.clear()
            self.company.addItem('全部公司', None)
            for company in self.service.qualifications.companies():
                self.company.addItem(f"{company['公司名称']}（ID {company['公司ID']}）", company['公司ID'])
            self.company.setCurrentIndex(max(0, self.company.findData(selected)))
            self.company_list_available = True
        except Exception as error:
            self.company_list_available = False
            self.company_info.display(None)
            self.error_label.setText(f'公司列表加载失败：{error}')
        finally:
            self.company.blockSignals(False)
        self.refresh_company_info()

    def refresh_company_info(self, *_):
        self.company_info.display(None)
        if not self.company_list_available:
            return
        company_id = self.company.currentData()
        try:
            if company_id is None:
                row = self.service.qualifications.get(self.current_qualification_id) if self.current_qualification_id is not None else None
                company_id = row['公司ID'] if row else (self.company.itemData(1) if self.company.count() == 2 else None)
            self.company_info.display(self.service.qualifications.company_info(company_id) if company_id is not None else None)
        except Exception as error:
            self.error_label.setText(f'公司信息加载失败：{error}')

    def search(self):
        try:
            rows = self.service.search(name=self.name_input.text(), grade=self.grade_input.text(),
                                       company_id=self.company.currentData(), status=self.status.currentData())
        except Exception as error:
            self.company_info.display(None)
            self.error_label.setText(f'搜索失败：{error}')
            return
        if self.company_list_available:
            self.error_label.clear()
        selected = self.current_qualification_id
        self.model.set_rows(rows)
        self.model.set_active_id(None)
        index = next((i for i, row in enumerate(rows) if row['资质ID'] == selected), 0)
        if rows:
            self.qualifications_view.setCurrentIndex(self.model.index(index, 1))
            self.qualification_changed(self.model.index(index, 1), None)
        else:
            self.clear_preview()
        self.update_count()

    def clear_search(self):
        self.name_input.clear()
        self.grade_input.clear()
        self.company.setCurrentIndex(0)
        self.status.setCurrentIndex(0)
        self.search()

    def update_count(self, *_):
        self.selected_count.setText(f'已选择 {len(self.selected_ids)} 项资质')

    def clear_selection(self):
        self.selected_ids.clear()
        if self.model.rowCount():
            self.model.dataChanged.emit(self.model.index(0, 0),
                                        self.model.index(self.model.rowCount() - 1, 0), [Qt.CheckStateRole])
        self.update_count()

    def clear_preview(self):
        self.current_qualification_id = None
        self.refresh_company_info()
        self.summary.setPlainText('选择公司资质以查看基本资料')
        self.current_label.setText('选择资质以查看附件')
        self.attachment_model.set_rows([])
        self.preview.show_path(None)

    def qualification_changed(self, current, _previous):
        if current.isValid() and current.column() == 0:
            return
        row = self.model.record(current)
        if row is None:
            self.clear_preview()
            return
        self.current_qualification_id = row['资质ID']
        self.refresh_company_info()
        self.model.set_active_id(self.current_qualification_id)
        fields = ('公司名称', '资质证书名称', '资质等级', '发证机构', '发证日期', '有效期')
        lines = [f"{field}：{row[field] if row[field] not in (None, '') else '—'}" for field in fields]
        lines.append('有效期状态：' + expiry_status(row['有效期']))
        self.summary.setPlainText('\n'.join(lines))
        self.current_label.setText(f"当前查看：{row['资质证书名称']}（ID {row['资质ID']}）")
        pages = self.service.qualifications.attachments(row['资质ID'])
        self.attachment_model.set_rows(pages)
        self.preview.show_path(None)
        if pages:
            self.attachments_view.selectRow(0)

    def attachment_changed(self, current, _previous):
        row = self.attachment_model.record(current)
        self.preview.show_path(row['路径'] if row else None)

    def eventFilter(self, watched, event):
        if watched is self.qualifications_view.viewport() and event.type() == QEvent.MouseButtonDblClick:
            if event.button() == Qt.LeftButton:
                index = self.qualifications_view.indexAt(event.position().toPoint())
                row = self.model.record(index)
                if row is not None and index.column() != 0:
                    value = row.get(self.model.columns[index.column()][1])
                    if value is not None and value != '':
                        self.copy_to_clipboard(str(value))
        return super().eventFilter(watched, event)

    def insert_to_word(self):
        self.output_button.setEnabled(False)
        try:
            plan = self.output_service.insert(self.selected_ids, self.settings_service.load(),
                insert_qualification_name=self.insert_name.isChecked(),
                confirm_style_fallback=lambda missing: confirm_style_fallback(self, missing))
        except (QualificationWordPreflightError, QualificationWordWriteError, WordServiceError) as error:
            self.error_label.setText(writer_error_message(error, self.settings_service.load().writer_target))
        except Exception as error:
            self.error_label.setText('文档输出失败：' + writer_error_message(error, self.settings_service.load().writer_target))
        else:
            self.error_label.clear()
            self.notify(f'已插入 {len(plan.blocks)} 项公司资质，共 {plan.image_count} 张附件图片')
        finally:
            self.output_button.setEnabled(True)
