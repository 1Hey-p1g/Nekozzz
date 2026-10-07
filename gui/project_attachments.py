"""Inline engineering PDF preview, using the existing renderer and publisher."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from gui.common import ImagePreview, RowsModel, table_view
from services.pdf_import import render_pdf, rotate_temporary_page


class ProjectAttachmentEditor(QWidget):
    pending_changed = Signal(bool)
    saved = Signal()

    def __init__(self, repository, publisher, settings, notify, *, describe_group=None,
                 delete_button_text='删除当前类型整份附件',
                 group_error='请先选择已保存工程和有效文件类型', large_view_enabled=False):
        super().__init__()
        self.repository, self.publisher, self.settings, self.notify = repository, publisher, settings, notify
        self.describe_group = describe_group or (
            lambda group: f"工程“{self.repository.get(group[0])['项目名称']}”的“{group[1]}”")
        self.group_error = group_error
        self.group = None
        self.context = None
        self.pages = ()
        self.page_index = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        actions = QHBoxLayout()
        self.import_button = QPushButton('导入 / 替换 PDF')
        self.delete_button = QPushButton(delete_button_text)
        actions.addWidget(self.import_button)
        actions.addWidget(self.delete_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.model = RowsModel([('页序', '备注'), ('路径', '路径')], self)
        self.view = table_view(self.model)
        self.view.setMinimumHeight(100)
        layout.addWidget(self.view)
        self.preview = ImagePreview(data_root=publisher.data_root, large_view_enabled=large_view_enabled)
        layout.addWidget(self.preview)
        self.pending = QWidget()
        pending_layout = QVBoxLayout(self.pending)
        self.page_label = QLabel()
        self.pending_image = QLabel()
        self.pending_image.setAlignment(Qt.AlignCenter)
        self.pending_image.setMinimumHeight(190)
        pending_layout.addWidget(self.page_label)
        pending_layout.addWidget(self.pending_image)
        controls = QHBoxLayout()
        for text, callback in (
            ('上一页', lambda: self.show_page(self.page_index - 1)),
            ('下一页', lambda: self.show_page(self.page_index + 1)),
            ('向左旋转 90°', lambda: self.rotate(-90)),
            ('向右旋转 90°', lambda: self.rotate(90)),
            ('确认导入', self.confirm_import), ('取消', self.cancel_import),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        pending_layout.addLayout(controls)
        layout.addWidget(self.pending)
        self.pending.hide()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #ae3131')
        layout.addWidget(self.error_label)
        self.import_button.clicked.connect(self.choose_pdf)
        self.delete_button.clicked.connect(self.delete_all)
        self.view.selectionModel().currentRowChanged.connect(self.show_attachment)
        QApplication.instance().aboutToQuit.connect(self.release)
        self.set_group(None)

    def set_group(self, group):
        if self.context is not None:
            raise ValueError('请先确认或取消当前 PDF 导入')
        self.group = group
        self.refresh()

    def refresh(self):
        pages = self.repository.attachments(*self.group) if self.group else []
        self.model.set_rows(pages)
        self.preview.show_path(None)
        if pages:
            self.view.selectRow(0)
        self.import_button.setEnabled(self.group is not None and self.context is None)
        self.delete_button.setEnabled(bool(pages) and self.context is None)

    def show_attachment(self, current, _previous):
        row = self.model.record(current)
        self.preview.show_path(row['路径'] if row else None)

    def choose_pdf(self):
        source, _ = QFileDialog.getOpenFileName(self, '选择整份 PDF', '', 'PDF 文件 (*.pdf)')
        if source:
            try:
                self.start_pdf_import(source)
            except Exception as error:
                self.error_label.setText(f'PDF 导入失败：{error}')

    def start_pdf_import(self, source):
        if self.group is None or self.context is not None:
            raise ValueError(self.group_error)
        context = render_pdf(source, self.settings.load())
        try:
            pages = context.__enter__()
            self.context, self.pages = context, pages
            self.replace = bool(self.model.rows)
            self.pending.show()
            self.show_page(0)
            self.import_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            self.error_label.clear()
            self.pending_changed.emit(True)
        except BaseException:
            context.__exit__(None, None, None)
            self.context, self.pages = None, ()
            raise

    def show_page(self, index):
        if not 0 <= index < len(self.pages):
            return
        self.page_index = index
        self.page_label.setText(f'第 {index + 1} / {len(self.pages)} 页 · 确认前不修改附件')
        self.pending_image.setPixmap(QPixmap(str(self.pages[index].path)).scaled(
            self.pending_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def rotate(self, degrees):
        try:
            rotate_temporary_page(self.pages[self.page_index], degrees, quality=self.settings.load().jpeg_quality)
            self.show_page(self.page_index)
        except Exception as error:
            self.error_label.setText(f'旋转失败：{error}')

    def confirm_import(self):
        if self.context is None:
            return
        try:
            result = self.publisher.save_pages(self.group, self.pages, replace=self.replace)
        except Exception as error:
            self.error_label.setText(f'保存失败：{error}')
            return
        verb = '替换' if self.replace else '导入'
        self.cancel_import()
        self.refresh()
        self.saved.emit()
        self.notify(f'已{verb} {result.page_count} 页附件')
        if result.old_files_not_removed:
            self.error_label.setText('旧文件未能清理：' + '、'.join(result.old_files_not_removed))

    def release(self):
        if self.context is not None:
            context, self.context = self.context, None
            self.pages = ()
            context.__exit__(None, None, None)

    def cancel_import(self):
        self.release()
        self.pending.hide()
        self.pending_changed.emit(False)
        self.refresh()

    def can_leave(self):
        if self.context is None:
            return True
        if QMessageBox.question(self, '未保存附件', '放弃当前 PDF 导入并清理临时图片？',
                                QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Discard:
            return False
        self.cancel_import()
        return True

    def delete_all(self):
        if not self.group or not self.model.rows:
            return
        if QMessageBox.question(self, '确认删除附件',
                                f"删除{self.describe_group(self.group)}整份附件？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            result = self.publisher.delete_all(self.group)
            self.refresh()
            self.saved.emit()
            self.notify(f'已删除 {result.page_count} 页附件')
            if result.old_files_not_removed:
                self.error_label.setText('图片未能清理：' + '、'.join(result.old_files_not_removed))
        except Exception as error:
            self.error_label.setText(f'删除失败：{error}')
