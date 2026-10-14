"""Qt's versioned geometry blob in existing portable preferences."""
import base64
from dataclasses import replace
from PySide6.QtCore import QByteArray, QRect, Qt
from PySide6.QtGui import QGuiApplication

def restore_window_geometry(window, settings):
    default_geometry = window.geometry()
    default_state = window.windowState()
    encoded = settings.load().window_geometry
    if not encoded:
        return False
    try:
        raw = base64.b64decode(encoded, validate=True)
        if not raw or not window.restoreGeometry(QByteArray(raw)):
            raise ValueError('Invalid Qt geometry')
        screens = QGuiApplication.screens()
        normal = window.normalGeometry() if window.isMaximized() else window.frameGeometry()
        if screens and not any(screen.availableGeometry().intersects(normal) for screen in screens):
            maximized = window.isMaximized()
            available = QGuiApplication.primaryScreen().availableGeometry()
            window.setWindowState(window.windowState() & ~Qt.WindowMaximized)
            width = min(max(200, normal.width()), available.width())
            height = min(max(150, normal.height()), available.height())
            window.setGeometry(QRect(available.x(), available.y(), width, height))
            if maximized:
                window.setWindowState(window.windowState() | Qt.WindowMaximized)
        return True
    except (ValueError, TypeError):
        window.setWindowState(default_state)
        window.setGeometry(default_geometry)
        return False

def save_window_geometry(window, settings):
    geometry = base64.b64encode(bytes(window.saveGeometry())).decode('ascii')
    settings.save(replace(settings.load(), window_geometry=geometry))
