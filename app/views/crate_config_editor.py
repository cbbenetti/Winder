from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QGroupBox, QFormLayout, QLineEdit, QSpinBox,
    QComboBox, QDialogButtonBox, QMessageBox
)
from PyQt6.QtCore import Qt

from app.models.daq import CRATE_TYPES
from app.storage.crate_config import CrateConfig, load_configs, save_configs


class CrateConfigEditor(QDialog):
    """Dialog for managing saved crate configuration templates."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crate Configuration Templates")
        self.resize(600, 380)
        self.configs = load_configs()
        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        # Left: list + buttons
        left = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_selection)
        left.addWidget(self.list_widget)

        btns = QHBoxLayout()
        self.btn_add = QPushButton("+ New")
        self.btn_add.clicked.connect(self._add_config)
        self.btn_del = QPushButton("Delete")
        self.btn_del.clicked.connect(self._delete_config)
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_del)
        left.addLayout(btns)
        layout.addLayout(left, 1)

        # Right: detail form
        box = QGroupBox("Template Details")
        form = QFormLayout(box)
        self.f_name = QLineEdit()
        self.f_name.editingFinished.connect(self._save_current)
        self.f_type = QComboBox()
        self.f_type.addItems(CRATE_TYPES)
        self.f_type.currentTextChanged.connect(self._save_current)
        self.f_slots = QSpinBox()
        self.f_slots.setRange(1, 100)
        self.f_slots.editingFinished.connect(self._save_current)
        self.f_desc = QLineEdit()
        self.f_desc.editingFinished.connect(self._save_current)
        form.addRow("Name:", self.f_name)
        form.addRow("Crate Type:", self.f_type)
        form.addRow("Number of Slots:", self.f_slots)
        form.addRow("Description:", self.f_desc)
        layout.addWidget(box, 2)

        # Bottom: OK/Cancel
        outer = QVBoxLayout()
        outer.addLayout(layout)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(self._commit)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
        outer.addWidget(buttons)
        self.setLayout(outer)

    def _populate_list(self):
        self.list_widget.clear()
        for cfg in self.configs:
            item = QListWidgetItem(f"{cfg.name}  [{cfg.crate_type}, {cfg.num_slots} slots]")
            self.list_widget.addItem(item)
        if self.configs:
            self.list_widget.setCurrentRow(0)

    def _on_selection(self, row: int):
        if row < 0 or row >= len(self.configs):
            return
        cfg = self.configs[row]
        self.f_name.blockSignals(True)
        self.f_type.blockSignals(True)
        self.f_slots.blockSignals(True)
        self.f_desc.blockSignals(True)
        self.f_name.setText(cfg.name)
        self.f_type.setCurrentText(cfg.crate_type)
        self.f_slots.setValue(cfg.num_slots)
        self.f_desc.setText(cfg.description)
        self.f_name.blockSignals(False)
        self.f_type.blockSignals(False)
        self.f_slots.blockSignals(False)
        self.f_desc.blockSignals(False)

    def _save_current(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.configs):
            return
        cfg = self.configs[row]
        cfg.name = self.f_name.text().strip() or cfg.name
        cfg.crate_type = self.f_type.currentText()
        cfg.num_slots = self.f_slots.value()
        cfg.description = self.f_desc.text().strip()
        self.list_widget.item(row).setText(
            f"{cfg.name}  [{cfg.crate_type}, {cfg.num_slots} slots]"
        )

    def _add_config(self):
        existing_ids = {c.id for c in self.configs}
        n = len(self.configs) + 1
        while f"custom-{n}" in existing_ids:
            n += 1
        cfg = CrateConfig(
            id=f"custom-{n}",
            name="New Template",
            crate_type="VME",
            num_slots=20,
        )
        self.configs.append(cfg)
        item = QListWidgetItem(f"{cfg.name}  [{cfg.crate_type}, {cfg.num_slots} slots]")
        self.list_widget.addItem(item)
        self.list_widget.setCurrentRow(len(self.configs) - 1)

    def _delete_config(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        cfg = self.configs[row]
        reply = QMessageBox.question(
            self, "Delete Template", f"Delete '{cfg.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.configs.pop(row)
        self.list_widget.takeItem(row)

    def _commit(self):
        self._save_current()
        save_configs(self.configs)
        QMessageBox.information(self, "Saved", "Crate templates saved.")
