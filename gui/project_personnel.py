"""Compact draft editor: one relation row, editable role, ID-backed person choice."""
from PySide6.QtCore import Signal, QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QPalette
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget, QLayout,
)
from gui.common import StyledComboBox
from services.projects import ProjectPersonnelEntry

COMMON_PROJECT_ROLES = (
    '项目负责人', '技术负责人', '质量员', '造价员', '施工员', '安全员',
    '安全负责人', '资料员', '材料员', '机械设备管理员', '项目管理员',
)


class RelationRow(QWidget):
    def active_colors(self):
        accent = self.palette().color(QPalette.Active, QPalette.Highlight)
        background, border = type(accent)(accent), type(accent)(accent)
        background.setAlpha(35)
        border.setAlpha(160)
        return background, border

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.property('active'):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            background, border = self.active_colors()
            painter.setBrush(background)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 5, 5)


class PersonnelScrollArea(QScrollArea):
    """Content-independent minimum; preferred viewport grows only up to six rows."""
    preferred_height = 0

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(hint.width(), self.preferred_height or hint.height())


class ProjectPersonnelEditor(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.entries, self.rows, self.candidates = [], [], []
        self.read_only = True
        self.active_row = None
        self._row_for_control = {}
        self._height_pending = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.heading = QLabel('项目管理人员 · 担任职务 / 人员')
        layout.addWidget(self.heading)
        self.scroll = PersonnelScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas = QWidget()
        self.row_layout = QVBoxLayout(self.canvas)
        self.row_layout.setContentsMargins(0, 0, 0, 0)
        self.row_layout.setSpacing(6)
        self.row_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.row_layout.addStretch()
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll)
        self.add_button = QPushButton('+ 添加人员')
        self._measure_role = StyledComboBox(self)
        self._measure_role.setEditable(True)
        self._measure_role.hide()  # Measurement only; no fake relation/draft.
        self.add_button.clicked.connect(lambda: self.add_entry())
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.add_button)
        layout.addLayout(actions)
        self.set_read_only(True)
        self._refresh_height()

    def _refresh_height(self):
        self._height_pending = False
        self._measure_role.ensurePolished()
        row_height = (self.rows[0][1].sizeHint().height() if self.rows else
                      max(24, self._measure_role.sizeHint().height()) + 8)
        margins = self.row_layout.contentsMargins()
        def height(rows):
            return (rows * row_height + (rows-1) * self.row_layout.spacing()
                    + margins.top() + margins.bottom() + 2 * self.scroll.frameWidth())
        minimum = height(3)
        maximum = height(6 if len(self.rows) > 3 else 3)
        preferred = height(max(3, min(6, len(self.rows))))
        if self.scroll.minimumHeight() != minimum:
            self.scroll.setMinimumHeight(minimum)
        if self.scroll.maximumHeight() != maximum:
            self.scroll.setMaximumHeight(maximum)
        if self.scroll.preferred_height != preferred:
            self.scroll.preferred_height = preferred
            self.scroll.updateGeometry()
        total = maximum + self.heading.sizeHint().height() + self.add_button.sizeHint().height()
        total += self.layout().spacing()*2
        if self.maximumHeight() != total:
            self.setMaximumHeight(total)
        self.updateGeometry()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange) and hasattr(self, 'scroll'):
            if not self._height_pending:
                self._height_pending = True
                QTimer.singleShot(0, self._refresh_height)

    def activate_row(self, row):
        if self.read_only or row is self.active_row:
            return
        self.clear_active()
        self.active_row = row
        row.setProperty('active', True)
        row.update()

    def clear_active(self):
        if self.active_row is not None:
            self.active_row.setProperty('active', False)
            self.active_row.update()
            self.active_row = None

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress):
            row = self._row_for_control.get(watched)
            if row is not None:
                self.activate_row(row)
        return super().eventFilter(watched, event)

    def _reveal(self, row):
        if not self.read_only and any(r[1] is row for r in self.rows):
            self.row_layout.activate()
            self.scroll.ensureWidgetVisible(row, 0, self.row_layout.spacing())

    def reset(self, candidates, entries):
        self.clear_active()
        self._row_for_control.clear()
        for _, row, _, _, _ in self.rows:
            self.row_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self.entries, self.rows = [], []
        names = [p['姓名'] for p in candidates]
        self.candidates = [(f"{p['姓名']}（ID {p['人员ID']}）" if names.count(p['姓名']) > 1 else p['姓名'],
                            p['人员ID']) for p in candidates]
        for entry in entries:
            self.add_entry(entry, notify=False)
        self._refresh_height()

    def set_read_only(self, read_only):
        self.read_only = read_only
        if read_only:
            self.clear_active()
        self.add_button.setEnabled(not read_only)
        for _, _, role, person, remove in self.rows:
            for control in (role, person, remove):
                control.setEnabled(not read_only)

    def add_entry(self, entry=None, *, notify=True):
        entry = entry if entry is not None else ProjectPersonnelEntry()
        self.entries.append(entry)
        row = RelationRow()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 4, 6, 4)
        role, person = StyledComboBox(), StyledComboBox()
        role.setEditable(True)
        role.setInsertPolicy(StyledComboBox.NoInsert)
        role.addItems(COMMON_PROJECT_ROLES)
        role.setCurrentText(entry.role)
        person.addItem('— 选择人员 —', None)
        for label, person_id in self.candidates:
            person.addItem(label, person_id)
        person.setCurrentIndex(max(0, person.findData(entry.person_id)))
        remove = QToolButton()
        remove.setText('×')
        remove.setToolTip('移除此人员关系（保存后生效）')
        remove.setFixedSize(24, 24)
        remove.setStyleSheet('QToolButton {border: none; border-radius: 5px; color: #a96767;}'
                            'QToolButton:hover {background: #fae8e8; color: #974747;}'
                            'QToolButton:pressed {background: #f3dada;}')
        layout.addWidget(role, 1)
        layout.addWidget(person, 1)
        layout.addWidget(remove)
        self.row_layout.insertWidget(self.row_layout.count()-1, row)
        self.rows.append((entry, row, role, person, remove))
        for control in (row, role, role.lineEdit(), person, remove):
            self._row_for_control[control] = row
            control.installEventFilter(self)
        role.currentTextChanged.connect(lambda text: self.update(entry, 'role', text))
        person.currentIndexChanged.connect(lambda _: self.update(entry, 'person_id', person.currentData()))
        remove.clicked.connect(lambda: self.remove_entry(entry))
        self.set_read_only(self.read_only)
        self._refresh_height()
        if notify:
            self.changed.emit()
            self.activate_row(row)
            QTimer.singleShot(0, lambda: self._reveal(row))
        return entry

    def update(self, entry, field, value):
        setattr(entry, field, value)
        self.changed.emit()

    def remove_entry(self, entry):
        matching = next(r for r in self.rows if r[0] is entry)
        if self.active_row is matching[1]:
            self.clear_active()
        self._row_for_control = {c: r for c, r in self._row_for_control.items() if r is not matching[1]}
        self.row_layout.removeWidget(matching[1])
        matching[1].hide()
        matching[1].deleteLater()
        self.rows = [r for r in self.rows if r is not matching]
        self.entries = [e for e in self.entries if e is not entry]
        self._refresh_height()
        self.changed.emit()
