"""Pure application identity display; no business state or settings."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from config.paths import resource_path
from version import APP_NAME, APP_VERSION, APP_SUBTITLE, APP_COPYRIGHT


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addStretch()
        block = QWidget(self)
        identity = QVBoxLayout(block)
        identity.setContentsMargins(24, 0, 24, 0)
        identity.setSpacing(12)
        self.icon = QLabel()
        self.icon.setPixmap(QPixmap(str(resource_path('resources/icon.png'))).scaled(
            96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        identity.addWidget(self.icon, alignment=Qt.AlignHCenter)
        for text, name in (
            (APP_NAME, 'pageTitle'),
            (APP_SUBTITLE, 'subtitle'),
            (f'Version {APP_VERSION}', 'subtitle'),
            ('Developed by 1Hey-p1g', 'subtitle'),
            (APP_COPYRIGHT, 'subtitle'),
            ('Licensed under the GNU Affero General Public License v3.0', 'subtitle'),
        ):
            label = QLabel(text)
            label.setObjectName(name)
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)
            identity.addWidget(label)
        layout.addWidget(block)
        layout.addStretch()
