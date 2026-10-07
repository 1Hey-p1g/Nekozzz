"""Reusable in-workspace clipboard feedback, without a separate window."""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel


class CopyToast(QLabel):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.setObjectName("copyToast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(
            "QLabel#copyToast { background: #203b5b; color: white; border-radius: 8px; "
            "padding: 9px 14px; font-weight: 600; }"
        )
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        workspace.installEventFilter(self)
        self.hide()

    def copy(self, value):
        """Copy the complete value; display an elided confirmation for one second."""
        if value is None or value == "":
            return False
        full_text = str(value)
        QGuiApplication.clipboard().setText(full_text)
        shortened = self.fontMetrics().elidedText(full_text.replace("\n", " "), Qt.ElideRight, 280)
        self.show_message(f"✓ 已复制：{shortened}", max_width=1000)
        return True

    def show_message(self, message, *, max_width=330):
        shortened = self.fontMetrics().elidedText(str(message).replace("\n", " "), Qt.ElideRight, max_width)
        self.setText(shortened)
        self.adjustSize()
        self._position()
        self.raise_()
        self.show()
        self._timer.start(1000)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Resize:
            self._position()
        return super().eventFilter(watched, event)

    def _position(self):
        if self.parentWidget() is not None:
            self.move(max(0, self.parentWidget().width() - self.width() - 18),
                      max(0, self.parentWidget().height() - self.height() - 18))
