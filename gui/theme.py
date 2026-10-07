"""Shared colors and native DWM caption; retain Windows window management."""
import re
import sys
from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

DARK_COLORS = dict(zip(
    ('#f6f8fb','#1e293b','#15243b','#23405d','#324b68','#64748b','#dce4ed','#d1dbe7',
     '#cbd7e4','#e9eff6','#d4deea','#e8eef5','#395575','#f1f4f8','#fbfdff','#eef3f8',
     '#e2eaf3','#dceafa','#cfe3fa','#f1f5f9','#eaf1f8','#eaf1f9','#356397','#ae3131',
     '#ffffff','#fff'),
    ('#182230','#e2e8f0','#e2e8f0','#d5e2f0','#c5d5e7','#9baec4','#3b4c60','#40536b',
     '#40536b','#2a394c','#40536b','#223044','#b3c7df','#263447','#2a3a4f','#2a394c',
     '#35475e','#354f70','#354f70','#27364a','#30445d','#30445d','#91b9e6','#ef9a9a',
     '#223044','#223044')))
DARK_COLORS.update({'#fbecee':'#3f2b35', '#f4dce0':'#50323f',
                    '#923e47':'#efb1b7', '#7d303a':'#f2bfc5', '#45627f':'#adc5e1'})

def system_theme():
    if sys.platform == 'win32':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                return 'light' if winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] else 'dark'
        except OSError:
            pass
    return 'light'

def resolve_theme(preference):
    return system_theme() if preference == 'system' else preference if preference in ('light','dark') else 'light'

def dark_stylesheet(source):
    source = re.sub(r'background\s*:\s*white\b', 'background: #223044', source, flags=re.I)
    return re.sub(r'#[0-9a-fA-F]{3,8}\b', lambda m: DARK_COLORS.get(m[0].lower(),m[0]),source)

def native_caption(widget, dark):
    if sys.platform != 'win32' or not widget.isWindow():
        return
    import ctypes
    try:
        setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        for attribute, value in ((20,int(dark)),(35,0x302218 if dark else 0xfbf8f6),
                                 (36,0xf0e8e2 if dark else 0x3b291e),
                                 (34,0x604c3b if dark else 0xede4dc)):
            data = ctypes.c_uint(value)
            setter(int(widget.winId()),attribute,ctypes.byref(data),ctypes.sizeof(data))
    except (OSError,AttributeError):
        pass  # Unsupported DWM attributes on older Windows do not affect resizing.

class ThemeManager(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.dark = app, False
        self.original_palette = QPalette(app.palette())
        app.installEventFilter(self)

    def apply(self, preference):
        dark = resolve_theme(preference) == 'dark'
        if getattr(self,'_applied',False) and self.dark == dark:
            return
        self._applied = True
        self.dark = dark
        palette = QPalette(self.original_palette)
        if self.dark:
            for role,color in ((QPalette.Window,'#182230'),(QPalette.WindowText,'#e2e8f0'),
                (QPalette.Base,'#223044'),(QPalette.AlternateBase,'#27364a'),
                (QPalette.Text,'#e2e8f0'),(QPalette.Button,'#223044'),
                (QPalette.ButtonText,'#e2e8f0'),(QPalette.Highlight,'#354f70'),
                (QPalette.HighlightedText,'#e2e8f0'),(QPalette.ToolTipBase,'#223044'),
                (QPalette.ToolTipText,'#e2e8f0')):
                palette.setColor(role,QColor(color))
        self.app.setPalette(palette)
        base = '''QDialog, QMessageBox, QScrollArea, QTabWidget::pane { background: #f6f8fb; color: #1e293b; }
QWidget { color: #1e293b; } QTextEdit, QPlainTextEdit, QListWidget { background: white; color: #1e293b; }
QTabBar::tab { background: #e9eff6; } QTabBar::tab:selected { background: white; }
QScrollBar { background: #f1f4f8; } QScrollBar::handle { background: #96aec9; border-radius: 4px; }
QScrollBar::add-page, QScrollBar::sub-page { background: #f1f4f8; }
QToolButton { background: #eef3f8; color: #23405d; }'''
        self.app.setStyleSheet(dark_stylesheet(base) if self.dark else base)
        for widget in QApplication.allWidgets():
            self._style(widget)
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible():
                native_caption(widget,self.dark)

    def _style(self, widget):
        if not hasattr(widget,'_theme_source_style'):
            widget._theme_source_style = widget.styleSheet()
        source = widget._theme_source_style
        wanted = dark_stylesheet(source) if self.dark else source
        if widget.styleSheet() != wanted:
            widget.setStyleSheet(wanted)

    def eventFilter(self,obj,event):
        if isinstance(obj,QWidget) and event.type() == QEvent.Show:
            self._style(obj)
            native_caption(obj,self.dark)
        return False
