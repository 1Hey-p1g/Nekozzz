"""Explicit running Writer selection; no launch, document creation or fallback."""
from threading import current_thread, main_thread

import pywintypes
from win32com.client import GetActiveObject

from services.word_service import WordService, WordNotRunningError, WordNoActiveDocumentError, WordOperationError

WRITER_TARGETS = {'word': ('Microsoft Word', 'Word.Application'),
                  'wps': ('WPS Writer', 'KWPS.Application')}


def writer_name(target):
    return WRITER_TARGETS[target][0]


def writer_error_message(error, target):
    name = writer_name(target)
    if isinstance(error, WordNotRunningError):
        return f'未检测到正在运行的 {name}，请先打开目标文档并放置光标。' + (f'\n{error}' if str(error) else '')
    if isinstance(error, WordNoActiveDocumentError):
        return f'{name} 当前没有活动文档，请先打开目标文档。'
    message = str(error).replace('Microsoft Word', name).replace('Word', name) if target == 'wps' else str(error)
    cause = error
    while cause.__cause__ is not None:
        cause = cause.__cause__
    if isinstance(cause, pywintypes.com_error) and str(cause) not in message:
        message += f'\nCOM：{cause}'
    return message


class OfficeWriterConnector:
    """Resolve preference at each operation; never cache/pass COM across threads.

    GUI insertions run synchronously on the main thread, where pywin32 initializes
    COM on import. No worker COM initialization/lifetime is added here.
    """
    def __init__(self, settings_service, get_active_object=None):
        self.settings_service = settings_service
        self.get_active_object = get_active_object or GetActiveObject

    def __call__(self):
        if current_thread() is not main_thread():
            raise WordOperationError('文档插入必须在 GUI 主线程连接和使用 Office，请重试。')
        target = self.settings_service.load().writer_target
        name, progid = WRITER_TARGETS[target]
        try:
            application = self.get_active_object(progid)
        except pywintypes.com_error as error:
            raise WordNotRunningError(f'{name} 连接失败（{progid}）：{error}') from error
        if application is None:
            raise WordNotRunningError(f'{name} 未运行（{progid}）')
        return WordService(application, application_name=name)
