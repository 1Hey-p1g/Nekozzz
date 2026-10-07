"""Scrollable application preferences, including PDF and future Word output settings."""

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from gui.common import StyledComboBox
from services.settings import PdfSettings, merge_certificate_type_order


QUALITY_VALUES = (70, 85, 90, 100)


class CertificateOrderList(QListWidget):
    order_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def values(self):
        return tuple(self.item(index).text() for index in range(self.count()))

    def dropEvent(self, event):
        before = self.values()
        super().dropEvent(event)
        if self.values() != before:
            self.order_changed.emit()


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    def __init__(self, settings_service, notify, certificate_types=None, project_types=None,
                 qualification_names=None, *, data_management=None):
        super().__init__()
        self.settings_service = settings_service
        self.notify = notify
        self.certificate_types = certificate_types or (lambda: ())
        self.project_types = project_types or (lambda: ())
        self.qualification_names = qualification_names or (lambda: ())
        self.data_management = data_management
        self._build()
        self.show_settings(self.settings_service.load())

    def _build(self):
        page = QVBoxLayout(self)
        page.setContentsMargins(26, 22, 26, 22)
        page.setSpacing(10)
        title = QLabel("设置")
        title.setObjectName("pageTitle")
        page.addWidget(title)
        subtitle = QLabel("Nekozzz 的应用程序设置与数据维护")
        subtitle.setObjectName("subtitle")
        page.addWidget(subtitle)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("settingsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        page.addWidget(self.scroll, 1)
        canvas = QWidget()
        self.scroll.setWidget(canvas)
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 3, 0, 8)
        column = QWidget()
        column.setMaximumWidth(850)
        column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(15)
        centered = QHBoxLayout()
        centered.setContentsMargins(0, 0, 0, 0)
        centered.addStretch(1)
        centered.addWidget(column, 100)
        centered.addStretch(1)
        canvas_layout.addLayout(centered)
        canvas_layout.addStretch()

        appearance = self._card("外观")
        column_layout.addWidget(appearance)
        self.theme = StyledComboBox()
        self.theme.setObjectName("themeChoice")
        self.theme.addItems(("跟随系统", "明亮模式", "黑暗模式"))
        self.theme.setFixedWidth(126)
        self.theme.currentIndexChanged.connect(self._save_theme)
        self._setting_row(appearance.layout(), "主题",
                          "根据系统设置自动切换，或固定使用明亮/黑暗模式。", self.theme)

        pdf = self._card("PDF 导入与图像处理")
        column_layout.addWidget(pdf)
        self.dpi = StyledComboBox()
        self.dpi.setObjectName("pdfDpi")
        for value in (150, 200, 300):
            self.dpi.addItem(f"{value} DPI", value)
        self.dpi.setFixedWidth(126)
        self._setting_row(pdf.layout(), "PDF 渲染 DPI", "决定导入图片的分辨率。", self.dpi)

        self.quality = QSlider(Qt.Horizontal)
        self.quality.setObjectName("jpegQuality")
        self.quality.setRange(0, 3)
        self.quality.setSingleStep(1)
        self.quality.setPageStep(1)
        self.quality.setTickInterval(1)
        self.quality.setTickPosition(QSlider.TicksBelow)
        slider_column = QWidget()
        slider_column.setMinimumWidth(180)
        slider_column.setMaximumWidth(300)
        slider_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        slider_layout = QVBoxLayout(slider_column)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        slider_layout.setSpacing(0)
        slider_layout.addWidget(self.quality)
        ticks = QHBoxLayout()
        ticks.setContentsMargins(0, 0, 0, 0)
        for index, value in enumerate(QUALITY_VALUES):
            label = QLabel(str(value))
            label.setObjectName(f"qualityTick{value}")
            ticks.addWidget(label)
            if index < len(QUALITY_VALUES) - 1:
                ticks.addStretch()
        slider_layout.addLayout(ticks)
        self.quality_value = QLabel("当前：90")
        self.quality_value.setObjectName("qualityValue")
        self._setting_row(pdf.layout(), "JPEG 质量", "数值越高，图片体积通常越大。",
                          slider_column, extra=self.quality_value, wide_control=True)

        self.color = StyledComboBox()
        self.color.setObjectName("pdfColor")
        self.color.addItems(("RGB", "Grayscale"))
        self.color.setFixedWidth(126)
        self._setting_row(pdf.layout(), "颜色模式", "彩色或灰度整页渲染。", self.color)

        word = self._card("Word 插入")
        column_layout.addWidget(word)
        self.image_style = QLineEdit()
        self.image_style.setObjectName("wordImageStyle")
        self.image_style.setMaximumWidth(300)
        self._setting_row(word.layout(), "图片样式", "输入目标 Word 文档中的图片段落样式名称。", self.image_style)
        self.person_name_style = QLineEdit()
        self.person_name_style.setObjectName("wordPersonNameStyle")
        self.person_name_style.setMaximumWidth(300)
        self._setting_row(word.layout(), "文本样式", "输入目标 Word 文档中的姓名、工程名称等文本段落样式名称。", self.person_name_style)
        self.shrink_images = QCheckBox("超宽图片自适应缩小")
        self.shrink_images.setObjectName("wordShrinkImages")
        word.layout().addWidget(self.shrink_images)
        self.enlarge_images = QCheckBox("小图片自适应放大")
        self.enlarge_images.setObjectName("wordEnlargeImages")
        word.layout().addWidget(self.enlarge_images)
        word.layout().addWidget(QLabel("人员证书输出顺序"))
        self.certificate_order = CertificateOrderList()
        self.certificate_order.setObjectName("personCertificateTypeOrder")
        self.certificate_order.setFixedHeight(190)
        word.layout().addWidget(self.certificate_order)
        word.layout().addWidget(self._muted("拖动调整 Word 输出顺序；暂时没有证书使用的类型仍会保留。"))
        word.layout().addWidget(QLabel("工程业绩附件类型输出顺序"))
        self.project_order = CertificateOrderList()
        self.project_order.setObjectName("projectAttachmentTypeOrder")
        self.project_order.setFixedHeight(190)
        word.layout().addWidget(self.project_order)
        word.layout().addWidget(self._muted("拖动调整工程附件输出顺序；暂时不存在的类型仍会保留。"))
        word.layout().addWidget(QLabel("公司资质 Word 输出顺序"))
        self.qualification_order = CertificateOrderList()
        self.qualification_order.setObjectName("companyQualificationNameOrder")
        self.qualification_order.setFixedHeight(190)
        word.layout().addWidget(self.qualification_order)
        word.layout().addWidget(self._muted("按资质证书名称拖动排序；同名资质按 ID 升序，暂时不存在的名称仍保留。"))

        autofill = self._card("自动填表")
        column_layout.addWidget(autofill)
        for key, label in (
                ('autofill_title_style', '表头样式'),
                ('autofill_note_style', '注释样式'),
                ('autofill_person_name_style', '人员姓名样式')):
            control = QLineEdit()
            control.setObjectName(key)
            control.setMaximumWidth(300)
            control.setPlaceholderText("留空使用内置正文（Normal）")
            setattr(self, key, control)
            self._setting_row(autofill.layout(), label,
                              "仅用于自动填表；留空通过 Word 内置 ID 使用正文。", control)
            control.editingFinished.connect(self._save_autofill)
        autofill.layout().addWidget(self._muted("附件图片继续使用上方的图片样式；表格内部格式保持模板原样。"))

        defaults_row = QHBoxLayout()
        self.defaults_button = QPushButton("恢复默认设置")
        self.defaults_button.setObjectName("restoreDefaults")
        defaults_row.addWidget(self.defaults_button)
        defaults_row.addStretch()
        column_layout.addLayout(defaults_row)

        data = self._card("数据管理")
        column_layout.addWidget(data)
        self._data_row(data.layout(), "Access 数据迁移",
                       "用于项目首次落地，将现有 Access 数据一次性迁移到 Nekozzz。",
                       ("从 Access 迁移...", "accessImport"))
        self._data_row(data.layout(), "数据备份",
                       "完整备份数据库、Images 和设置；恢复前自动创建安全备份。",
                       ("创建完整备份...", "backupDatabase"), ("从备份恢复...", "restoreDatabase"))
        self._data_row(data.layout(), "人员资料", "仅导出人员表，便于人工校对；不导入或更新数据库。",
                       ("导出人员表 Excel...", "exportPeople"))
        self.error_label = QLabel("")
        self.error_label.setObjectName("settingsError")
        self.error_label.setWordWrap(True)
        column_layout.addWidget(self.error_label)

        self.dpi.currentIndexChanged.connect(self._save_pdf)
        self.quality.valueChanged.connect(self._quality_changed)
        self.color.currentIndexChanged.connect(self._save_pdf)
        self.image_style.editingFinished.connect(self._save_word)
        self.person_name_style.editingFinished.connect(self._save_word)
        self.shrink_images.toggled.connect(self._save_word)
        self.enlarge_images.toggled.connect(self._save_word)
        self.certificate_order.order_changed.connect(self._save_word)
        self.project_order.order_changed.connect(self._save_word)
        self.qualification_order.order_changed.connect(self._save_word)
        self.defaults_button.clicked.connect(self.restore_defaults)
        self.setStyleSheet("""
            QLabel#pageTitle { color: #15243b; font-size: 22px; font-weight: 700; }
            QLabel#subtitle { color: #64748b; margin-bottom: 7px; }
            QWidget#settingsScroll { background: transparent; }
            QFrame#settingsCard { background: white; border: 1px solid #dce4ed;
                border-radius: 8px; }
            QLabel#settingsCardTitle { color: #15243b; font-size: 16px; font-weight: 650; }
            QLabel#settingName { color: #23405d; font-weight: 600; }
            QLabel#settingHint { color: #64748b; font-size: 12px; }
            QLabel#qualityValue { color: #356397; font-weight: 600; }
            QLabel#settingsError { color: #ae3131; }
            QComboBox { background: white; border: 1px solid #d1dbe7; border-radius: 6px;
                min-height: 20px; padding: 5px 30px 5px 8px; color: #23405d; }
            QComboBox:hover { background: #fbfdff; border-color: #96aec9; }
            QComboBox:focus { border-color: #4d83bd; }
            QComboBox:disabled { background: #f1f4f8; color: #7d8fa4; }
            QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right;
                width: 25px; border-left: 1px solid #d1dbe7; background: #eef3f8; }
            QComboBox::down-arrow { image: none; width: 0; height: 0; }
            QLineEdit, QListWidget { background: white; border: 1px solid #d1dbe7;
                border-radius: 6px; padding: 6px; color: #23405d; }
            QLineEdit:focus, QListWidget:focus { border-color: #4d83bd; }
            QListWidget::item { background: #f1f5f9; padding: 6px 8px;
                margin: 2px 0px; border-radius: 4px; }
            QListWidget::item:hover { background: #eaf1f8; }
            QListWidget::item:selected { background: #dceafa; color: #23405d; }
            QCheckBox { color: #23405d; spacing: 8px; }
            QSlider::groove:horizontal { height: 6px; border-radius: 3px; background: #dce4ed; }
            QSlider::sub-page:horizontal { border-radius: 3px; background: #4d83bd; }
            QSlider::handle:horizontal { width: 16px; margin: -6px 0; border-radius: 8px;
                background: white; border: 2px solid #4d83bd; }
            QPushButton { background: white; border: 1px solid #cbd7e4; border-radius: 6px;
                padding: 7px 12px; color: #23405d; }
            QPushButton:hover { background: #eaf1f9; }
            QPushButton:disabled { color: #9caec0; background: #f1f4f8; }
        """)

    @staticmethod
    def _muted(text):
        label = QLabel(text)
        label.setObjectName("settingHint")
        label.setWordWrap(True)
        return label

    def _card(self, title):
        card = QFrame()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("settingsCardTitle")
        layout.addWidget(heading)
        return card

    def _setting_row(self, layout, title, hint, control, *, extra=None, wide_control=False):
        row = QHBoxLayout()
        row.setSpacing(14)
        labels = QVBoxLayout()
        labels.setSpacing(3)
        title_label = QLabel(title)
        title_label.setObjectName("settingName")
        labels.addWidget(title_label)
        if extra is not None:
            labels.addWidget(extra)
        labels.addWidget(self._muted(hint))
        row.addLayout(labels, 1)
        row.addWidget(control, 1 if wide_control else 0,
                      Qt.AlignVCenter if wide_control else Qt.AlignRight | Qt.AlignVCenter)
        layout.addLayout(row)

    def _data_row(self, layout, title, hint, *buttons):
        row = QHBoxLayout()
        labels = QVBoxLayout()
        name = QLabel(title)
        name.setObjectName("settingName")
        labels.addWidget(name)
        labels.addWidget(self._muted(hint))
        row.addLayout(labels, 1)
        for text, object_name in buttons:
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.setEnabled(self.data_management is not None)
            if self.data_management is None:
                button.setToolTip("需要连接明确指定的 V1 数据库")
            row.addWidget(button)
        layout.addLayout(row)

    def show_settings(self, settings):
        """Display persisted values without triggering an immediate save."""
        controls = (self.theme, self.dpi, self.quality, self.color, self.image_style,
                    self.person_name_style, self.shrink_images, self.enlarge_images,
                    self.certificate_order, self.project_order, self.qualification_order,
                    self.autofill_title_style, self.autofill_note_style, self.autofill_person_name_style)
        previous = [control.blockSignals(True) for control in controls]
        try:
            self.theme.setCurrentIndex(('system', 'light', 'dark').index(settings.theme))
            self.dpi.setCurrentIndex(self.dpi.findData(settings.dpi))
            self.quality.setValue(QUALITY_VALUES.index(settings.jpeg_quality))
            self.color.setCurrentText(settings.color_mode)
            self.quality_value.setText(f"当前：{settings.jpeg_quality}")
            self.image_style.setText(settings.image_style)
            self.person_name_style.setText(settings.person_name_style)
            self.autofill_title_style.setText(settings.autofill_title_style)
            self.autofill_note_style.setText(settings.autofill_note_style)
            self.autofill_person_name_style.setText(settings.autofill_person_name_style)
            self.shrink_images.setChecked(settings.shrink_oversized_images)
            self.enlarge_images.setChecked(settings.enlarge_small_images)
            self.certificate_order.clear()
            self.certificate_order.addItems(merge_certificate_type_order(
                settings.person_certificate_type_order, self.certificate_types()
            ))
            self.project_order.clear()
            self.project_order.addItems(merge_certificate_type_order(
                settings.project_attachment_type_order, self.project_types()
            ))
            self.qualification_order.clear()
            self.qualification_order.addItems(merge_certificate_type_order(
                settings.company_qualification_name_order, self.qualification_names()
            ))
        finally:
            for control, old in zip(controls, previous):
                control.blockSignals(old)

    def _quality_changed(self, index):
        self.quality_value.setText(f"当前：{QUALITY_VALUES[index]}")
        self._save_pdf()

    def _save_theme(self, index):
        settings = replace(self.settings_service.load(), theme=('system', 'light', 'dark')[index])
        try:
            self.settings_service.save(settings)
        except (OSError, ValueError, TypeError) as error:
            self.error_label.setText(f'保存设置失败：{error}')
            self.show_settings(self.settings_service.load())
            return
        self.error_label.clear()
        self.theme_changed.emit(settings.theme)

    def _save_pdf(self, *_):
        settings = replace(self.settings_service.load(), dpi=self.dpi.currentData(),
                           jpeg_quality=QUALITY_VALUES[self.quality.value()],
                           color_mode=self.color.currentText())
        self._persist(settings)

    def _save_word(self, *_):
        settings = replace(
            self.settings_service.load(), image_style=self.image_style.text(),
            person_name_style=self.person_name_style.text(),
            shrink_oversized_images=self.shrink_images.isChecked(),
            enlarge_small_images=self.enlarge_images.isChecked(),
            person_certificate_type_order=self.certificate_order.values(),
            project_attachment_type_order=self.project_order.values(),
            company_qualification_name_order=self.qualification_order.values(),
        )
        self._persist(settings, refresh=True)

    def _save_autofill(self):
        settings = replace(
            self.settings_service.load(),
            autofill_title_style=self.autofill_title_style.text(),
            autofill_note_style=self.autofill_note_style.text(),
            autofill_person_name_style=self.autofill_person_name_style.text(),
        )
        self._persist(settings, refresh=True)

    def _persist(self, settings, *, refresh=False):
        try:
            self.settings_service.save(settings)
        except (OSError, ValueError, TypeError) as error:
            self.error_label.setText(f"保存设置失败：{error}")
            self.show_settings(self.settings_service.load())
            return
        if refresh:
            self.show_settings(self.settings_service.load())
        self.error_label.clear()

    def refresh_certificate_types(self):
        self.show_settings(self.settings_service.load())

    def restore_defaults(self):
        result = QMessageBox.question(
            self, "恢复默认设置", "确定恢复应用程序偏好设置的默认值？数据库和图片不会受到影响。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        defaults = replace(PdfSettings(), person_certificate_type_order=merge_certificate_type_order(
            (), self.certificate_types()
        ), project_attachment_type_order=merge_certificate_type_order((), self.project_types()),
            company_qualification_name_order=merge_certificate_type_order((), self.qualification_names()))
        try:
            self.settings_service.save(defaults)
        except (OSError, ValueError, TypeError) as error:
            self.error_label.setText(f"保存设置失败：{error}")
            return
        self.show_settings(defaults)
        self.theme_changed.emit(defaults.theme)
        self.error_label.clear()
        self.notify("已恢复默认设置")
