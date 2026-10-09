"""Small dialogs/controller for explicit data management in the Settings card."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QVBoxLayout, QCheckBox,
)

from services.backup import new_output_path, RestoreRecoveryRequiredError
from version import APP_NAME, DB_SCHEMA_VERSION


class _OperationThread(QThread):
    result = Signal(object)
    failure = Signal(object)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.result.emit(self.operation())
        except Exception as error:
            self.failure.emit(error)


class _OperationDialog(QDialog):
    def __init__(self, parent, operation, message):
        super().__init__(parent)
        self.setWindowTitle('数据管理')
        self.setWindowModality(Qt.ApplicationModal)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(message))
        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)
        self.value, self.error = None, None
        self.worker = _OperationThread(operation, self)
        self.worker.result.connect(self.succeeded)
        self.worker.failure.connect(self.failed)
        self.worker.finished.connect(self.accept)

    @Slot(object)
    def succeeded(self, value):
        self.value = value

    @Slot(object)
    def failed(self, error):
        self.error = error

    def reject(self):
        if not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)


def run_operation(parent, operation, message):
    """No SQLite connection crosses threads; worker opens and closes its own."""
    window = parent.window()
    window._data_operation_running = True
    dialog = _OperationDialog(parent, operation, message)
    try:
        dialog.worker.start()
        dialog.exec()
        dialog.worker.wait()
        if dialog.error is not None:
            raise dialog.error
        return dialog.value
    finally:
        window._data_operation_running = False
        dialog.deleteLater()


class AccessMigrationDialog(QDialog):
    def __init__(self, parent, service, *, prepare_current=None):
        super().__init__(parent)
        self.service = service
        self.prepare_current = prepare_current or (lambda: True)
        self.setWindowTitle('Access 一次性迁移')
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)
        hint = QLabel('仅生成新的 SQLite；不会修改 Access，也不会切换当前数据库。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.source, self.target = QLineEdit(), QLineEdit()
        for title, editor, handler in (('Access 源文件', self.source, self.choose_source),
                                      ('目标 SQLite', self.target, self.choose_target)):
            row = QHBoxLayout()
            row.addWidget(editor, 1)
            button = QPushButton('浏览')
            button.clicked.connect(handler)
            if editor is self.target:
                self.target_button = button
            row.addWidget(button)
            form.addRow(title, row)
        layout.addLayout(form)
        self.use_current = QCheckBox('迁移并作为当前数据库使用（成功后重启）')
        eligible = service.can_migrate_as_current()
        self.use_current.setEnabled(eligible)
        self.use_current.setChecked(eligible)
        self.use_current.setToolTip('仅当前 portable 默认 V1 空库允许替换；非空库只能独立迁移')
        def mode_changed(checked):
            self.target.setEnabled(not checked)
            self.target_button.setEnabled(not checked)
            self.target.setPlaceholderText(str(service.database_path) if checked else '请选择尚不存在的新 SQLite')
            hint.setText('迁移先在独立新库中验证，仅成功后替换当前默认空库；不会修改 Access。'
                         if checked else '仅生成新的 SQLite；不会修改 Access，也不会切换当前数据库。')
        self.use_current.toggled.connect(mode_changed)
        mode_changed(eligible)
        layout.addWidget(self.use_current)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.result_label)
        actions = QHBoxLayout()
        self.start_button = QPushButton('开始迁移')
        self.start_button.clicked.connect(self.start)
        close = QPushButton('关闭')
        close.clicked.connect(self.reject)
        actions.addStretch()
        actions.addWidget(self.start_button)
        actions.addWidget(close)
        layout.addLayout(actions)

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择 Access 源文件', '', 'Access (*.accdb *.mdb)')
        if path:
            self.source.setText(path)

    def choose_target(self):
        path, _ = QFileDialog.getSaveFileName(self, '选择尚不存在的 SQLite', '', 'SQLite (*.db)',
                                            options=QFileDialog.DontConfirmOverwrite)
        if path:
            self.target.setText(path)

    def start(self):
        try:
            current = self.use_current.isChecked()
            if not self.source.text().strip() or (not current and not self.target.text().strip()):
                raise ValueError('请指定 Access 源文件和新的 SQLite 目标文件')
            if current:
                if not self.service.can_migrate_as_current():
                    raise ValueError('当前数据库不再是可安全替换的默认 V1 空库')
                source = Path(self.source.text().strip()).expanduser().resolve()
                target = self.service.database_path
                if not source.is_file():
                    raise FileNotFoundError(f'Access 源文件不存在：{source}')
            else:
                source, target = self.service.check_migration(self.source.text().strip(), self.target.text().strip())
            if QMessageBox.question(self, '确认一次性迁移',
                f'Access：\n{source}\n\n输出 SQLite：\n{target}\n\n'
                + ('迁移不会修改原 Access。验证成功后将替换当前默认空数据库，并退出以便重新启动。'
                   if current else '迁移不会修改原 Access 数据库，也不会替换当前 Nekozzz 数据库。'),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            if current and not self.prepare_current():
                return
            self.start_button.setEnabled(False)
            result = run_operation(self, lambda: self.service.migrate_as_current(source) if current
                                   else self.service.migrate(source, target), '正在迁移并验证数据，请稍候…')
            if current:
                window = self.parentWidget().window()
                window._restore_completed = True  # Existing close guard skips stale repository reads.
                window.setEnabled(False)
                QMessageBox.information(self, '首次迁移完成', '迁移成功，已替换默认空数据库。请重新启动 Nekozzz。')
                self.accept()
                window.close()
                return
            self.result_label.setText(f'迁移成功\n目标：{target}\nDB Schema Version：{DB_SCHEMA_VERSION}\n'
                                     f'业务记录：{result.get("rows", "—")}\n当前数据库未切换。')
        except Exception as error:
            if isinstance(error, RestoreRecoveryRequiredError):
                window = self.parentWidget().window()
                window._data_recovery_required = True
                QMessageBox.critical(self, '首次迁移未完成', str(error))
                self.accept()
                window.close()
                return
            self.result_label.setText(f'迁移失败：{error}')
        finally:
            self.start_button.setEnabled(True)


class DataManagementController:
    def __init__(self, window, page, service, notify, prepare_restore):
        self.window, self.page, self.service, self.notify = window, page, service, notify
        self.prepare_restore = prepare_restore
        for name, handler in (('accessImport', self.migrate), ('backupDatabase', self.backup),
                              ('restoreDatabase', self.restore), ('exportPeople', self.export_people)):
            page.findChild(QPushButton, name).clicked.connect(handler)

    def migrate(self):
        dialog = AccessMigrationDialog(self.window, self.service, prepare_current=self.prepare_restore)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def _save_path(self, title, default, filter):
        path, _ = QFileDialog.getSaveFileName(self.window, title, default, filter,
                                            options=QFileDialog.DontConfirmOverwrite)
        if path:
            new_output_path(path)  # Always refuse existing output, no overwrite branch.
        return path

    def backup(self):
        try:
            stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
            path = self._save_path('创建完整备份', f'{APP_NAME}_Backup_{stamp}.zip', '完整备份 (*.zip)')
            if not path:
                return
            run_operation(self.window, lambda: self.service.backups.create_backup(path), '正在创建一致性快照和完整备份…')
        except Exception as error:
            self.page.error_label.setText(f'备份失败：{error}')
        else:
            self.page.error_label.clear()
            self.notify('完整备份已创建')

    def export_people(self):
        try:
            path = self._save_path('导出人员表 Excel', '人员表.xlsx', 'Excel (*.xlsx)')
            if not path:
                return
            _, count = run_operation(self.window, lambda: self.service.export_people(path), '正在导出人员表…')
        except Exception as error:
            self.page.error_label.setText(f'人员表导出失败：{error}')
        else:
            self.page.error_label.clear()
            self.notify(f'已导出 {count} 条人员资料')

    def restore(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self.window, '选择完整备份', '', '完整备份 (*.zip)')
            if not path:
                return
            info = run_operation(self.window, lambda: self.service.backups.inspect_backup(path), '正在验证备份，请稍候…')
            manifest = info.manifest
            settings_text = '恢复备份中的设置' if manifest['includes_settings'] else '未包含设置，保留当前设置'
            attachment_warning = (f'注意：备份中有 {len(info.missing_images)} 个附件引用缺少实体文件；恢复后仍会缺失。\n'
                                  if info.missing_images else '')
            if QMessageBox.question(self.window, '确认恢复完整备份',
                f'备份时间：{manifest["created_at"]}\n创建版本：{manifest["app_version"]}\n'
                f'数据库版本：{manifest["database_version"]}\nImages：完整包含\nSettings：{settings_text}\n\n'
                '备份格式与数据库结构校验已通过；创建时的应用版本无需与当前版本相同。\n'
                + attachment_warning +
                '恢复将替换当前 Nekozzz 数据库、Images 和设置（未包含设置时保留当前设置）。\n'
                '恢复前会自动创建 Safety Backup。成功后程序退出，请重新启动。',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            if not self.prepare_restore():
                return
            # Finish any pending style editing before replacing settings. Keep
            # preference controls disabled so focus restoration cannot save the
            # old UI values over the restored settings.json.
            self.page.setEnabled(False)
            result = run_operation(self.window,
                lambda: self.service.backups.restore_backup(path, expected_digest=info.sha256),
                '正在创建 Safety Backup 并恢复；请勿中断…')
        except Exception as error:
            if isinstance(error, RestoreRecoveryRequiredError):
                self.window._data_recovery_required = True
                self.window.setEnabled(False)
                QMessageBox.critical(self.window, '恢复未完成',
                    f'{error}\n\n程序将退出。请保留 Safety Backup 和上述目录，恢复数据后再启动。')
                self.window.close()
                return
            self.page.setEnabled(True)
            self.page.error_label.setText(f'恢复失败：{error}')
        else:
            # No repository/page refresh or settings save after restored files land.
            self.window._restore_completed = True
            self.window.setEnabled(False)
            QMessageBox.information(self.window, '恢复完成',
                                    f'恢复完成，请重新启动 Nekozzz。\nSafety Backup：{result.safety_backup}')
            self.window.close()
