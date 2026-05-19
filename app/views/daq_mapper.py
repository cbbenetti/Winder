from typing import Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QMenu, QDialog, QFormLayout, QLineEdit, QSpinBox,
    QComboBox, QDialogButtonBox, QMessageBox, QHeaderView, QColorDialog,
    QCheckBox, QLabel, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from app.models.daq import DaqCrate, DaqSlot, DaqModule, DaqChannel, CRATE_TYPES, MODULE_TYPES
from app.models.project import Project
from app.storage.crate_config import load_configs


LEVEL_CRATE   = 0
LEVEL_SLOT    = 1
LEVEL_MODULE  = 2
LEVEL_CHANNEL = 3


class DaqMapper(QWidget):
    def __init__(self, project: Project, on_change: Callable):
        super().__init__()
        self.project = project
        self.on_change = on_change
        self._build_ui()
        self.refresh()

    def set_project(self, project: Project):
        self.project = project
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()
        btn_crate = QPushButton("+ Add Crate")
        btn_crate.clicked.connect(self._add_crate)
        toolbar.addWidget(btn_crate)
        btn_templates = QPushButton("Manage Templates…")
        btn_templates.clicked.connect(self._manage_templates)
        toolbar.addWidget(btn_templates)
        btn_library = QPushButton("Module Library…")
        btn_library.clicked.connect(self._module_library)
        toolbar.addWidget(btn_library)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Name / Label", "Type / Ch#", "Cable ID", "Signal Label", "Notes"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)

    def refresh(self):
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            for crate in self.project.crates:
                crate_item = self._make_crate_item(crate)
                self.tree.addTopLevelItem(crate_item)
                crate_item.setExpanded(True)
                for slot in crate.slots:
                    slot_item = self._make_slot_item(slot)
                    crate_item.addChild(slot_item)
                    slot_item.setExpanded(True)
                    if slot.module:
                        mod_item = self._make_module_item(slot.module)
                        slot_item.addChild(mod_item)
                        mod_item.setExpanded(True)
                        for ch in slot.module.channels:
                            mod_item.addChild(self._make_channel_item(ch))
        finally:
            self.tree.blockSignals(False)

    def _make_crate_item(self, crate: DaqCrate) -> QTreeWidgetItem:
        item = QTreeWidgetItem([crate.name or crate.id, crate.crate_type, "", "", ""])
        item.setData(0, Qt.ItemDataRole.UserRole, ("crate", crate.id))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        return item

    def _make_slot_item(self, slot: DaqSlot) -> QTreeWidgetItem:
        label = f"Slot {slot.slot_number:02d}"
        type_label = slot.module.module_type if slot.module else slot.module_type
        item = QTreeWidgetItem([label, type_label, "", "", ""])
        item.setData(0, Qt.ItemDataRole.UserRole, ("slot", slot.id))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _make_module_item(self, module: DaqModule) -> QTreeWidgetItem:
        item = QTreeWidgetItem([module.name or module.id, module.module_type, "", "", ""])
        item.setData(0, Qt.ItemDataRole.UserRole, ("module", module.id))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        color = QColor(module.color)
        color.setAlpha(80)
        for col in range(5):
            item.setBackground(col, color)
        return item

    def _make_channel_item(self, ch: DaqChannel) -> QTreeWidgetItem:
        role_text = "IN ▸" if ch.role != "output" else "◂ OUT"
        if ch.connector:
            role_text += f"  {ch.connector}"
        item = QTreeWidgetItem([role_text, str(ch.channel_number), ch.cable_id, ch.signal_label, ch.notes])
        item.setData(0, Qt.ItemDataRole.UserRole, ("channel", ch.id))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        color = QColor("#e3f2fd") if ch.role != "output" else QColor("#fce4ec")
        item.setBackground(0, color)
        item.setBackground(1, color)
        return item

    def _context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        if item is None:
            menu.addAction("Add Crate", self._add_crate)
        else:
            tag, obj_id = item.data(0, Qt.ItemDataRole.UserRole)
            if tag == "crate":
                menu.addAction("Add Slot", lambda: self._add_slot(obj_id))
                menu.addAction("Delete Crate", lambda: self._delete_crate(obj_id))
            elif tag == "slot":
                menu.addAction("Add Module", lambda: self._add_module(obj_id))
                menu.addAction("Delete Slot", lambda: self._delete_slot(obj_id))
            elif tag == "module":
                menu.addAction("Add Channel", lambda: self._add_channel(obj_id))
                menu.addAction("Delete Module", lambda: self._delete_module(obj_id))
            elif tag == "channel":
                menu.addAction("Toggle Input/Output", lambda: self._toggle_channel_role(obj_id))
                menu.addAction("Delete Channel", lambda: self._delete_channel(obj_id))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # ── Finders ────────────────────────────────────────────────────────────────

    def _find_crate(self, crate_id: str) -> DaqCrate | None:
        return next((c for c in self.project.crates if c.id == crate_id), None)

    def _find_slot(self, slot_id: str) -> tuple[DaqCrate, DaqSlot] | None:
        for crate in self.project.crates:
            for slot in crate.slots:
                if slot.id == slot_id:
                    return crate, slot
        return None

    def _find_module(self, module_id: str) -> tuple[DaqCrate, DaqSlot, DaqModule] | None:
        for crate in self.project.crates:
            for slot in crate.slots:
                if slot.module and slot.module.id == module_id:
                    return crate, slot, slot.module
        return None

    def _find_channel(self, ch_id: str) -> tuple[DaqSlot, DaqModule, DaqChannel] | None:
        for crate in self.project.crates:
            for slot in crate.slots:
                if slot.module:
                    for ch in slot.module.channels:
                        if ch.id == ch_id:
                            return slot, slot.module, ch
        return None

    # ── Actions ────────────────────────────────────────────────────────────────

    def _manage_templates(self):
        from app.views.crate_config_editor import CrateConfigEditor
        CrateConfigEditor(self).exec()

    def _module_library(self):
        from app.views.module_library_editor import ModuleLibraryEditor
        ModuleLibraryEditor(self).exec()

    def _add_crate(self):
        dlg = _CrateDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        crate = DaqCrate(
            id=self.project.next_crate_id(),
            name=dlg.name(),
            crate_type=dlg.crate_type(),
        )
        for i in range(dlg.slots_to_create()):
            crate.slots.append(DaqSlot(
                id=f"{crate.id}-SL{i:02d}",
                slot_number=i,
                module_type="ADC",
            ))
        self.project.crates.append(crate)
        self.refresh()
        self.on_change()

    def _add_slot(self, crate_id: str):
        crate = self._find_crate(crate_id)
        if crate is None:
            return
        dlg = _SlotDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        existing_slots = {s.slot_number for s in crate.slots}
        slot_num = dlg.slot_number()
        if slot_num in existing_slots:
            QMessageBox.warning(self, "Duplicate", f"Slot {slot_num} already exists in {crate.name}.")
            return
        slot = DaqSlot(
            id=f"{crate.id}-SL{slot_num:02d}",
            slot_number=slot_num,
            module_type=dlg.module_type(),
        )
        crate.slots.append(slot)
        crate.slots.sort(key=lambda s: s.slot_number)
        self.refresh()
        self.on_change()

    def _add_module(self, slot_id: str):
        result = self._find_slot(slot_id)
        if result is None:
            return
        crate, slot = result
        if slot.module is not None:
            QMessageBox.warning(
                self, "Module exists",
                f"Slot {slot.slot_number} already has a module.\n"
                "Delete it first to replace it."
            )
            return
        dlg = _ModuleDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        mod_id = slot.id + "-MOD"
        module = DaqModule(
            id=mod_id,
            name=dlg.name(),
            module_type=dlg.module_type(),
            color=dlg.color(),
            channel_start=dlg.channel_start(),
            coupled_io=dlg.coupled_io(),
        )
        start = dlg.channel_start()
        defn = dlg._selected_def
        if defn is not None and (defn.inputs or defn.outputs):
            if module.coupled_io:
                all_specs = list(defn.inputs) + list(defn.outputs)
                ch_per_spec = max((s.num_channels for s in all_specs), default=0)
                for k in range(ch_per_spec):
                    ch_num = start + k
                    for s_idx, spec in enumerate(defn.inputs):
                        if k < spec.num_channels:
                            module.channels.append(DaqChannel(
                                id=f"{slot.id}-I{s_idx}-{ch_num:02d}",
                                channel_number=ch_num,
                                role="input",
                                connector=spec.name,
                            ))
                    for s_idx, spec in enumerate(defn.outputs):
                        if k < spec.num_channels:
                            module.channels.append(DaqChannel(
                                id=f"{slot.id}-O{s_idx}-{ch_num:02d}",
                                channel_number=ch_num,
                                role="output",
                                connector=spec.name,
                            ))
            else:
                ch_num = start
                for spec in defn.inputs:
                    for _ in range(spec.num_channels):
                        module.channels.append(DaqChannel(
                            id=f"{slot.id}-CH{ch_num:02d}",
                            channel_number=ch_num,
                            role="input",
                        ))
                        ch_num += 1
                for spec in defn.outputs:
                    for _ in range(spec.num_channels):
                        module.channels.append(DaqChannel(
                            id=f"{slot.id}-CH{ch_num:02d}",
                            channel_number=ch_num,
                            role="output",
                        ))
                        ch_num += 1
        else:
            for n in range(dlg.num_channels()):
                ch_num = start + n
                module.channels.append(DaqChannel(
                    id=f"{slot.id}-CH{ch_num:02d}",
                    channel_number=ch_num,
                ))
        slot.module = module
        self.refresh()
        self.on_change()

    def _add_channel(self, module_id: str):
        result = self._find_module(module_id)
        if result is None:
            return
        crate, slot, module = result
        dlg = _ChannelDialog(self, [c.id for c in self.project.cables])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        existing_chs = {ch.channel_number for ch in module.channels}
        ch_num = dlg.channel_number()
        if ch_num in existing_chs:
            QMessageBox.warning(self, "Duplicate", f"Channel {ch_num} already exists.")
            return
        ch = DaqChannel(
            id=f"{slot.id}-CH{ch_num:02d}",
            channel_number=ch_num,
            cable_id=dlg.cable_id(),
            signal_label=dlg.signal_label(),
            notes=dlg.notes(),
            role=dlg.role(),
        )
        module.channels.append(ch)
        module.channels.sort(key=lambda c: c.channel_number)
        self.refresh()
        self.on_change()

    def _delete_crate(self, crate_id: str):
        crate = self._find_crate(crate_id)
        if crate is None:
            return
        if QMessageBox.question(
            self, "Delete", f"Delete crate {crate.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self.project.crates.remove(crate)
        self.refresh()
        self.on_change()

    def _delete_slot(self, slot_id: str):
        result = self._find_slot(slot_id)
        if result is None:
            return
        crate, slot = result
        if QMessageBox.question(
            self, "Delete", f"Delete slot {slot.slot_number}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        crate.slots.remove(slot)
        self.refresh()
        self.on_change()

    def _delete_module(self, module_id: str):
        result = self._find_module(module_id)
        if result is None:
            return
        crate, slot, module = result
        if QMessageBox.question(
            self, "Delete", f"Delete module '{module.name}'? This also deletes all its channels.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        slot.module = None
        self.refresh()
        self.on_change()

    def _toggle_channel_role(self, ch_id: str):
        result = self._find_channel(ch_id)
        if result is None:
            return
        _, _, ch = result
        ch.role = "output" if ch.role != "output" else "input"
        self.refresh()
        self.on_change()

    def _delete_channel(self, ch_id: str):
        result = self._find_channel(ch_id)
        if result is None:
            return
        slot, module, ch = result
        module.channels.remove(ch)
        self.refresh()
        self.on_change()

    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        tag, obj_id = data
        text = item.text(col)
        if tag == "crate":
            crate = self._find_crate(obj_id)
            if crate and col == 0:
                crate.name = text
        elif tag == "module":
            result = self._find_module(obj_id)
            if result:
                _, _, module = result
                if col == 0:
                    module.name = text
                elif col == 1:
                    module.module_type = text
        elif tag == "channel":
            result = self._find_channel(obj_id)
            if result:
                _, _, ch = result
                if col == 0:
                    item.setText(0, "IN ▸" if ch.role != "output" else "◂ OUT")
                    return
                elif col == 1:
                    item.setText(1, str(ch.channel_number))
                    return
                elif col == 2:
                    ch.cable_id = text
                elif col == 3:
                    ch.signal_label = text
                elif col == 4:
                    ch.notes = text
        self.on_change()


# ── Dialogs ────────────────────────────────────────────────────────────────────

class _CrateDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Add Crate")
        self._configs = load_configs()
        layout = QFormLayout(self)

        self._template = QComboBox()
        self._template.addItem("(none)")
        for cfg in self._configs:
            self._template.addItem(f"{cfg.name}  [{cfg.crate_type}, {cfg.num_slots} slots]")
        self._template.currentIndexChanged.connect(self._apply_template)
        layout.addRow("Template:", self._template)

        self._name = QLineEdit("New Crate")
        self._type = QComboBox()
        self._type.addItems(CRATE_TYPES)
        self._slots = QSpinBox()
        self._slots.setRange(0, 100)
        self._slots.setValue(0)
        self._slots.setToolTip("Number of empty slots to create (0 = none)")

        layout.addRow("Name:", self._name)
        layout.addRow("Type:", self._type)
        layout.addRow("Slots to create:", self._slots)

        btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        layout.addRow(btn)

    def _apply_template(self, idx: int):
        if idx == 0:
            return
        cfg = self._configs[idx - 1]
        self._name.setText(cfg.name)
        self._type.setCurrentText(cfg.crate_type)
        self._slots.setValue(cfg.num_slots)

    def name(self): return self._name.text().strip()
    def crate_type(self): return self._type.currentText()
    def slots_to_create(self): return self._slots.value()


class _SlotDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Add Slot")
        layout = QFormLayout(self)
        self._slot = QSpinBox()
        self._slot.setRange(0, 31)
        self._module = QComboBox()
        self._module.addItems(MODULE_TYPES)
        layout.addRow("Slot #:", self._slot)
        layout.addRow("Default Module Type:", self._module)
        btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        layout.addRow(btn)

    def slot_number(self): return self._slot.value()
    def module_type(self): return self._module.currentText()


class _ModuleDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Add Module")
        self._color_val = "#546e7a"
        layout = QFormLayout(self)

        # Try to populate from library
        self._selected_def = None
        self._lib_combo = QComboBox()
        self._lib_combo.addItem("(custom)")
        try:
            from app.storage.module_library import load_module_library
            self._lib_defs = load_module_library()
            for defn in self._lib_defs:
                self._lib_combo.addItem(f"{defn.name}  [{defn.module_type}, {defn.num_channels} ch]")
        except Exception:
            self._lib_defs = []
        self._lib_combo.currentIndexChanged.connect(self._apply_library)
        layout.addRow("From library:", self._lib_combo)

        self._name = QLineEdit("New Module")
        self._type = QComboBox()
        self._type.addItems(MODULE_TYPES)

        color_row = QHBoxLayout()
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(28, 22)
        self._color_btn.setStyleSheet(
            f"background-color: {self._color_val}; border: 1px solid #666;"
        )
        self._color_btn.clicked.connect(self._pick_color)
        self._color_label = QLabel(self._color_val)
        color_row.addWidget(self._color_btn)
        color_row.addWidget(self._color_label)
        color_row.addStretch()
        color_widget = QWidget()
        color_widget.setLayout(color_row)

        self._ch_start = QSpinBox()
        self._ch_start.setRange(0, 1)
        self._ch_start.setValue(0)
        self._ch_start.setToolTip("First channel number (0 or 1)")

        self._num_ch = QSpinBox()
        self._num_ch.setRange(0, 128)
        self._num_ch.setValue(0)
        self._num_ch.setToolTip("Auto-create this many channels (0 = none)")

        self._coupled = QCheckBox("Couple input/output channel numbers (same ch# for paired in/out)")

        layout.addRow("Name:", self._name)
        layout.addRow("Module Type:", self._type)
        layout.addRow("Color:", color_widget)
        layout.addRow("Channel start:", self._ch_start)
        layout.addRow("Channels to create:", self._num_ch)
        layout.addRow("", self._coupled)

        btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        layout.addRow(btn)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._color_val), self, "Choose Module Color")
        if color.isValid():
            self._color_val = color.name()
            self._color_label.setText(self._color_val)
            self._color_btn.setStyleSheet(
                f"background-color: {self._color_val}; border: 1px solid #666;"
            )

    def _apply_library(self, idx: int):
        if idx == 0 or not self._lib_defs:
            self._selected_def = None
            return
        defn = self._lib_defs[idx - 1]
        self._selected_def = defn
        self._name.setText(defn.name)
        self._type.setCurrentText(defn.module_type)
        self._color_val = defn.color
        self._color_label.setText(defn.color)
        self._color_btn.setStyleSheet(
            f"background-color: {defn.color}; border: 1px solid #666;"
        )
        self._ch_start.setValue(defn.channel_start)
        self._num_ch.setValue(defn.num_channels)
        self._coupled.setChecked(defn.coupled_io)

    def name(self): return self._name.text().strip()
    def module_type(self): return self._type.currentText()
    def color(self): return self._color_val
    def channel_start(self): return self._ch_start.value()
    def num_channels(self): return self._num_ch.value()
    def coupled_io(self): return self._coupled.isChecked()


class _ChannelDialog(QDialog):
    def __init__(self, parent, cable_ids: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Add Channel")
        layout = QFormLayout(self)
        self._ch = QSpinBox()
        self._ch.setRange(0, 127)
        self._cable = QComboBox()
        self._cable.setEditable(True)
        self._cable.addItems([""] + cable_ids)
        self._label = QLineEdit()
        self._notes = QLineEdit()
        self._role = QComboBox()
        self._role.addItems(["input", "output"])
        layout.addRow("Channel #:", self._ch)
        layout.addRow("Cable ID:", self._cable)
        layout.addRow("Signal Label:", self._label)
        layout.addRow("Notes:", self._notes)
        layout.addRow("Role:", self._role)
        btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        layout.addRow(btn)

    def channel_number(self): return self._ch.value()
    def cable_id(self): return self._cable.currentText().strip()
    def signal_label(self): return self._label.text().strip()
    def notes(self): return self._notes.text().strip()
    def role(self): return self._role.currentText()
