from typing import Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QComboBox, QCompleter, QHeaderView, QAbstractItemView,
    QMessageBox, QSplitter, QTabWidget, QListWidget, QListWidgetItem,
    QColorDialog, QFrame, QStyledItemDelegate
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

from app.models.cable import Cable, CableBundle, SIGNAL_TYPES
from app.models.project import Project
from app.storage.cable_type import load_cable_types, CableType
from app.views.cable_type_editor import CableTypeEditor


class _ComboDelegate(QStyledItemDelegate):
    def __init__(self, items: list[str], parent=None):
        super().__init__(parent)
        self._items = list(items)

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems(self._items)
        return cb

    def setEditorData(self, editor, index):
        val = index.data(Qt.ItemDataRole.EditRole) or ""
        i = editor.findText(val)
        editor.setCurrentIndex(max(0, i))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class _EndpointDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._endpoint_ids: list[str] = []

    def set_endpoints(self, ids: list[str]):
        self._endpoint_ids = list(ids)

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        completer = QCompleter(self._endpoint_ids, editor)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        editor.setCompleter(completer)
        return editor

    def setEditorData(self, editor, index):
        editor.setText(index.data(Qt.ItemDataRole.EditRole) or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


COLUMNS = ["ID", "Label", "Type", "Signal Type", "From", "To", "Length (m)", "Notes"]
COL = {name: i for i, name in enumerate(COLUMNS)}
_TEXT_COLS = {COL["ID"], COL["Label"], COL["Length (m)"], COL["Notes"]}


class CableEditor(QWidget):
    def __init__(self, project: Project, on_change: Callable):
        super().__init__()
        self.project = project
        self.on_change = on_change
        self._building = False
        self._cable_types: list[CableType] = []
        self._type_name_to_id: dict[str, str] = {}
        self._type_id_to_name: dict[str, str] = {}
        self._endpoint_ids: list[str] = []
        self._current_bundle_idx = -1
        self._bundle_color_val = "#78909c"
        self._building_bundles = False
        self._reload_types()
        self._build_ui()
        self.refresh()

    def set_project(self, project: Project):
        self.project = project
        self.refresh()

    def _reload_types(self):
        self._cable_types = load_cable_types()
        self._type_name_to_id = {ct.name: ct.id for ct in self._cable_types}
        self._type_id_to_name = {ct.id: ct.name for ct in self._cable_types}

    def _build_endpoint_ids(self):
        ids = set(self.project.all_endpoint_ids())
        for cable in self.project.cables:
            if cable.from_endpoint:
                ids.add(cable.from_endpoint)
            if cable.to_endpoint:
                ids.add(cable.to_endpoint)
        self._endpoint_ids = sorted(ids)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        tabs = QTabWidget()
        tabs.addTab(self._build_cables_tab(), "Cables")
        tabs.addTab(self._build_bundles_tab(), "Bundles")
        layout.addWidget(tabs)

    def _build_cables_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

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

        splitter = QSplitter(Qt.Orientation.Horizontal)

        table_container = QWidget()
        tc_layout = QVBoxLayout(table_container)
        tc_layout.setContentsMargins(0, 0, 0, 0)
        tc_layout.setSpacing(4)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)
        self.table.itemChanged.connect(self._on_item_changed)
        self._type_delegate = _ComboDelegate([], self.table)
        self._sig_delegate = _ComboDelegate(list(SIGNAL_TYPES), self.table)
        self._endpoint_delegate = _EndpointDelegate(self.table)
        self.table.setItemDelegateForColumn(COL["Type"], self._type_delegate)
        self.table.setItemDelegateForColumn(COL["Signal Type"], self._sig_delegate)
        self.table.setItemDelegateForColumn(COL["From"], self._endpoint_delegate)
        self.table.setItemDelegateForColumn(COL["To"], self._endpoint_delegate)
        tc_layout.addWidget(self.table)

        prefix_row = QHBoxLayout()
        prefix_row.addWidget(QLabel("Auto-ID prefix:"))
        self.prefix_box = QLineEdit("CBL")
        self.prefix_box.setFixedWidth(80)
        prefix_row.addWidget(self.prefix_box)
        prefix_row.addStretch()
        tc_layout.addLayout(prefix_row)

        self.type_editor = CableTypeEditor()
        self.type_editor.types_changed.connect(self._on_types_changed)
        self.type_editor.setMinimumWidth(200)
        self.type_editor.setMaximumWidth(260)

        splitter.addWidget(table_container)
        splitter.addWidget(self.type_editor)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([900, 220])

        layout.addWidget(splitter)
        return w

    def _build_bundles_tab(self) -> QWidget:
        w = QWidget()
        outer = QHBoxLayout(w)
        outer.setContentsMargins(8, 8, 8, 8)

        # Left: bundle list
        left = QVBoxLayout()
        left.addWidget(QLabel("Cable Bundles:"))
        self._bundle_list = QListWidget()
        self._bundle_list.setMinimumWidth(180)
        self._bundle_list.currentRowChanged.connect(self._on_bundle_select)
        left.addWidget(self._bundle_list)
        btn_row = QHBoxLayout()
        btn_new_bundle = QPushButton("+ New")
        btn_new_bundle.clicked.connect(self._new_bundle)
        btn_del_bundle = QPushButton("Delete")
        btn_del_bundle.clicked.connect(self._delete_bundle)
        btn_row.addWidget(btn_new_bundle)
        btn_row.addWidget(btn_del_bundle)
        left.addLayout(btn_row)
        left_w = QWidget(); left_w.setLayout(left)
        outer.addWidget(left_w)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        outer.addWidget(sep)

        # Right: bundle detail
        right = QVBoxLayout()
        right.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._bundle_name = QLineEdit()
        name_row.addWidget(self._bundle_name)
        right.addLayout(name_row)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color:"))
        self._bundle_color_btn = QPushButton()
        self._bundle_color_btn.setFixedSize(28, 22)
        self._bundle_color_btn.clicked.connect(self._pick_bundle_color)
        self._bundle_color_label = QLabel(self._bundle_color_val)
        color_row.addWidget(self._bundle_color_btn)
        color_row.addWidget(self._bundle_color_label)
        color_row.addStretch()
        right.addLayout(color_row)
        self._update_bundle_color_btn()

        right.addWidget(QLabel("Member cables (check to include):"))
        self._bundle_cables = QListWidget()
        right.addWidget(self._bundle_cables)

        save_row = QHBoxLayout()
        btn_save_bundle = QPushButton("Save Bundle")
        btn_save_bundle.setStyleSheet("font-weight: bold;")
        btn_save_bundle.clicked.connect(self._save_bundle)
        save_row.addStretch()
        save_row.addWidget(btn_save_bundle)
        right.addLayout(save_row)

        right_w = QWidget(); right_w.setLayout(right)
        outer.addWidget(right_w, 1)

        self._set_bundle_form_enabled(False)
        return w

    def refresh(self):
        self._build_endpoint_ids()
        type_names = [ct.name for ct in self._cable_types]
        self._type_delegate._items = type_names
        self._endpoint_delegate.set_endpoints(self._endpoint_ids)
        self._building = True
        self.table.setRowCount(0)
        for cable in self.project.cables:
            self._insert_row(cable)
        self._building = False
        self._refresh_bundles()

    def _insert_row(self, cable: Cable):
        row = self.table.rowCount()
        self.table.insertRow(row)

        id_item = QTableWidgetItem(cable.id)
        id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, COL["ID"], id_item)

        self.table.setItem(row, COL["Label"], QTableWidgetItem(cable.label))

        current_name = self._type_id_to_name.get(cable.cable_type, cable.cable_type)
        self.table.setItem(row, COL["Type"], QTableWidgetItem(current_name))
        self.table.setItem(row, COL["Signal Type"], QTableWidgetItem(cable.signal_type))

        self.table.setItem(row, COL["From"], QTableWidgetItem(cable.from_endpoint))
        self.table.setItem(row, COL["To"], QTableWidgetItem(cable.to_endpoint))

        self.table.setItem(row, COL["Length (m)"], QTableWidgetItem(str(cable.length_m)))
        self.table.setItem(row, COL["Notes"], QTableWidgetItem(cable.notes))

        self._tint_row(row, cable.cable_type)

    def _tint_row(self, row: int, cable_type_id: str):
        color_map = {ct.id: ct.color for ct in self._cable_types}
        hex_color = color_map.get(cable_type_id, "#9e9e9e")
        bg = _blend_with_white(hex_color, 0.25)
        for col in _TEXT_COLS:
            item = self.table.item(row, col)
            if item:
                item.setBackground(bg)

    def _current_cable(self) -> Cable | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        id_item = self.table.item(row, COL["ID"])
        if id_item is None:
            return None
        return self.project.cable_by_id(id_item.text())

    def _add_cable(self):
        prefix = self.prefix_box.text().strip() or "CBL"
        cable = Cable(id=self.project.next_cable_id(prefix))
        self.project.cables.append(cable)
        self.refresh()
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
        self.refresh()
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
        if col == COL["Label"]:
            cable.label = text
        elif col == COL["Type"]:
            cable.cable_type = self._type_name_to_id.get(text, text)
            self._tint_row(item.row(), cable.cable_type)
        elif col == COL["Signal Type"]:
            cable.signal_type = text
        elif col == COL["From"]:
            cable.from_endpoint = text
        elif col == COL["To"]:
            cable.to_endpoint = text
        elif col == COL["Length (m)"]:
            try:
                cable.length_m = float(text)
            except ValueError:
                pass
        elif col == COL["Notes"]:
            cable.notes = text
        self.on_change()

    # ── Bundle management ──────────────────────────────────────────────────────

    def _refresh_bundles(self):
        self._building_bundles = True
        self._bundle_list.clear()
        for bundle in self.project.bundles:
            self._bundle_list.addItem(bundle.name or bundle.id)
        self._building_bundles = False
        if self.project.bundles:
            self._bundle_list.setCurrentRow(0)
        else:
            self._set_bundle_form_enabled(False)

    def _on_bundle_select(self, idx: int):
        if self._building_bundles or idx < 0 or idx >= len(self.project.bundles):
            return
        self._current_bundle_idx = idx
        bundle = self.project.bundles[idx]
        self._bundle_color_val = bundle.color
        self._bundle_name.setText(bundle.name)
        self._update_bundle_color_btn()
        self._bundle_color_label.setText(bundle.color)
        self._building_bundles = True
        self._bundle_cables.clear()
        for cable in self.project.cables:
            item = QListWidgetItem(f"{cable.id}  {cable.label}")
            item.setData(Qt.ItemDataRole.UserRole, cable.id)
            item.setCheckState(
                Qt.CheckState.Checked if cable.id in bundle.cable_ids
                else Qt.CheckState.Unchecked
            )
            self._bundle_cables.addItem(item)
        self._building_bundles = False
        self._set_bundle_form_enabled(True)

    def _set_bundle_form_enabled(self, enabled: bool):
        self._bundle_name.setEnabled(enabled)
        self._bundle_color_btn.setEnabled(enabled)
        self._bundle_cables.setEnabled(enabled)

    def _update_bundle_color_btn(self):
        self._bundle_color_btn.setStyleSheet(
            f"background-color: {self._bundle_color_val}; border: 1px solid #666;"
        )

    def _pick_bundle_color(self):
        color = QColorDialog.getColor(QColor(self._bundle_color_val), self, "Bundle Color")
        if color.isValid():
            self._bundle_color_val = color.name()
            self._bundle_color_label.setText(self._bundle_color_val)
            self._update_bundle_color_btn()

    def _new_bundle(self):
        bundle = CableBundle(
            id=f"BUNDLE-{len(self.project.bundles)+1:02d}",
            name=f"Bundle {len(self.project.bundles)+1}",
        )
        self.project.bundles.append(bundle)
        self._refresh_bundles()
        self._bundle_list.setCurrentRow(len(self.project.bundles) - 1)
        self.on_change()

    def _delete_bundle(self):
        idx = self._current_bundle_idx
        if idx < 0 or idx >= len(self.project.bundles):
            return
        self.project.bundles.pop(idx)
        self._current_bundle_idx = -1
        self._refresh_bundles()
        self.on_change()

    def _save_bundle(self):
        idx = self._current_bundle_idx
        if idx < 0 or idx >= len(self.project.bundles):
            return
        bundle = self.project.bundles[idx]
        bundle.name = self._bundle_name.text().strip() or bundle.name
        bundle.color = self._bundle_color_val
        bundle.cable_ids = []
        for row in range(self._bundle_cables.count()):
            item = self._bundle_cables.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                bundle.cable_ids.append(item.data(Qt.ItemDataRole.UserRole))
        list_item = self._bundle_list.item(idx)
        if list_item:
            list_item.setText(bundle.name)
        self.on_change()

    def _on_types_changed(self):
        self._reload_types()
        self.refresh()

    def _apply_filter(self, text: str):
        text = text.lower()
        for row in range(self.table.rowCount()):
            match = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                cell_text = item.text().lower() if item else ""
                if text in cell_text:
                    match = True
                    break
            self.table.setRowHidden(row, not match)


def _blend_with_white(hex_color: str, alpha: float = 0.25) -> QColor:
    c = QColor(hex_color)
    r = int(c.red() * alpha + 255 * (1 - alpha))
    g = int(c.green() * alpha + 255 * (1 - alpha))
    b = int(c.blue() * alpha + 255 * (1 - alpha))
    return QColor(r, g, b)
