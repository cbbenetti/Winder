from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QFormLayout, QLineEdit, QComboBox, QPushButton, QLabel,
    QColorDialog, QFrame
)
from PyQt6.QtGui import QColor, QPixmap, QIcon
from PyQt6.QtCore import Qt, pyqtSignal

from app.storage.cable_type import CableType, CONNECTOR_TYPES, load_cable_types, save_cable_types
from app.models.cable import SIGNAL_TYPES


class CableTypeEditor(QWidget):
    types_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._types: list[CableType] = load_cable_types()
        self._current_idx = -1
        self._current_color = "#9e9e9e"
        self._building = False
        self._build_ui()
        self._populate_list()

    def reload(self):
        self._types = load_cable_types()
        self._populate_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        lbl = QLabel("Cable Types")
        lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(180)
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self.list_widget)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 4)
        form.setSpacing(4)

        self._name = QLineEdit()
        form.addRow("Name:", self._name)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(28, 22)
        self._color_btn.clicked.connect(self._pick_color)
        self._color_label = QLabel("#9e9e9e")
        color_row.addWidget(self._color_btn)
        color_row.addWidget(self._color_label)
        color_row.addStretch()
        color_widget = QWidget()
        color_widget.setLayout(color_row)
        form.addRow("Color:", color_widget)

        self._connector = QComboBox()
        self._connector.addItems(CONNECTOR_TYPES)
        form.addRow("Connector:", self._connector)

        self._signal = QComboBox()
        self._signal.addItems(SIGNAL_TYPES)
        form.addRow("Signal:", self._signal)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_new = QPushButton("+ New")
        btn_new.clicked.connect(self._new_type)
        btn_del = QPushButton("Delete")
        btn_del.clicked.connect(self._delete_type)
        btn_save = QPushButton("Save")
        btn_save.setStyleSheet("font-weight: bold;")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)
        layout.addStretch()

        self._set_form_enabled(False)

    def _make_swatch(self, color: str) -> QIcon:
        pix = QPixmap(16, 16)
        pix.fill(QColor(color))
        return QIcon(pix)

    def _populate_list(self):
        self._building = True
        self.list_widget.clear()
        for ct in self._types:
            item = QListWidgetItem(self._make_swatch(ct.color), ct.name)
            self.list_widget.addItem(item)
        self._building = False
        if self._types:
            self.list_widget.setCurrentRow(0)
        else:
            self._set_form_enabled(False)

    def _on_selection_changed(self, idx: int):
        if self._building or idx < 0 or idx >= len(self._types):
            self._set_form_enabled(False)
            return
        self._current_idx = idx
        ct = self._types[idx]
        self._current_color = ct.color
        self._building = True
        self._name.setText(ct.name)
        self._color_label.setText(ct.color)
        self._color_btn.setStyleSheet(
            f"background-color: {ct.color}; border: 1px solid #666;"
        )
        self._connector.setCurrentText(ct.connector_type)
        self._signal.setCurrentText(ct.default_signal_type)
        self._building = False
        self._set_form_enabled(True)

    def _set_form_enabled(self, enabled: bool):
        self._name.setEnabled(enabled)
        self._color_btn.setEnabled(enabled)
        self._connector.setEnabled(enabled)
        self._signal.setEnabled(enabled)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._current_color), self, "Choose Cable Color")
        if color.isValid():
            self._current_color = color.name()
            self._color_label.setText(self._current_color)
            self._color_btn.setStyleSheet(
                f"background-color: {self._current_color}; border: 1px solid #666;"
            )
            if 0 <= self._current_idx < len(self._types):
                self.list_widget.item(self._current_idx).setIcon(
                    self._make_swatch(self._current_color)
                )

    def _new_type(self):
        ct = CableType(
            id=f"TYPE-{len(self._types)+1:02d}",
            name="New Type",
            color="#9e9e9e",
            connector_type="BNC",
            default_signal_type="Analog",
        )
        self._types.append(ct)
        self._populate_list()
        self.list_widget.setCurrentRow(len(self._types) - 1)

    def _delete_type(self):
        idx = self._current_idx
        if idx < 0 or idx >= len(self._types):
            return
        self._types.pop(idx)
        self._current_idx = -1
        self._populate_list()
        self._set_form_enabled(False)

    def _save(self):
        if 0 <= self._current_idx < len(self._types):
            ct = self._types[self._current_idx]
            name = self._name.text().strip()
            if name:
                ct.name = name
                ct.id = name  # keep id in sync with name for user-defined types
            ct.color = self._current_color
            ct.connector_type = self._connector.currentText()
            ct.default_signal_type = self._signal.currentText()
            self.list_widget.item(self._current_idx).setText(ct.name)
            self.list_widget.item(self._current_idx).setIcon(self._make_swatch(ct.color))
        save_cable_types(self._types)
        self.types_changed.emit()
