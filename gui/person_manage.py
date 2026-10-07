"""Editable person → certificate → attachment workspace."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from gui.common import ImagePreview, RowsModel, StyledComboBox, table_view
from repositories.certificate_repository import CERTIFICATE_PRIORITY
from repositories.person_repository import PERSON_FIELDS
from services.people import friendly_database_error
from services.pdf_import import render_pdf, rotate_temporary_page


class PersonManagePage(QWidget):
    def __init__(self, service, *, settings_service, attachment_service, notify):
        super().__init__()
        self.service = service
        self.settings_service = settings_service
        self.attachment_service = attachment_service
        self.notify = notify
        self._render_context = None
        self._pending_pages = ()
        self._pending_replace = False
        self._pending_page_index = 0
        self.person_id = None
        self.certificate_id = None
        self.mode = "view"
        self.dirty = False
        self._loading = False
        self._reverting = False
        self._original_person = None
        self._original_certificate = None
        self.person_model = RowsModel([("姓名", "姓名"), ("人员 ID", "人员ID")], self)
        self.certificate_model = RowsModel(
            [("类型", "证书类型"), ("名称", "证书名称"), ("编号", "证书编号"), ("有效期", "有效期")], self,
        )
        self.attachment_model = RowsModel([("页序", "备注"), ("路径", "路径")], self)
        self._build()
        self.refresh_people()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        heading = QLabel("人员资料管理")
        heading.setObjectName("pageTitle")
        heading.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(heading)
        subtitle = QLabel("维护人员、证书及当前证书的附件。删除受关联约束保护。")
        subtitle.setObjectName("subtitle")
        subtitle.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(subtitle)
        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索人员姓名")
        left_layout.addWidget(self.search_input)
        self.people_view = table_view(self.person_model)
        left_layout.addWidget(self.people_view)
        self.new_person_button = QPushButton("新增人员")
        left_layout.addWidget(self.new_person_button)
        splitter.addWidget(left)

        scroll = QScrollArea()
        self.detail_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 8, 0)
        right_layout.setSpacing(12)
        self.state_label = QLabel("查看状态")
        self.state_label.setObjectName("stateLabel")
        right_layout.addWidget(self.state_label)
        right_layout.addWidget(QLabel("人员基本资料"))
        person_grid = QGridLayout()
        self.person_inputs = {}
        labels = {"进入系统日期": "入职日期"}
        for index, field in enumerate(PERSON_FIELDS):
            label = QLabel(labels.get(field, field))
            editor = QLineEdit()
            if field == "进入系统日期":
                editor.setPlaceholderText("YYYY-MM-DD；留空为未填写")
            editor.textChanged.connect(self._mark_dirty)
            self.person_inputs[field] = editor
            row, group = divmod(index, 2)
            person_grid.addWidget(label, row, group * 2)
            person_grid.addWidget(editor, row, group * 2 + 1)
        right_layout.addLayout(person_grid)
        person_actions = QHBoxLayout()
        self.edit_person_button = QPushButton("编辑人员")
        self.save_person_button = QPushButton("保存人员")
        self.cancel_person_button = QPushButton("取消")
        self.delete_person_button = QPushButton("删除人员")
        for button in (self.edit_person_button, self.save_person_button,
                       self.cancel_person_button, self.delete_person_button):
            person_actions.addWidget(button)
        right_layout.addLayout(person_actions)

        right_layout.addWidget(QLabel("该人员的证书"))
        self.certificates_view = table_view(self.certificate_model)
        self.certificates_view.setMinimumHeight(145)
        right_layout.addWidget(self.certificates_view)
        certificate_form = QFormLayout()
        self.type_input = StyledComboBox()
        self.type_input.setEditable(True)
        self.type_input.addItems(CERTIFICATE_PRIORITY)
        self.type_input.currentTextChanged.connect(self._mark_dirty)
        self.certificate_inputs = {"证书类型": self.type_input}
        certificate_form.addRow("证书类型", self.type_input)
        for field in ("证书名称", "证书编号", "有效期"):
            editor = QLineEdit()
            if field == "有效期":
                editor.setPlaceholderText("YYYY-MM-DD；留空为长期有效")
            editor.textChanged.connect(self._mark_dirty)
            self.certificate_inputs[field] = editor
            certificate_form.addRow(field, editor)
        right_layout.addLayout(certificate_form)
        certificate_actions = QHBoxLayout()
        self.new_certificate_button = QPushButton("新增证书")
        self.edit_certificate_button = QPushButton("编辑证书")
        self.save_certificate_button = QPushButton("保存证书")
        self.cancel_certificate_button = QPushButton("取消")
        self.delete_certificate_button = QPushButton("删除证书")
        for button in (self.new_certificate_button, self.edit_certificate_button,
                       self.save_certificate_button, self.cancel_certificate_button,
                       self.delete_certificate_button):
            certificate_actions.addWidget(button)
        right_layout.addLayout(certificate_actions)
        self.attachment_section = QGroupBox("当前证书附件")
        self.attachment_section.setObjectName("certificateAttachmentSection")
        attachment_layout = QVBoxLayout(self.attachment_section)
        attachment_layout.setSpacing(8)
        attachment_actions = QHBoxLayout()
        self.import_pdf_button = QPushButton("导入 PDF")
        self.replace_pdf_button = QPushButton("替换 PDF")
        self.delete_attachments_button = QPushButton("删除整份附件")
        for button in (self.import_pdf_button, self.replace_pdf_button, self.delete_attachments_button):
            attachment_actions.addWidget(button)
        attachment_actions.addStretch()
        attachment_layout.addLayout(attachment_actions)
        self.attachments_view = table_view(self.attachment_model)
        self.attachments_view.setMinimumHeight(125)
        attachment_layout.addWidget(self.attachments_view)
        self.preview = ImagePreview(data_root=self.attachment_service.data_root)
        attachment_layout.addWidget(self.preview)
        self.import_preview = QWidget()
        import_layout = QVBoxLayout(self.import_preview)
        self.import_page_label = QLabel("第 1 / 1 页")
        import_layout.addWidget(self.import_page_label)
        self.import_image = QLabel()
        self.import_image.setAlignment(Qt.AlignCenter)
        self.import_image.setMinimumHeight(190)
        self.import_image.setStyleSheet("background: #f6f8fb; border: 1px solid #dce4ed; border-radius: 6px")
        import_layout.addWidget(self.import_image)
        page_actions = QHBoxLayout()
        self.previous_page_button = QPushButton("上一页")
        self.next_page_button = QPushButton("下一页")
        self.rotate_left_button = QPushButton("向左旋转 90°")
        self.rotate_right_button = QPushButton("向右旋转 90°")
        for button in (self.previous_page_button, self.next_page_button,
                       self.rotate_left_button, self.rotate_right_button):
            page_actions.addWidget(button)
        import_layout.addLayout(page_actions)
        confirm_actions = QHBoxLayout()
        self.confirm_import_button = QPushButton("确认导入")
        self.cancel_import_button = QPushButton("取消")
        confirm_actions.addWidget(self.confirm_import_button)
        confirm_actions.addWidget(self.cancel_import_button)
        confirm_actions.addStretch()
        import_layout.addLayout(confirm_actions)
        self.import_error = QLabel("")
        self.import_error.setStyleSheet("color: #ae3131")
        import_layout.addWidget(self.import_error)
        attachment_layout.addWidget(self.import_preview)
        self.import_preview.hide()
        right_layout.addWidget(self.attachment_section)
        right_layout.addStretch(1)
        scroll.setWidget(right)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        layout.addWidget(splitter, 1)

        self.search_input.returnPressed.connect(self.search_people)
        self.people_view.selectionModel().currentRowChanged.connect(self._person_changed)
        self.certificates_view.selectionModel().currentRowChanged.connect(self._certificate_changed)
        self.attachments_view.selectionModel().currentRowChanged.connect(self._attachment_changed)
        self.new_person_button.clicked.connect(self.new_person)
        self.edit_person_button.clicked.connect(lambda: self._set_mode("edit_person"))
        self.save_person_button.clicked.connect(self.save_person)
        self.cancel_person_button.clicked.connect(self.cancel)
        self.delete_person_button.clicked.connect(self.delete_person)
        self.new_certificate_button.clicked.connect(self.new_certificate)
        self.edit_certificate_button.clicked.connect(lambda: self._set_mode("edit_certificate"))
        self.save_certificate_button.clicked.connect(self.save_certificate)
        self.cancel_certificate_button.clicked.connect(self.cancel)
        self.delete_certificate_button.clicked.connect(self.delete_certificate)
        self.import_pdf_button.clicked.connect(lambda: self._choose_pdf(replace=False))
        self.replace_pdf_button.clicked.connect(lambda: self._choose_pdf(replace=True))
        self.delete_attachments_button.clicked.connect(self.delete_attachments)
        self.previous_page_button.clicked.connect(lambda: self._show_pending_page(self._pending_page_index - 1))
        self.next_page_button.clicked.connect(lambda: self._show_pending_page(self._pending_page_index + 1))
        self.rotate_left_button.clicked.connect(lambda: self._rotate_pending(-90))
        self.rotate_right_button.clicked.connect(lambda: self._rotate_pending(90))
        self.confirm_import_button.clicked.connect(self.confirm_import)
        self.cancel_import_button.clicked.connect(self.cancel_import)
        QApplication.instance().aboutToQuit.connect(self._release_pending)
        self._set_mode("view")

    def _mark_dirty(self, *_):
        if not self._loading and self.mode != "view":
            self.dirty = True

    def _set_mode(self, mode):
        self.mode = mode
        self.dirty = False
        self.state_label.setText({
            "view": "查看状态", "edit_person": "编辑人员 · 未保存",
            "new_person": "新增人员 · 未保存", "edit_certificate": "编辑证书 · 未保存",
            "new_certificate": "新增证书 · 未保存",
        }[mode])
        person_edit = mode in ("edit_person", "new_person")
        certificate_edit = mode in ("edit_certificate", "new_certificate")
        for editor in self.person_inputs.values():
            editor.setReadOnly(not person_edit)
        for field, editor in self.certificate_inputs.items():
            if field == "证书类型":
                editor.setEnabled(certificate_edit)
            else:
                editor.setReadOnly(not certificate_edit)
        self.save_person_button.setEnabled(person_edit)
        self.cancel_person_button.setEnabled(person_edit)
        self.save_certificate_button.setEnabled(certificate_edit)
        self.cancel_certificate_button.setEnabled(certificate_edit)
        self.edit_person_button.setEnabled(mode == "view" and self.person_id is not None)
        self.delete_person_button.setEnabled(mode == "view" and self.person_id is not None)
        self.new_person_button.setEnabled(mode == "view")
        self.new_certificate_button.setEnabled(mode == "view" and self.person_id is not None)
        self.edit_certificate_button.setEnabled(mode == "view" and self.certificate_id is not None)
        self.delete_certificate_button.setEnabled(mode == "view" and self.certificate_id is not None)
        self._update_attachment_actions()

    def can_leave(self):
        if self._render_context is not None:
            result = QMessageBox.question(
                self, "取消附件导入", "当前 PDF 尚未保存。确定放弃并清理临时图片吗？",
                QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel,
            )
            if result != QMessageBox.Discard:
                return False
            self.cancel_import()
        if not self.dirty:
            return True
        result = QMessageBox.question(
            self, "未保存的修改", "当前修改尚未保存。确定放弃修改吗？",
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        return result == QMessageBox.Discard

    def _allow_switch(self):
        if self.can_leave():
            self._set_mode("view")
            return True
        return False

    def _select_id(self, view, model, field, value):
        for index, row in enumerate(model.rows):
            if row[field] == value:
                view.selectRow(index)
                return True
        return False

    def search_people(self):
        if self.mode != "view":
            if not self.can_leave():
                return
            self.discard_changes()
        self.refresh_people()

    def discard_changes(self):
        """Use only after the user approved discarding, or for an explicit cancel."""
        self._set_mode("view")
        if self.person_id is None:
            self.refresh_people()
            return
        self._load_person(self.service.people.get(self.person_id))
        self._refresh_certificates()
        self._load_certificate(self.service.certificates.get(self.certificate_id) if self.certificate_id else None)

    def refresh_people(self, select_id=None):
        target = select_id if select_id is not None else self.person_id
        self._loading = True
        self.person_model.set_rows(self.service.people.search(self.search_input.text()))
        self._loading = False
        if not self._select_id(self.people_view, self.person_model, "人员ID", target):
            if self.person_model.rows:
                self.people_view.selectRow(0)
            else:
                self.person_id = None
                self.certificate_id = None
                self._load_person(None)
                self._load_certificate(None)
                self.certificate_model.set_rows([])
                self.attachment_model.set_rows([])
                self._set_mode("view")

    def _person_changed(self, current, _previous):
        if self._loading or self._reverting:
            return
        row = self.person_model.record(current)
        new_id = row["人员ID"] if row else None
        if new_id == self.person_id:
            return
        if self.mode != "view" and not self._allow_switch():
            self._reverting = True
            if not self._select_id(self.people_view, self.person_model, "人员ID", self.person_id):
                self.people_view.clearSelection()
            self._reverting = False
            return
        self.person_id = new_id
        self.certificate_id = None
        self._load_person(self.service.people.get(new_id) if new_id else None)
        self._refresh_certificates()
        self._set_mode("view")

    def _load_person(self, row):
        self._original_person = row
        self._loading = True
        for field, editor in self.person_inputs.items():
            editor.setText("" if not row or row[field] is None else str(row[field]))
        self._loading = False

    def _refresh_certificates(self, select_id=None):
        rows = self.service.certificates.for_person(self.person_id) if self.person_id else []
        self._loading = True
        self.certificate_model.set_rows(rows)
        self._loading = False
        target = select_id if select_id is not None else self.certificate_id
        if not self._select_id(self.certificates_view, self.certificate_model, "证书ID", target):
            if rows:
                self.certificates_view.selectRow(0)
            else:
                self.certificate_id = None
                self._load_certificate(None)
                self.attachment_model.set_rows([])
                self.preview.show_path(None)
                self._set_mode("view")

    def _certificate_changed(self, current, _previous):
        if self._loading or self._reverting:
            return
        row = self.certificate_model.record(current)
        new_id = row["证书ID"] if row else None
        if new_id == self.certificate_id:
            return
        if self.mode != "view" and not self._allow_switch():
            self._reverting = True
            if not self._select_id(self.certificates_view, self.certificate_model, "证书ID", self.certificate_id):
                self.certificates_view.clearSelection()
            self._reverting = False
            return
        self.certificate_id = new_id
        self._load_certificate(self.service.certificates.get(new_id) if new_id else None)
        self._refresh_attachments()
        self._set_mode("view")

    def _load_certificate(self, row):
        self._original_certificate = row
        self._loading = True
        for field, editor in self.certificate_inputs.items():
            value = "" if not row or row[field] is None else str(row[field])
            if field == "证书类型":
                editor.setCurrentText(value)  # Editable: historical categories remain valid.
            else:
                editor.setText(value)
        self._loading = False

    def _attachment_changed(self, current, _previous):
        row = self.attachment_model.record(current)
        self.preview.show_path(row["路径"] if row else None)

    def _refresh_attachments(self):
        attachments = self.service.certificates.attachments(self.certificate_id) if self.certificate_id else []
        self.attachment_model.set_rows(attachments)
        self.preview.show_path(None)
        if attachments:
            self.attachments_view.selectRow(0)
        self._update_attachment_actions()

    def _update_attachment_actions(self):
        if not hasattr(self, "import_pdf_button"):
            return
        available = self.mode == "view" and self.certificate_id is not None and self._render_context is None
        has_pages = bool(self.attachment_model.rows)
        self.import_pdf_button.setEnabled(available and not has_pages)
        self.replace_pdf_button.setEnabled(available and has_pages)
        self.delete_attachments_button.setEnabled(available and has_pages)

    def _choose_pdf(self, *, replace):
        if not self.certificate_id:
            return
        source, _ = QFileDialog.getOpenFileName(self, "选择整份 PDF", "", "PDF 文件 (*.pdf)")
        if source:
            try:
                self.start_pdf_import(source, replace=replace)
            except Exception as error:
                self.import_error.setText(f"PDF 导入失败：{friendly_database_error(error)}")

    def start_pdf_import(self, source, *, replace=False):
        """Enter inline preview; the source PDF is only opened read-only by PyMuPDF."""
        if self.certificate_id is None or self.mode != "view" or self._render_context is not None:
            raise ValueError("请先选择当前证书并结束其他编辑或导入")
        if bool(self.attachment_model.rows) != replace:
            raise ValueError("请使用与现有附件状态对应的导入或替换操作")
        context = render_pdf(source, self.settings_service.load())
        try:
            pages = context.__enter__()
        except Exception as error:
            self.import_error.setText(f"PDF 转换失败：{friendly_database_error(error)}")
            raise
        self._render_context = context
        self._pending_pages = pages
        self._pending_replace = replace
        self._pending_page_index = 0
        self.import_error.clear()
        self.confirm_import_button.setText("确认替换" if replace else "确认导入")
        self.people_view.setEnabled(False)
        self.certificates_view.setEnabled(False)
        self.search_input.setEnabled(False)
        self.import_preview.show()
        self._show_pending_page(0)
        self._update_attachment_actions()
        QTimer.singleShot(0, lambda: self.detail_scroll.ensureWidgetVisible(self.import_image))

    def _show_pending_page(self, index):
        if not 0 <= index < len(self._pending_pages):
            return
        self._pending_page_index = index
        page = self._pending_pages[index]
        self.import_page_label.setText(f"第 {page.number} / {len(self._pending_pages)} 页")
        pixmap = QPixmap(str(page.path))
        self.import_image.setPixmap(pixmap.scaled(
            self.import_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        self.previous_page_button.setEnabled(index > 0)
        self.next_page_button.setEnabled(index < len(self._pending_pages) - 1)

    def _rotate_pending(self, degrees):
        if not self._pending_pages:
            return
        try:
            rotate_temporary_page(self._pending_pages[self._pending_page_index], degrees,
                                  quality=self.settings_service.load().jpeg_quality)
            self._show_pending_page(self._pending_page_index)
        except Exception as error:
            self.import_error.setText(f"旋转失败：{friendly_database_error(error)}")

    def confirm_import(self):
        if self._render_context is None:
            return
        try:
            result = self.attachment_service.save_pages(
                self.certificate_id, self._pending_pages, replace=self._pending_replace
            )
        except Exception as error:
            self.import_error.setText(f"保存失败：{friendly_database_error(error)}")
            return
        replaced = self._pending_replace
        self.cancel_import()
        self._refresh_attachments()
        self.notify(f"已{'替换' if replaced else '导入'} {result.page_count} 页附件")
        if result.old_files_not_removed:
            self.import_error.setText("旧文件未能清理，请稍后检查：" + "、".join(result.old_files_not_removed))

    def _release_pending(self):
        if self._render_context is not None:
            context = self._render_context
            self._render_context = None
            self._pending_pages = ()
            context.__exit__(None, None, None)

    def cancel_import(self):
        self._release_pending()
        self.import_preview.hide()
        self.people_view.setEnabled(True)
        self.certificates_view.setEnabled(True)
        self.search_input.setEnabled(True)
        self._update_attachment_actions()

    def delete_attachments(self):
        if self.certificate_id is None or not self.attachment_model.rows:
            return
        count = len(self.attachment_model.rows)
        if QMessageBox.question(
            self, "确认删除附件", f"确定删除当前证书的整份附件（{count} 页）？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            result = self.attachment_service.delete_all(self.certificate_id)
        except Exception as error:
            self.import_error.setText(f"删除失败：{friendly_database_error(error)}")
            return
        self._refresh_attachments()
        self.notify(f"已删除 {result.page_count} 页附件")
        if result.old_files_not_removed:
            self.import_error.setText("图片未能清理：" + "、".join(result.old_files_not_removed))

    def _person_values(self):
        values = {}
        for field, editor in self.person_inputs.items():
            text = editor.text()
            old = self._original_person[field] if self._original_person else None
            values[field] = old if text == "" and old == "" else (text if text else None)
        return values

    def _certificate_values(self):
        values = {"人员ID": self.person_id}
        for field, editor in self.certificate_inputs.items():
            text = editor.currentText() if field == "证书类型" else editor.text()
            old = self._original_certificate[field] if self._original_certificate else None
            values[field] = old if text == "" and old == "" else (text if text else None)
        return values

    def new_person(self):
        if self.mode != "view" and not self._allow_switch():
            return
        self.person_id = None
        self.certificate_id = None
        self.people_view.clearSelection()
        self._load_person(None)
        self._load_certificate(None)
        self.certificate_model.set_rows([])
        self.attachment_model.set_rows([])
        self.preview.show_path(None)
        self._set_mode("new_person")
        self.person_inputs["姓名"].setFocus()

    def save_person(self):
        if self.mode not in ("new_person", "edit_person"):
            return
        try:
            values = self._person_values()
            new_record = self.mode == "new_person"
            if new_record:
                self.person_id = self.service.add_person(values)
            else:
                self.service.update_person(self.person_id, values)
        except Exception as error:
            QMessageBox.warning(self, "保存人员失败", friendly_database_error(error))
            return
        self._set_mode("view")
        self._load_person(self.service.people.get(self.person_id))
        if new_record:
            self.search_input.clear()
        self.refresh_people(select_id=self.person_id)

    def new_certificate(self):
        if self.person_id is None or (self.mode != "view" and not self._allow_switch()):
            return
        self.certificate_id = None
        self.certificates_view.clearSelection()
        self._load_certificate(None)
        self.attachment_model.set_rows([])
        self.preview.show_path(None)
        self._set_mode("new_certificate")
        self.certificate_inputs["证书名称"].setFocus()

    def save_certificate(self):
        if self.mode not in ("new_certificate", "edit_certificate"):
            return
        try:
            values = self._certificate_values()
            if self.mode == "new_certificate":
                self.certificate_id = self.service.add_certificate(values)
            else:
                self.service.update_certificate(self.certificate_id, values)
        except Exception as error:
            QMessageBox.warning(self, "保存证书失败", friendly_database_error(error))
            return
        self._set_mode("view")
        self._load_certificate(self.service.certificates.get(self.certificate_id))
        self._refresh_certificates(select_id=self.certificate_id)

    def cancel(self):
        if self.mode == "view":
            return
        if not self.can_leave():
            return
        self.discard_changes()

    def delete_person(self):
        if self.person_id is None:
            return
        dependencies = self.service.people.dependencies(self.person_id)
        details = "、".join(f"{name} {count} 条" for name, count in dependencies.items() if count)
        if details:
            QMessageBox.warning(self, "无法删除人员", f"该人员仍关联{details}。请先处理关联记录。")
            return
        if QMessageBox.question(self, "确认删除", "确定删除当前人员？", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.service.delete_person(self.person_id)
        except Exception as error:
            QMessageBox.warning(self, "删除人员失败", friendly_database_error(error))
            return
        self.person_id = None
        self.refresh_people()

    def delete_certificate(self):
        if self.certificate_id is None:
            return
        dependencies = self.service.certificates.dependencies(self.certificate_id)
        details = "、".join(f"{name} {count} 条" for name, count in dependencies.items() if count)
        if details:
            QMessageBox.warning(self, "无法删除证书", f"该证书仍关联{details}。请先处理关联记录。")
            return
        if QMessageBox.question(self, "确认删除", "确定删除当前证书？", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.service.delete_certificate(self.certificate_id)
        except Exception as error:
            QMessageBox.warning(self, "删除证书失败", friendly_database_error(error))
            return
        self.certificate_id = None
        self._refresh_certificates()
