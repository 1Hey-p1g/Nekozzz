"""Shared, one-shot GUI confirmation for missing Word styles."""

from PySide6.QtWidgets import QMessageBox


def confirm_style_fallback(parent, missing):
    lines = '\n'.join(f'{label}：{name}' for label, name in missing)
    return QMessageBox.question(
        parent, 'Word 样式缺失',
        '当前 Word 文档缺少以下样式：\n\n' + lines +
        '\n\n是否将缺失的样式仅在本次插入中改用 Word“正文”样式？',
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
    ) == QMessageBox.Yes
