"""External test script executed by an instrumented candidate EXE, in TEMP only.

Uses frozen application modules, not the development interpreter. No real Word
write and no real IME claim. The normal candidate and diagnostic twin must have
identical native binaries before results may be used as pruning evidence.
"""
import json
import os
from pathlib import Path
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader, QInputMethodEvent, QKeyEvent, QPixmap
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QMainWindow, QPushButton, QStackedWidget

app = QApplication.instance()
result = dict(status='FAIL', checks={}, manual_verification=[], frozen=bool(getattr(sys, 'frozen', False)))


def checked(name, condition):
    if not condition:
        raise AssertionError(name)
    result['checks'][name] = True


try:
    from config.paths import DATA_ROOT, resource_path
    from database.runtime import runtime_connection
    from services.people import PeopleService
    from services.settings import PdfSettings
    from services.data_management import DataManagementService
    from services.pdf_import import render_pdf, rotate_temporary_page
    from services.autofill.person_service import PersonAutoFillService
    from services.autofill.person_task import PersonAutoFillTask
    from services.person_word import PersonWordJob, PersonWordOutputService
    from services.word_service import WordService
    from gui.common import ImagePreview
    import pymupdf
    import openpyxl

    checked('running_frozen_interpreter', result['frozen'])
    checked('windows_platform_plugin', app.platformName() == 'windows')
    window = next(w for w in app.topLevelWidgets() if isinstance(w, QMainWindow))
    checked('main_window_visible', window.isVisible())
    db = DATA_ROOT / 'database/TenderSystem-v1.db'
    with runtime_connection(db) as connection:
        checked('first_launch_schema_1', connection.execute('PRAGMA user_version').fetchone()[0] == 1)
        checked('first_launch_empty_personnel', connection.execute('SELECT count(*) FROM 人员表').fetchone()[0] == 0)
    stack = window.findChild(QStackedWidget, 'workspace')
    for name in ('navPersonSearch', 'navProjectSearch', 'navQualSearch', 'navAwardSearch', 'navFinanceSearch',
                 'navPersonAutoFill', 'navPersonManage', 'navQualManage', 'navProjectManage',
                 'navAwardFinanceManage', 'navSettings', 'navAbout'):
        button = window.findChild(QPushButton, name)
        button.click()
        app.processEvents()
        checked('navigation_' + name, button.isChecked() and stack.currentWidget().isVisible())
    checked('about_page', stack.currentWidget() is window.about_page)
    checked('about_icon_png', not window.about_page.icon.pixmap().isNull())
    for theme in ('light', 'dark', 'system'):
        app.theme_manager.apply(theme)
        app.processEvents()
        checked('theme_' + theme, window.isVisible())

    # Exercise LineEdit/key events and editable ComboBox input; synthetic IME
    # commit verifies Qt event handling but is NOT a real TSF composition test.
    inputs = [QLineEdit(window)]
    combo = QComboBox(window)
    combo.setEditable(True)
    combo.addItems(['first', 'second'])
    combo.setCurrentIndex(1)
    checked('combo_selection', combo.currentText() == 'second')
    inputs.append(combo.lineEdit())
    for index, edit in enumerate(inputs):
        edit.clear()
        app.sendEvent(edit, QKeyEvent(QKeyEvent.KeyPress, Qt.Key_A, Qt.NoModifier, 'a'))
        app.sendEvent(edit, QKeyEvent(QKeyEvent.KeyRelease, Qt.Key_A, Qt.NoModifier, 'a'))
        event = QInputMethodEvent()
        event.setCommitString('中文输入')
        app.sendEvent(edit, event)
        checked('text_and_synthetic_input_method_' + str(index), edit.text() == 'a中文输入')
    result['manual_verification'].append('Real Windows Chinese IME/TSF preedit/candidate selection/commit not performed')

    checked('resource_png', not QPixmap(str(resource_path('resources/icon.png'))).isNull())
    checked('packaged_icon_png', not QPixmap(str(Path(sys.executable).parent / '_internal/resources/icon.png')).isNull())
    # ICO is not normally a data asset: decode a test ICO copied from the
    # unchanged official resource, without collecting additional modules.
    fixture = Path(os.environ['NEKOZZZ_PRUNE_ICO'])
    checked('ico_decode', not QPixmap(str(fixture)).isNull())
    image_dir = DATA_ROOT / 'Images'
    image_dir.mkdir(exist_ok=True)
    image = QImage(72, 48, QImage.Format_RGB32)
    image.fill(Qt.red)
    for extension in ('png', 'jpg'):
        path = image_dir / ('probe.' + extension)
        checked(extension + '_encode', image.save(str(path)))
        checked(extension + '_decode', not QImage(str(path)).isNull())
        preview = ImagePreview(data_root=DATA_ROOT)
        preview.show_path('Images/' + path.name)
        checked(extension + '_image_preview', preview._pixmap is not None and not preview._pixmap.isNull())
        preview.deleteLater()
    preview = ImagePreview(data_root=DATA_ROOT)
    preview.show_path('Images/missing.jpg')
    checked('missing_image_placeholder', preview._pixmap is None and bool(preview.text()))
    preview.deleteLater()
    result['image_formats'] = [bytes(x).decode() for x in QImageReader.supportedImageFormats()]
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    kernel.GetModuleFileNameW.restype = ctypes.c_uint
    result['loaded_windows_modules'] = {}
    for dll in ('ucrtbase.dll', 'IMM32.dll', 'MSCTF.dll', 'Qt6Core.dll', 'Qt6Gui.dll', 'qwindows.dll',
                'VCRUNTIME140.dll', 'MSVCP140.dll'):
        handle = kernel.GetModuleHandleW(dll)
        buffer = ctypes.create_unicode_buffer(32768)
        if handle and kernel.GetModuleFileNameW(handle, buffer, len(buffer)):
            value = buffer.value.replace(str(DATA_ROOT), '%TEMP_PORTABLE%')
            result['loaded_windows_modules'][dll] = value

    source = DATA_ROOT.parent / 'independent-test.pdf'
    document = pymupdf.open()
    for number in range(3):
        page = document.new_page(width=72 * (number + 1), height=72)
        page.insert_text((10, 30), 'Independent pruning fixture')
    document.save(str(source))
    document.close()
    with render_pdf(source, PdfSettings(150, 90, 'RGB')) as pages:
        checked('multipage_pdf_render', len(pages) == 3 and all(not QImage(str(p.path)).isNull() for p in pages))
        before = QImage(str(pages[1].path)).size()
        rotate_temporary_page(pages[1], 90)
        after = QImage(str(pages[1].path)).size()
        checked('pdf_render_rotation', after.width() == before.height() and after.height() == before.width())
        (image_dir / 'attachment.jpg').write_bytes(pages[0].path.read_bytes())
    checked('pdf_temporary_cleanup', all(not p.path.exists() for p in pages))

    people = PeopleService(db)
    person = people.add_person({'姓名': 'Pruning fictional fixture', '身份证号': None, '联系电话': None,
        '学历': None, '毕业院校': None, '专业': None, '进入系统日期': None})
    cert = people.add_certificate({'人员ID': person, '证书类型': '职称证', '证书名称': 'Fixture',
        '证书编号': 'TEST', '有效期': None})
    import sqlite3
    with sqlite3.connect(db) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('INSERT INTO 人员证书图表(证书ID,路径,备注) VALUES(?,?,?)',
                           (cert, 'Images/attachment.jpg', '1'))
        connection.commit()
    exported = DATA_ROOT.parent / 'fictional-people.xlsx'
    DataManagementService(db, data_root=DATA_ROOT).export_people(exported)
    book = openpyxl.load_workbook(exported)
    checked('real_people_xlsx_export_readback', book.active.max_row == 2)
    book.close()
    # This proves the existing application workflow without PIL; it does not
    # claim openpyxl's optional Drawing.image API works after PIL exclusion.
    task = PersonAutoFillTask()
    task.add(person, 'Pruning fictional fixture')
    task.item(person).attachment_certificate_ids.add(cert)
    settings = PdfSettings()
    plan = PersonAutoFillService(people, data_root=DATA_ROOT).build_plan(task, settings)
    checked('autofill_real_template_plan_with_attachment', len(plan.blocks) == 1 and plan.image_count == 1)
    job = PersonWordJob()
    job.add(person)
    job.item(person).selected_certificate_ids.add(cert)
    word_plan = PersonWordOutputService(people, data_root=DATA_ROOT).build_plan(job, settings)
    checked('word_image_plan_real_attachment', word_plan.image_count == 1)
    try:
        word = WordService.connect_existing_word()
        word.active_document()
        result['word_com'] = 'Existing Word/document read-only connection succeeded; no output written'
    except Exception as error:
        result['word_com'] = type(error).__name__ + ': existing Word/document unavailable'
    result['manual_verification'].append('Real Word image output and AutoFill document write not performed; fake tests are separate')
    try:
        import PIL
        result['pillow_runtime_import'] = 'present'
    except ImportError:
        result['pillow_runtime_import'] = 'absent'
    result['status'] = 'PASS'
except BaseException:
    result['error'] = traceback.format_exc()
finally:
    Path(os.environ['NEKOZZZ_PRUNE_RESULT']).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    app.exit(0 if result['status'] == 'PASS' else 1)
