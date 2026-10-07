"""Small native Qt components shared by the two person pages."""

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QLabel, QStyle, QStyleOptionButton,
    QStyleOptionViewItem, QStyledItemDelegate, QTableView,
    QHBoxLayout, QPushButton, QWidget, QDialog, QVBoxLayout, QSizePolicy,
)

from config.paths import DATA_ROOT, resolve_image_path
from services.people import age_from_identity, work_years


def task_row_widget(parent, text, remove_callback, *, tooltip, button_name, constrain_name=False):
    """DPI-aware task row, shared by person and engineering output lists."""
    widget = QWidget(parent)
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(8, 5, 7, 5)
    layout.setSpacing(9)
    handle = QLabel('≡')
    handle.setStyleSheet('color: #637c99; font-size: 17px;')
    label = QLabel(text)
    if constrain_name:
        from PySide6.QtWidgets import QSizePolicy
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        label.setToolTip(text)
    layout.addWidget(handle)
    layout.addWidget(label, 1 if constrain_name else 0)
    if not constrain_name:
        layout.addStretch()
    remove = QPushButton('×')
    remove.setObjectName(button_name)
    remove.setToolTip(tooltip)
    remove.setFont(QFont('Segoe UI', 12))
    remove.setFixedSize(24, 24)
    remove.setFocusPolicy(Qt.NoFocus)
    remove.clicked.connect(remove_callback)
    layout.addWidget(remove)
    widget.ensurePolished()
    layout.activate()
    inset = layout.contentsMargins().top() + layout.contentsMargins().bottom()
    height = max(widget.sizeHint().height(), label.fontMetrics().height() + inset, remove.height() + inset)
    widget.setMinimumHeight(height)
    return widget, QSize(0, height)


def format_person_summary(detail):
    """Shared display text for the two read-only person workspaces."""
    labels = (("姓名", "姓名"), ("身份证号", "身份证号"), ("联系电话", "联系电话"),
              ("学历", "学历"), ("毕业院校", "毕业院校"), ("专业", "专业"),
              ("进入系统日期", "入职日期"))
    age = age_from_identity(detail["身份证号"])
    tenure = work_years(detail["进入系统日期"])
    summary = [f"{label}：{detail[key] or '—'}" for key, label in labels]
    summary.extend((f"年龄：{age if age is not None else '—'}",
                    f"工龄：{tenure if tenure is not None else '—'}"))
    return "    ".join(summary)


class RowsModel(QAbstractTableModel):
    def __init__(self, columns, parent=None, *, check_key=None, checked=None):
        super().__init__(parent)
        self.columns = columns
        self.rows = []
        self.check_key = check_key
        self.checked = checked if checked is not None else set()
        self.active_id = None

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section][0]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if self.check_key and index.column() == 0 and role == Qt.CheckStateRole:
            return Qt.Checked if row[self.check_key] in self.checked else Qt.Unchecked
        if self.check_key and index.column() == 0 and role == Qt.BackgroundRole:
            if row[self.check_key] == self.active_id:
                dark = QApplication.palette().base().color().lightness() < 128
                return QBrush(QColor('#354f70' if dark else '#cfe3fa'))
            return None
        if role == Qt.DisplayRole:
            key = self.columns[index.column()][1]
            value = row.get(key, "")
            return "" if value is None else str(value)
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and self.check_key and index.column() == 0:
            return flags | Qt.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or not self.check_key or index.column() != 0 or role != Qt.CheckStateRole:
            return False
        if value not in (Qt.Checked, Qt.Unchecked):
            return False
        key = self.rows[index.row()][self.check_key]
        if value == Qt.Checked:
            self.checked.add(key)
        else:
            self.checked.discard(key)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole])
        return True

    def set_active_id(self, record_id):
        if self.active_id == record_id:
            return
        old_id = self.active_id
        self.active_id = record_id
        for row_number, row in enumerate(self.rows):
            if row[self.check_key] in (old_id, record_id):
                index = self.index(row_number, 0)
                self.dataChanged.emit(index, index, [Qt.BackgroundRole])

    def record(self, index):
        return self.rows[index.row()] if index.isValid() and index.row() < len(self.rows) else None


class TaskRowsModel(RowsModel):
    """Read-only browsing until an existing output task owns the check set."""

    checks_enabled = False

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0 and not self.checks_enabled:
            flags &= ~(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and not self.checks_enabled:
            return False
        return super().setData(index, value, role)


class CheckBoxDelegate(QStyledItemDelegate):
    """Paint a real Qt checkbox independent of the table's selection style."""

    def paint(self, painter, option, index):
        painter.save()
        brush = index.data(Qt.BackgroundRole)
        painter.fillRect(option.rect, brush if brush is not None else option.palette.base())
        checkbox = QStyleOptionButton()
        checkbox.rect = QRect(option.rect.center().x() - 8, option.rect.center().y() - 8, 16, 16)
        checkbox.state = QStyle.State_Enabled if index.flags() & Qt.ItemIsEnabled else QStyle.State_None
        checkbox.state |= QStyle.State_On if index.data(Qt.CheckStateRole) == Qt.Checked else QStyle.State_Off
        style = option.widget.style() if option.widget is not None else QApplication.style()
        style.drawPrimitive(QStyle.PE_IndicatorCheckBox, checkbox, painter, option.widget)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if index.column() == 0 and model.check_key and (
            (event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton
             and option.rect.contains(event.position().toPoint()))
            or (event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space)
        ):
            checked = model.data(index, Qt.CheckStateRole) == Qt.Checked
            return model.setData(index, Qt.Unchecked if checked else Qt.Checked, Qt.CheckStateRole)
        return super().editorEvent(event, model, option, index)


class CertificateTextDelegate(QStyledItemDelegate):
    """Selection remains functional without painting backgrounds outside column 0."""

    def paint(self, painter, option, index):
        plain = QStyleOptionViewItem(option)
        plain.state &= ~(QStyle.State_Selected | QStyle.State_HasFocus)
        super().paint(painter, plain, index)


class StyledComboBox(QComboBox):
    """Keep the editable native combo and draw a clear, theme-matched arrow."""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.palette().buttonText().color() if self.isEnabled() else QColor('#9caec0'), 1.8))
        x, y = self.width() - 14, self.height() // 2
        painter.drawLine(x - 4, y - 2, x, y + 2)
        painter.drawLine(x, y + 2, x + 4, y - 2)


def table_view(model):
    view = QTableView()
    view.setModel(model)
    view.setSelectionBehavior(QAbstractItemView.SelectRows)
    view.setSelectionMode(QAbstractItemView.SingleSelection)
    view.setAlternatingRowColors(True)
    view.verticalHeader().hide()
    view.horizontalHeader().setStretchLastSection(True)
    return view


class ImageViewer(QDialog):
    """Resizable view retaining the source pixmap rather than a thumbnail."""

    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle('附件大图')
        self.original_pixmap = QPixmap(pixmap)
        layout = QVBoxLayout(self)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        layout.addWidget(self.image, 1)
        close = QPushButton('关闭')
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignRight)
        available = self.screen().availableGeometry()
        self.resize(int(available.width() * .85), int(available.height() * .85))
        self.setMaximumSize(available.size())
        self.image.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.image and event.type() == QEvent.Resize:
            self.image.setPixmap(self.original_pixmap.scaled(
                self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return super().eventFilter(watched, event)


class ImagePreview(QLabel):
    def __init__(self, *, data_root=DATA_ROOT, large_view_enabled=False):
        super().__init__("选择附件以预览")
        self.data_root = data_root
        self.setObjectName("imagePreview")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(190)
        self.setWordWrap(True)
        self._pixmap = None
        self.large_view_enabled = large_view_enabled
        # The scaled thumbnail must not feed its previous size back into layout.
        if large_view_enabled:
            self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.large_view_enabled and self._pixmap is not None and not self._pixmap.isNull():
            viewer = ImageViewer(self._pixmap, self)
            try:
                viewer.exec()
            finally:
                viewer.deleteLater()
        else:
            super().mousePressEvent(event)

    def show_path(self, relative_path):
        self._pixmap = None
        self.setCursor(Qt.ArrowCursor)
        if not relative_path:
            self.setText("选择附件以预览")
            return
        try:
            path = resolve_image_path(relative_path, data_root=self.data_root)
        except (TypeError, ValueError) as error:
            self.setText(f"无效图片路径：{error}")
            return
        if not path.is_file():
            self.setText(f"图片文件尚未就位\n{relative_path}")
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.setText(f"无法读取图片\n{relative_path}")
            return
        self._pixmap = pixmap
        if self.large_view_enabled:
            self.setCursor(Qt.PointingHandCursor)
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if self._pixmap:
            self.setPixmap(self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
