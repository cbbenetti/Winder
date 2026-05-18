from typing import Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QComboBox, QHeaderView, QAbstractItemView,
    QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt

from app.models.cable import Cable, CABLE_TYPES, SIGNAL_TYPES
from app.models.project import Project


COLUMNS = ["ID", "Label", "Type", "Signal Type", "From", "To", "Length (m)", "Notes"]
COL = {name: i for i, name in enumerate(COLUMNS)}


class CableEditor(QWidget):
    def __init__(self, project: Project, on_change: Callable):
        super().__init__()
        self.project = project
        self.on_change = on_change
        self._building = False
        self._build_ui()
        self.refresh()

    def set_project(self, project: Project):
        self.project = project
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("+ Add Cable")
        self.btn_add.clicked.connect(self._add_cable)
        self.btn_dup = QPushButton("Duplicate")
        self.btn_dup.clicked.connect(self._duplicate_cable)
        self.btn_del = QPushButton("Delete")
        self.btn_del.clicked.connect(self._delete_cable)
        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_dup)
        toolbar.addWidget(self.btn_del)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("Filter:"))
        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Search cables…")
        self.filter_box.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.filter_box)
        layout.addLayout(toolbar)

        # Table
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        # Prefix row
        prefix_row = QHBoxLayout()
        prefix_row.addWidget(QLabel("Auto-ID prefix:"))
        self.prefix_box = QLineEdit("CBL")
        self.prefix_box.setFixedWidth(80)
        prefix_row.addWidget(self.prefix_box)
        prefix_row.addStretch()
        layout.addLayout(prefix_row)

    def refresh(self):
        self._building = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for cable in self.project.cables:
            self._insert_row(cable)
        self.table.setSortingEnabled(True)
        self._building = False

    def _insert_row(self, cable: Cable):
        row = self.table.rowCount()
        self.table.insertRow(row)
        items = [
            cable.id, cable.label, cable.cable_type, cable.signal_type,
            cable.from_endpoint, cable.to_endpoint,
            str(cable.length_m), cable.notes
        ]
        for col, text in enumerate(items):
            item = QTableWidgetItem(text)
            if col == COL["ID"]:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col, item)

    def _current_cable(self) -> Cable | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        cable_id = self.table.item(row, COL["ID"])
        if cable_id is None:
            return None
        return self.project.cable_by_id(cable_id.text())

    def _add_cable(self):
        prefix = self.prefix_box.text().strip() or "CBL"
        cable = Cable(id=self.project.next_cable_id(prefix))
        self.project.cables.append(cable)
        self._building = True
        self.table.setSortingEnabled(False)
        self._insert_row(cable)
        self.table.setSortingEnabled(True)
        self._building = False
        self.on_change()

    def _duplicate_cable(self):
        cable = self._current_cable()
        if cable is None:
            return
        prefix = self.prefix_box.text().strip() or "CBL"
        new_cable = Cable(
            id=self.project.next_cable_id(prefix),
            label=cable.label,
            cable_type=cable.cable_type,
            signal_type=cable.signal_type,
            from_endpoint=cable.from_endpoint,
            to_endpoint=cable.to_endpoint,
            length_m=cable.length_m,
            notes=cable.notes,
        )
        self.project.cables.append(new_cable)
        self._building = True
        self.table.setSortingEnabled(False)
        self._insert_row(new_cable)
        self.table.setSortingEnabled(True)
        self._building = False
        self.on_change()

    def _delete_cable(self):
        cable = self._current_cable()
        if cable is None:
            return
        reply = QMessageBox.question(
            self, "Delete Cable", f"Delete cable {cable.id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.project.cables.remove(cable)
        self.refresh()
        self.on_change()

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._building:
            return
        row = item.row()
        col = item.column()
        id_item = self.table.item(row, COL["ID"])
        if id_item is None:
            return
        cable = self.project.cable_by_id(id_item.text())
        if cable is None:
            return
        text = item.text()
        field_map = {
            COL["Label"]: "label",
            COL["Type"]: "cable_type",
            COL["Signal Type"]: "signal_type",
            COL["From"]: "from_endpoint",
            COL["To"]: "to_endpoint",
            COL["Notes"]: "notes",
        }
        if col in field_map:
            setattr(cable, field_map[col], text)
        elif col == COL["Length (m)"]:
            try:
                cable.length_m = float(text)
            except ValueError:
                pass
        self.on_change()

    def _apply_filter(self, text: str):
        text = text.lower()
        for row in range(self.table.rowCount()):
            match = any(
                text in (self.table.item(row, col).text().lower() if self.table.item(row, col) else "")
                for col in range(self.table.columnCount())
            )
            self.table.setRowHidden(row, not match)
