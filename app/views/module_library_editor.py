from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QFormLayout, QLineEdit, QComboBox, QSpinBox, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialogButtonBox, QColorDialog, QWidget, QFrame, QSplitter,
    QMessageBox, QAbstractItemView
)
from PyQt6.QtGui import QColor, QPixmap, QIcon
from PyQt6.QtCore import Qt

from app.storage.module_library import (
    ModuleDefinition, ConnectorSpec, CONNECTOR_TYPES,
    load_module_library, save_module_library
)
from app.models.daq import MODULE_TYPES


class ModuleLibraryEditor(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Module Library")
        self.resize(820, 560)
        self._defs: list[ModuleDefinition] = load_module_library()
        self._current_idx = -1
        self._building = False
        self._color_val = "#546e7a"
        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)

        # Left: list + add/delete
        left = QVBoxLayout()
        self._list = QListWidget()
        self._list.setMinimumWidth(200)
        self._list.currentRowChanged.connect(self._on_select)
        left.addWidget(QLabel("Modules:"))
        left.addWidget(self._list)
        btn_row = QHBoxLayout()
        btn_new = QPushButton("+ New")
        btn_new.clicked.connect(self._new_def)
        btn_del = QPushButton("Delete")
        btn_del.clicked.connect(self._delete_def)
        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_del)
        left.addLayout(btn_row)
        left_w = QWidget()
        left_w.setLayout(left)
        main_layout.addWidget(left_w)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        main_layout.addWidget(sep)

        # Right: edit form
        right = QVBoxLayout()
        form = QFormLayout()
        form.setSpacing(6)

        self._name = QLineEdit()
        form.addRow("Name:", self._name)

        self._mtype = QComboBox()
        self._mtype.addItems(MODULE_TYPES)
        form.addRow("Module Type:", self._mtype)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(28, 22)
        self._color_btn.clicked.connect(self._pick_color)
        self._color_label = QLabel("#546e7a")
        color_row.addWidget(self._color_btn)
        color_row.addWidget(self._color_label)
        color_row.addStretch()
        cw = QWidget(); cw.setLayout(color_row)
        form.addRow("Color:", cw)

        self._num_ch = QSpinBox()
        self._num_ch.setRange(0, 256)
        form.addRow("Num Channels:", self._num_ch)

        self._ch_start = QSpinBox()
        self._ch_start.setRange(0, 1)
        form.addRow("Channel Start (0/1):", self._ch_start)

        right.addLayout(form)

        # Connectors tables
        conn_layout = QHBoxLayout()
        for label, attr in [("Inputs", "_inputs_table"), ("Outputs", "_outputs_table")]:
            box = QVBoxLayout()
            lbl = QLabel(label + ":")
            tbl = QTableWidget(0, 3)
            tbl.setHorizontalHeaderLabels(["Name", "Type", "Channels"])
            tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            setattr(self, attr, tbl)
            btn_add = QPushButton(f"+ Add {label[:-1]}")
            btn_add.clicked.connect(lambda _, t=tbl: self._add_connector_row(t))
            btn_rem = QPushButton(f"Remove")
            btn_rem.clicked.connect(lambda _, t=tbl: self._remove_connector_row(t))
            row = QHBoxLayout()
            row.addWidget(btn_add)
            row.addWidget(btn_rem)
            box.addWidget(lbl)
            box.addWidget(tbl)
            box.addLayout(row)
            w = QWidget(); w.setLayout(box)
            conn_layout.addWidget(w)
        right.addLayout(conn_layout)

        # Save button
        save_row = QHBoxLayout()
        btn_save = QPushButton("Save to Library")
        btn_save.setStyleSheet("font-weight: bold;")
        btn_save.clicked.connect(self._save_current)
        save_row.addStretch()
        save_row.addWidget(btn_save)
        right.addLayout(save_row)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.accept)
        right.addWidget(btns)

        right_w = QWidget()
        right_w.setLayout(right)
        main_layout.addWidget(right_w, 1)

        self._set_form_enabled(False)

    def _make_swatch(self, color: str) -> QIcon:
        pix = QPixmap(16, 16)
        pix.fill(QColor(color))
        return QIcon(pix)

    def _populate_list(self):
        self._building = True
        self._list.clear()
        for d in self._defs:
            item = QListWidgetItem(self._make_swatch(d.color), d.name)
            self._list.addItem(item)
        self._building = False
        if self._defs:
            self._list.setCurrentRow(0)

    def _on_select(self, idx: int):
        if self._building or idx < 0 or idx >= len(self._defs):
            self._set_form_enabled(False)
            return
        self._current_idx = idx
        d = self._defs[idx]
        self._color_val = d.color
        self._building = True
        self._name.setText(d.name)
        self._mtype.setCurrentText(d.module_type)
        self._color_label.setText(d.color)
        self._color_btn.setStyleSheet(f"background-color: {d.color}; border: 1px solid #666;")
        self._num_ch.setValue(d.num_channels)
        self._ch_start.setValue(d.channel_start)
        self._fill_connector_table(self._inputs_table, d.inputs)
        self._fill_connector_table(self._outputs_table, d.outputs)
        self._building = False
        self._set_form_enabled(True)

    def _fill_connector_table(self, tbl: QTableWidget, specs: list[ConnectorSpec]):
        tbl.setRowCount(0)
        for spec in specs:
            row = tbl.rowCount()
            tbl.insertRow(row)
            tbl.setItem(row, 0, QTableWidgetItem(spec.name))
            combo = QComboBox()
            combo.addItems(CONNECTOR_TYPES)
            combo.setCurrentText(spec.type)
            tbl.setCellWidget(row, 1, combo)
            tbl.setItem(row, 2, QTableWidgetItem(str(spec.num_channels)))

    def _read_connector_table(self, tbl: QTableWidget) -> list[ConnectorSpec]:
        specs = []
        for row in range(tbl.rowCount()):
            name_item = tbl.item(row, 0)
            combo = tbl.cellWidget(row, 1)
            ch_item = tbl.item(row, 2)
            name = name_item.text().strip() if name_item else ""
            ctype = combo.currentText() if combo else "single"
            try:
                num_ch = int(ch_item.text()) if ch_item else 1
            except ValueError:
                num_ch = 1
            specs.append(ConnectorSpec(name=name, type=ctype, num_channels=num_ch))
        return specs

    def _add_connector_row(self, tbl: QTableWidget):
        row = tbl.rowCount()
        tbl.insertRow(row)
        tbl.setItem(row, 0, QTableWidgetItem(""))
        combo = QComboBox()
        combo.addItems(CONNECTOR_TYPES)
        tbl.setCellWidget(row, 1, combo)
        tbl.setItem(row, 2, QTableWidgetItem("1"))

    def _remove_connector_row(self, tbl: QTableWidget):
        row = tbl.currentRow()
        if row >= 0:
            tbl.removeRow(row)

    def _set_form_enabled(self, enabled: bool):
        for w in [self._name, self._mtype, self._color_btn,
                  self._num_ch, self._ch_start,
                  self._inputs_table, self._outputs_table]:
            w.setEnabled(enabled)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._color_val), self, "Choose Module Color")
        if color.isValid():
            self._color_val = color.name()
            self._color_label.setText(self._color_val)
            self._color_btn.setStyleSheet(
                f"background-color: {self._color_val}; border: 1px solid #666;"
            )
            if 0 <= self._current_idx < len(self._defs):
                self._list.item(self._current_idx).setIcon(self._make_swatch(self._color_val))

    def _new_def(self):
        defn = ModuleDefinition(
            id=f"MOD-{len(self._defs)+1:02d}",
            name="New Module",
            color="#546e7a",
            module_type="ADC",
            num_channels=16,
            channel_start=0,
        )
        self._defs.append(defn)
        self._populate_list()
        self._list.setCurrentRow(len(self._defs) - 1)

    def _delete_def(self):
        idx = self._current_idx
        if idx < 0 or idx >= len(self._defs):
            return
        self._defs.pop(idx)
        self._current_idx = -1
        self._populate_list()
        self._set_form_enabled(False)

    def _save_current(self):
        if 0 <= self._current_idx < len(self._defs):
            d = self._defs[self._current_idx]
            name = self._name.text().strip()
            if name:
                d.name = name
                d.id = name
            d.module_type = self._mtype.currentText()
            d.color = self._color_val
            d.num_channels = self._num_ch.value()
            d.channel_start = self._ch_start.value()
            d.inputs  = self._read_connector_table(self._inputs_table)
            d.outputs = self._read_connector_table(self._outputs_table)
            self._list.item(self._current_idx).setText(d.name)
            self._list.item(self._current_idx).setIcon(self._make_swatch(d.color))
        save_module_library(self._defs)
        QMessageBox.information(self, "Saved", "Module library saved.")
