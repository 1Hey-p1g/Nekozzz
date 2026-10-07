"""Qt Designer shell and the two real person workspaces."""

from PySide6.QtCore import QEvent, QObject
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QStackedWidget, QWidget

from config.paths import UI_FILE, resource_path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from gui.theme import ThemeManager
from gui.copy_toast import CopyToast
from gui.person_manage import PersonManagePage
from gui.person_search import PersonSearchPage
from gui.person_word import PersonWordPage
from gui.person_autofill import PersonAutoFillPage
from services.autofill.person_service import PersonAutoFillService
from gui.settings_page import SettingsPage
from gui.about import AboutPage
from gui.project_manage import ProjectManagePage
from gui.project_search import ProjectSearchPage
from services.projects import ProjectService
from services.project_word import ProjectWordOutputService
from services.person_word import PersonWordOutputService
from services.settings import SettingsService
from services.attachments import CertificateAttachmentService, ProjectAttachmentService
from services.attachments import QualificationAttachmentService
from services.qualifications import QualificationService
from services.qualification_word import QualificationWordOutputService
from gui.qualification_search import QualificationSearchPage
from gui.qualification_manage import QualificationManagePage
from gui.award_finance import ReportSearchPage, ReportManagePage, AwardFinanceManagePage
from services.award_finance import AwardService, FinanceService
from services.report_word import ReportWordOutputService
from services.attachments import AwardAttachmentService, FinanceAttachmentService
from services.data_management import DataManagementService
from gui.data_management import DataManagementController
from version import APP_NAME, APP_VERSION, DB_SCHEMA_VERSION


STYLE = """
QMainWindow, QStackedWidget { background: #f6f8fb; color: #1e293b; }
QFrame#navigation { background: #17243a; }
QFrame#navigation QLabel { color: #a9b9ce; margin: 10px 6px 3px 6px; }
QFrame#navigation QLabel#brand { color: white; font-size: 19px; font-weight: 700; margin-bottom: 22px; }
QFrame#navigation QPushButton { border: 0; border-radius: 8px; background: transparent;
    color: #e3ebf5; text-align: left; padding: 10px 12px; }
QFrame#navigation QPushButton:hover { background: #2b405d; }
QFrame#navigation QPushButton:checked { background: #345a8d; color: white; font-weight: 600; }
QFrame#navigation QPushButton:disabled { color: #71849d; }
QLabel#pageTitle { font-size: 22px; font-weight: 700; color: #15243b; }
QLabel#subtitle { color: #64748b; margin-bottom: 7px; }
QLabel#detailSummary, QLabel#imagePreview { background: white; border: 1px solid #dce4ed;
    border-radius: 8px; padding: 10px; }
QLabel#stateLabel { color: #356397; font-weight: 600; }
QLineEdit, QComboBox, QTableView { background: white; border: 1px solid #d1dbe7;
    border-radius: 6px; padding: 5px; }
QLineEdit:focus, QComboBox:focus, QTableView:focus { border-color: #4d83bd; }
QComboBox { min-height: 20px; padding: 5px 30px 5px 8px; }
QComboBox:hover { border-color: #96aec9; background: #fbfdff; }
QComboBox:focus { border-color: #4d83bd; }
QComboBox:disabled { background: #f1f4f8; color: #7d8fa4; }
QComboBox QLineEdit { border: 0; border-radius: 0; background: transparent; padding: 0; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right;
    width: 25px; border-left: 1px solid #d1dbe7; border-top-right-radius: 6px;
    border-bottom-right-radius: 6px; background: #eef3f8; }
QComboBox::drop-down:hover { background: #e2eaf3; }
QComboBox::down-arrow { image: none; width: 0; height: 0; }
QComboBox QAbstractItemView { background: white; color: #1e293b; border: 1px solid #d1dbe7;
    selection-background-color: #dceafa; selection-color: #1e293b; outline: 0; }
QGroupBox#certificateAttachmentSection { background: white; border: 1px solid #dce4ed;
    border-radius: 8px; margin-top: 12px; padding: 8px; }
QGroupBox#certificateAttachmentSection::title { subcontrol-origin: margin; left: 12px;
    padding: 0 5px; color: #324b68; font-weight: 600; }
QPushButton { background: white; border: 1px solid #cbd7e4; border-radius: 6px;
    padding: 7px 12px; color: #23405d; }
QPushButton:hover { background: #eaf1f9; }
QPushButton:disabled { color: #9caec0; background: #f1f4f8; }
QHeaderView::section { background: #e9eff6; border: 0; border-bottom: 1px solid #d4deea;
    padding: 7px; color: #324b68; font-weight: 600; }
QStatusBar { background: #e8eef5; color: #395575; }
"""


class _CloseGuard(QObject):
    def __init__(self, *manage_pages):
        super().__init__()
        self.manage_pages = manage_pages

    def eventFilter(self, _object, event):
        if event.type() == QEvent.Close:
            if getattr(_object, '_data_operation_running', False):
                event.ignore()
                return True
            if getattr(_object, '_restore_completed', False) or getattr(_object, '_data_recovery_required', False):
                return False
        if event.type() == QEvent.Close and not all(page.can_leave() for page in self.manage_pages):
            event.ignore()
            return True
        return False


def build_main_window(service, database_path, *, settings_service=None, attachment_service=None,
                      person_word_service=None, project_service=None, project_word_service=None,
                      project_attachment_service=None, qualification_service=None,
                      qualification_word_service=None, qualification_attachment_service=None,
                      award_service=None, finance_service=None, award_word_service=None, finance_word_service=None,
                      award_attachment_service=None, finance_attachment_service=None, data_management_service=None):
    window = QUiLoader().load(str(UI_FILE))
    if window is None:
        raise RuntimeError(f"无法加载主界面: {UI_FILE}")
    stack = window.findChild(QStackedWidget, "workspace")
    toast = CopyToast(stack)
    search_page = PersonSearchPage(service, copy_to_clipboard=toast.copy)
    settings_service = settings_service or SettingsService()
    multi_page = PersonWordPage(
        service, person_word_service or PersonWordOutputService(service),
        settings_service, toast.show_message, copy_to_clipboard=toast.copy,
    )
    autofill_page = PersonAutoFillPage(service, PersonAutoFillService(service), settings_service, toast.show_message)
    stack.addWidget(autofill_page)
    window.person_autofill_page = autofill_page
    manage_page = PersonManagePage(
        service, settings_service=settings_service,
        attachment_service=attachment_service or CertificateAttachmentService(database_path),
        notify=toast.show_message,
    )
    project_service = project_service or ProjectService(database_path)
    project_manage_page = ProjectManagePage(
        project_service, settings_service=settings_service,
        attachment_service=project_attachment_service or ProjectAttachmentService(database_path),
        notify=toast.show_message,
    )
    project_search_page = ProjectSearchPage(
        project_service, project_word_service or ProjectWordOutputService(project_service.projects),
        settings_service, toast.show_message, copy_to_clipboard=toast.copy,
    )
    qualification_service = qualification_service or QualificationService(database_path)
    qualification_manage_page = QualificationManagePage(
        qualification_service, settings_service=settings_service,
        attachment_service=qualification_attachment_service or QualificationAttachmentService(database_path),
        notify=toast.show_message,
    )
    qualification_search_page = QualificationSearchPage(
        qualification_service, qualification_word_service or QualificationWordOutputService(qualification_service.qualifications),
        settings_service, toast.show_message, copy_to_clipboard=toast.copy,
    )
    award_service = award_service or AwardService(database_path)
    finance_service = finance_service or FinanceService(database_path)
    award_search_page = ReportSearchPage(
        award_service, award_word_service or ReportWordOutputService(award_service.repository),
        settings_service, toast.show_message, copy_to_clipboard=toast.copy)
    finance_search_page = ReportSearchPage(
        finance_service, finance_word_service or ReportWordOutputService(finance_service.repository),
        settings_service, toast.show_message, copy_to_clipboard=toast.copy)
    award_manage_page = ReportManagePage(
        award_service, settings_service=settings_service,
        attachment_service=award_attachment_service or AwardAttachmentService(database_path), notify=toast.show_message)
    finance_manage_page = ReportManagePage(
        finance_service, settings_service=settings_service,
        attachment_service=finance_attachment_service or FinanceAttachmentService(database_path), notify=toast.show_message)
    award_finance_manage_page = AwardFinanceManagePage(award_manage_page, finance_manage_page)
    data_management_service = data_management_service or DataManagementService(
        database_path, settings_path=settings_service.path)
    settings_page = SettingsPage(settings_service, toast.show_message,
                                 service.certificates.list_certificate_types,
                                 project_service.projects.list_attachment_types,
                                 qualification_service.qualifications.list_names,
                                 data_management=data_management_service)
    stack.addWidget(search_page)
    stack.addWidget(multi_page)
    stack.addWidget(manage_page)
    stack.addWidget(settings_page)
    about_page = AboutPage()
    stack.addWidget(about_page)
    window.about_page = about_page
    stack.addWidget(project_manage_page)
    stack.addWidget(project_search_page)
    stack.addWidget(qualification_manage_page)
    stack.addWidget(qualification_search_page)
    for page in (award_search_page, finance_search_page, award_finance_manage_page):
        stack.addWidget(page)
    window.search_page = search_page
    window.person_word_page = multi_page
    window.manage_page = manage_page
    window.settings_page = settings_page
    window.project_manage_page = project_manage_page
    window.project_search_page = project_search_page
    window.qualification_manage_page = qualification_manage_page
    window.qualification_search_page = qualification_search_page
    window.award_search_page = award_search_page
    window.finance_search_page = finance_search_page
    window.award_finance_manage_page = award_finance_manage_page
    window.award_manage_page = award_manage_page
    window.finance_manage_page = finance_manage_page
    window.copy_toast = toast
    window.copy_to_clipboard = toast.copy
    navigation = {
        "navPersonAutoFill": autofill_page,
        "navPersonSearch": search_page,
        "navPersonManage": manage_page,
        "navSettings": settings_page,
        "navAbout": about_page,
        "navProjectSearch": project_search_page,
        "navProjectManage": project_manage_page,
        "navQualSearch": qualification_search_page,
        "navQualManage": qualification_manage_page,
        "navAwardSearch": award_search_page,
        "navFinanceSearch": finance_search_page,
        "navAwardFinanceManage": award_finance_manage_page,
    }

    mode_buttons = []
    def add_mode_bar(page):
        bar = QWidget(page)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 3)
        row.setSpacing(8)
        single = QPushButton("单人选择")
        multiple = QPushButton("多人 Word 输出")
        for button in (single, multiple):
            button.setCheckable(True)
            button.setObjectName("personModeButton")
            row.addWidget(button)
        row.addStretch()
        page.layout().insertWidget(0, bar)
        mode_buttons.append((single, multiple))
        single.clicked.connect(lambda: show_person_mode(search_page))
        multiple.clicked.connect(lambda: show_person_mode(multi_page))

    person_mode = search_page

    def show_person_mode(page):
        nonlocal person_mode
        person_mode = page
        stack.setCurrentWidget(page)
        for single, multiple in mode_buttons:
            single.setChecked(page is search_page)
            multiple.setChecked(page is multi_page)
        window.findChild(QPushButton, "navPersonSearch").setChecked(True)

    add_mode_bar(search_page)
    add_mode_bar(multi_page)

    def navigate(page):
        if page is search_page:
            page = person_mode
        if stack.currentWidget() is page and any(
            window.findChild(QPushButton, name).isChecked() for name in navigation
        ):
            return
        current = stack.currentWidget()
        if current in (manage_page, project_manage_page, qualification_manage_page, award_finance_manage_page) and current is not page:
            if not current.can_leave():
                return
            if current.mode != "view":
                current.discard_changes()
        if page is manage_page:
            manage_page.refresh_people()
        elif page is search_page:
            search_page.search_people()
        elif page is multi_page:
            multi_page.search_people()
        elif page is settings_page:
            settings_page.refresh_certificate_types()
        elif page is project_manage_page:
            project_manage_page.refresh_projects()
        elif page is project_search_page:
            project_search_page.search()
            project_search_page.refresh_task(project_search_page.current_id())
        elif page is qualification_manage_page:
            qualification_manage_page.refresh_qualifications()
        elif page is qualification_search_page:
            qualification_search_page.refresh_companies()
            qualification_search_page.search()
        elif page is award_finance_manage_page:
            page.refresh_records()
        elif page in (award_search_page, finance_search_page):
            page.search()
        stack.setCurrentWidget(page)
        for name, target in navigation.items():
            window.findChild(QPushButton, name).setChecked(
                target is page or (name == "navPersonSearch" and page is multi_page)
            )

    for name, page in navigation.items():
        button = window.findChild(QPushButton, name)
        button.setEnabled(True)
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, target=page: navigate(target))
    guard = _CloseGuard(manage_page, project_manage_page, qualification_manage_page, award_finance_manage_page)
    window.installEventFilter(guard)
    window._close_guard = guard
    def prepare_restore():
        if not all(page.can_leave() for page in guard.manage_pages):
            return False
        for page in guard.manage_pages:
            page.discard_changes()
        return True
    window.data_management_controller = DataManagementController(
        window, settings_page, data_management_service, toast.show_message, prepare_restore)
    window.setStyleSheet(STYLE)
    window.setWindowIcon(QIcon(str(resource_path('resources/icon.png'))))
    app = QApplication.instance()
    if not hasattr(app, 'theme_manager'):
        app.theme_manager = ThemeManager(app)
    settings_page.theme_changed.connect(app.theme_manager.apply)
    app.theme_manager.apply(settings_service.load().theme)
    window.setWindowTitle(f'{APP_NAME} {APP_VERSION} · 投标资料工作台')
    window.statusBar().showMessage(f"{APP_NAME} {APP_VERSION} · DB Schema {DB_SCHEMA_VERSION} · 数据库：{database_path}")
    navigate(search_page)
    show_person_mode(search_page)
    return window
