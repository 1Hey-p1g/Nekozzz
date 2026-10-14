"""Designer-compatible window with once-only page factories and close protection."""
from PySide6.QtCore import QEvent, QObject, QThread
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QMainWindow
from gui.window_geometry import save_window_geometry

MANAGE_PAGES = ('manage_page', 'project_manage_page', 'qualification_manage_page', 'award_finance_manage_page')

class LazyMainWindow(QMainWindow):
    def __getattr__(self, name):
        factories = self.__dict__.get('_page_factories', {})
        if name in factories:
            return self.get_page(name)
        if name in ('award_manage_page', 'finance_manage_page') and factories:
            self.get_page('award_finance_manage_page')
            return self.created_pages[name]
        if name == 'data_management_controller' and factories:
            self.get_page('settings_page')
            return self.__dict__[name]
        raise AttributeError(name)

    def get_page(self, name):
        if name not in self.created_pages:
            if QThread.currentThread() != self.thread():
                raise RuntimeError('业务页面必须在 GUI 主线程创建')
            if getattr(self, '_data_operation_running', False) or getattr(self, '_restore_completed', False) or getattr(self, '_data_recovery_required', False):
                raise RuntimeError('数据维护期间不能创建业务页面')
            page = self._page_factories[name]()
            self.created_pages[name] = page
            self.workspace.addWidget(page)
        return self.created_pages[name]

    def managed_pages(self):
        return tuple(self.created_pages[name] for name in MANAGE_PAGES if name in self.created_pages)

class WindowLoader(QUiLoader):
    def createWidget(self, class_name, parent=None, name=''):
        if class_name == 'QMainWindow' and parent is None:
            window = LazyMainWindow()
            window.setObjectName(name)
            return window
        return super().createWidget(class_name, parent, name)

class CloseGuard(QObject):
    def __init__(self, window, settings):
        super().__init__(window)
        self.window, self.settings = window, settings

    @property
    def manage_pages(self):
        return self.window.managed_pages()

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Close:
            return False
        if getattr(obj, '_data_operation_running', False):
            event.ignore()
            return True
        if getattr(obj, '_restore_completed', False) or getattr(obj, '_data_recovery_required', False):
            return False  # Never save old preferences over restored settings.
        if not all(page.can_leave() for page in self.manage_pages):
            event.ignore()
            return True
        try:
            save_window_geometry(obj, self.settings)
            obj.geometry_persistence_error = ''
        except (OSError, ValueError, TypeError) as error:
            obj.geometry_persistence_error = str(error)
            obj.statusBar().showMessage(f'窗口位置未保存：{error}')
        return False
