"""Shared, one-shot GUI confirmation for missing Word styles."""

from PySide6.QtWidgets import QMessageBox
from services.office_writer import writer_name


def confirm_style_fallback(parent, missing):
    lines = '\n'.join(f'{label}：{name}' for label, name in missing)
    settings = getattr(parent, 'settings_service', None)
    name = writer_name(settings.load().writer_target if settings is not None else 'word')
    return QMessageBox.question(
        parent, '文档样式缺失',
        f'当前 {name} 文档缺少以下样式：\n\n' + lines +
        '\n\n是否将缺失的样式仅在本次插入中改用内置“正文”样式？',
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
    ) == QMessageBox.Yes
