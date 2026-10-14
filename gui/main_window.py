"""Designer shell with cached, first-visit business pages."""
from PySide6.QtWidgets import QApplication, QPushButton, QStackedWidget
from PySide6.QtGui import QIcon
from config.paths import UI_FILE, resource_path
from gui.theme import ThemeManager
from gui.copy_toast import CopyToast
from services.settings import SettingsService
from services.office_writer import OfficeWriterConnector, writer_name
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


def build_main_window(service, database_path, *, settings_service=None, attachment_service=None,
                      person_word_service=None, project_service=None, project_word_service=None,
                      project_attachment_service=None, qualification_service=None,
                      qualification_word_service=None, qualification_attachment_service=None,
                      award_service=None, finance_service=None, award_word_service=None, finance_word_service=None,
                      award_attachment_service=None, finance_attachment_service=None, data_management_service=None):
    from gui.lazy_window import WindowLoader, CloseGuard
    from gui.window_geometry import restore_window_geometry
    window = WindowLoader().load(str(UI_FILE))
    if window is None:
        raise RuntimeError(f'无法加载主界面: {UI_FILE}')
    stack = window.findChild(QStackedWidget, 'workspace')
    window.workspace = stack
    window.created_pages = {}
    settings_service = settings_service or SettingsService()
    writer_factory = OfficeWriterConnector(settings_service)
    toast = CopyToast(stack)
    window.copy_toast, window.copy_to_clipboard = toast, toast.copy
    app = QApplication.instance()
    if not hasattr(app, 'theme_manager'):
        app.theme_manager = ThemeManager(app)
    app.theme_manager.apply(settings_service.load().theme)
    domains = {}
    def domain(name):
        if name not in domains:
            if name == 'project':
                from services.projects import ProjectService
                domains[name] = project_service or ProjectService(database_path)
            elif name == 'qualification':
                from services.qualifications import QualificationService
                domains[name] = qualification_service or QualificationService(database_path)
            elif name == 'award':
                from services.award_finance import AwardService
                domains[name] = award_service or AwardService(database_path)
            elif name == 'finance':
                from services.award_finance import FinanceService
                domains[name] = finance_service or FinanceService(database_path)
            elif name == 'data':
                from services.data_management import DataManagementService
                domains[name] = data_management_service or DataManagementService(database_path, settings_path=settings_service.path)
        return domains[name]

    def person_page():
        from gui.person_word import PersonWordPage
        from services.person_word import PersonWordOutputService
        return PersonWordPage(service, person_word_service or PersonWordOutputService(service, word_factory=writer_factory),
                              settings_service, toast.show_message, copy_to_clipboard=toast.copy)

    def person_manage():
        from gui.person_manage import PersonManagePage
        from services.attachments import CertificateAttachmentService
        return PersonManagePage(service, settings_service=settings_service,
                                attachment_service=attachment_service or CertificateAttachmentService(database_path), notify=toast.show_message)

    def autofill():
        from gui.person_autofill import PersonAutoFillPage
        from services.autofill.person_service import PersonAutoFillService
        return PersonAutoFillPage(service, PersonAutoFillService(service, word_factory=writer_factory), settings_service, toast.show_message)

    def project_manage():
        from gui.project_manage import ProjectManagePage
        from services.attachments import ProjectAttachmentService
        return ProjectManagePage(domain('project'), settings_service=settings_service,
                                 attachment_service=project_attachment_service or ProjectAttachmentService(database_path), notify=toast.show_message)

    def project_search():
        from gui.project_search import ProjectSearchPage
        from services.project_word import ProjectWordOutputService
        source = domain('project')
        return ProjectSearchPage(source, project_word_service or ProjectWordOutputService(source.projects, word_factory=writer_factory),
                                 settings_service, toast.show_message, copy_to_clipboard=toast.copy)

    def qualification_manage():
        from gui.qualification_manage import QualificationManagePage
        from services.attachments import QualificationAttachmentService
        return QualificationManagePage(domain('qualification'), settings_service=settings_service,
                                       attachment_service=qualification_attachment_service or QualificationAttachmentService(database_path), notify=toast.show_message)

    def qualification_search():
        from gui.qualification_search import QualificationSearchPage
        from services.qualification_word import QualificationWordOutputService
        source = domain('qualification')
        return QualificationSearchPage(source, qualification_word_service or QualificationWordOutputService(source.qualifications, word_factory=writer_factory),
                                       settings_service, toast.show_message, copy_to_clipboard=toast.copy)

    def report_search(name):
        from gui.award_finance import ReportSearchPage
        from services.report_word import ReportWordOutputService
        source = domain(name)
        supplied = award_word_service if name == 'award' else finance_word_service
        return ReportSearchPage(source, supplied or ReportWordOutputService(source.repository, word_factory=writer_factory),
                                settings_service, toast.show_message, copy_to_clipboard=toast.copy)

    def report_manage():
        from gui.award_finance import ReportManagePage, AwardFinanceManagePage
        from services.attachments import AwardAttachmentService, FinanceAttachmentService
        award = ReportManagePage(domain('award'), settings_service=settings_service,
                                attachment_service=award_attachment_service or AwardAttachmentService(database_path), notify=toast.show_message)
        finance = ReportManagePage(domain('finance'), settings_service=settings_service,
                                  attachment_service=finance_attachment_service or FinanceAttachmentService(database_path), notify=toast.show_message)
        aggregate = AwardFinanceManagePage(award, finance)
        window.created_pages['award_manage_page'], window.created_pages['finance_manage_page'] = award, finance
        return aggregate

    def prepare_restore():
        pages = window.managed_pages()
        if not all(page.can_leave() for page in pages):
            return False
        for page in pages:
            page.discard_changes()
        return True

    def show_writer_target(target):
        window.statusBar().showMessage(f'{APP_NAME} {APP_VERSION} · 插入目标：{writer_name(target)} · DB Schema {DB_SCHEMA_VERSION} · 数据库：{database_path}')

    def settings_page():
        from gui.settings_page import SettingsPage
        from gui.data_management import DataManagementController
        data = domain('data')
        page = SettingsPage(settings_service, toast.show_message, service.certificates.list_certificate_types,
                            domain('project').projects.list_attachment_types, domain('qualification').qualifications.list_names,
                            data_management=data)
        page.theme_changed.connect(app.theme_manager.apply)
        page.writer_target_changed.connect(show_writer_target)
        window.data_management_controller = DataManagementController(window, page, data, toast.show_message, prepare_restore)
        return page

    def about_page():
        from gui.about import AboutPage
        return AboutPage()

    window._page_factories = {
        'person_word_page': person_page, 'manage_page': person_manage, 'person_autofill_page': autofill,
        'project_manage_page': project_manage, 'project_search_page': project_search,
        'qualification_manage_page': qualification_manage, 'qualification_search_page': qualification_search,
        'award_search_page': lambda: report_search('award'), 'finance_search_page': lambda: report_search('finance'),
        'award_finance_manage_page': report_manage, 'settings_page': settings_page, 'about_page': about_page,
    }
    navigation = {
        'navPersonSearch': 'person_word_page', 'navPersonManage': 'manage_page', 'navPersonAutoFill': 'person_autofill_page',
        'navProjectSearch': 'project_search_page', 'navProjectManage': 'project_manage_page',
        'navQualSearch': 'qualification_search_page', 'navQualManage': 'qualification_manage_page',
        'navAwardSearch': 'award_search_page', 'navFinanceSearch': 'finance_search_page',
        'navAwardFinanceManage': 'award_finance_manage_page', 'navSettings': 'settings_page', 'navAbout': 'about_page',
    }

    def navigate(name):
        if getattr(window, '_data_operation_running', False) or getattr(window, '_restore_completed', False) or getattr(window, '_data_recovery_required', False):
            return
        current = stack.currentWidget()
        if name in window.created_pages and window.created_pages[name] is current:
            for button_name, target in navigation.items():
                window.findChild(QPushButton, button_name).setChecked(target == name)
            return
        if current in window.managed_pages():
            if not current.can_leave():
                return
            if current.mode != 'view':
                current.discard_changes()
        existing = name in window.created_pages
        page = window.get_page(name)
        if current is page:
            return
        if existing:
            # Refresh underlying data with the retained filters/selection, not
            # new instances. Qualification refresh never reapplies default ID 1.
            if name == 'manage_page': page.refresh_people()
            elif name == 'person_word_page': page.search_people()
            elif name == 'settings_page': page.refresh_certificate_types()
            elif name == 'project_manage_page': page.refresh_projects()
            elif name == 'project_search_page':
                page.search()
                page.refresh_task(page.current_id())
            elif name == 'qualification_manage_page': page.refresh_qualifications()
            elif name == 'qualification_search_page':
                page.refresh_companies()
                page.search()
            elif name == 'award_finance_manage_page': page.refresh_records()
            elif name in ('award_search_page', 'finance_search_page'): page.search()
        stack.setCurrentWidget(page)
        for button_name, target in navigation.items():
            window.findChild(QPushButton, button_name).setChecked(target == name)

    window.navigate = navigate
    window.prepare_restore = prepare_restore
    for button_name, target in navigation.items():
        button = window.findChild(QPushButton, button_name)
        button.setEnabled(True)
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, name=target: navigate(name))
    guard = CloseGuard(window, settings_service)
    window.installEventFilter(guard)
    window._close_guard = guard
    window.setStyleSheet(STYLE)
    window.setWindowIcon(QIcon(str(resource_path('resources/icon.png'))))
    window.setWindowTitle(f'{APP_NAME} {APP_VERSION} · 投标资料工作台')
    show_writer_target(settings_service.load().writer_target)
    restore_window_geometry(window, settings_service)
    navigate('person_word_page')
    return window
