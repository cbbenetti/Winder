from typing import Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QMenu, QDialog, QFormLayout, QLineEdit, QSpinBox,
    QComboBox, QDialogButtonBox, QMessageBox, QLabel, QHeaderView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from app.models.daq import DaqCrate, DaqSlot, DaqChannel, CRATE_TYPES, MODULE_TYPES
from app.models.project import Project
from app.storage.crate_config import load_configs


LEVEL_CRATE = 0
LEVEL_SLOT = 1
LEVEL_CHANNEL = 2

CH_COLS = ["Ch#", "Cable ID", "Signal Label", "Notes"]


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
        self.tree.clear()
        for crate in self.project.crates:
            crate_item = self._make_crate_item(crate)
            self.tree.addTopLevelItem(crate_item)
            crate_item.setExpanded(True)
            for slot in crate.slots:
                slot_item = self._make_slot_item(slot)
                crate_item.addChild(slot_item)
                slot_item.setExpanded(True)
                for ch in slot.channels:
                    ch_item = self._make_channel_item(ch)
                    slot_item.addChild(ch_item)
        self.tree.blockSignals(False)

    def _make_crate_item(self, crate: DaqCrate) -> QTreeWidgetItem:
        item = QTreeWidgetItem([crate.name or crate.id, crate.crate_type, "", "", ""])
        item.setData(0, Qt.ItemDataRole.UserRole, ("crate", crate.id))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        return item

    def _make_slot_item(self, slot: DaqSlot) -> QTreeWidgetItem:
        label = f"Slot {slot.slot_number}" + (f" — {slot.model}" if slot.model else "")
        item = QTreeWidgetItem([label, slot.module_type, "", "", ""])
        item.setData(0, Qt.ItemDataRole.UserRole, ("slot", slot.id))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        return item

    def _make_channel_item(self, ch: DaqChannel) -> QTreeWidgetItem:
        item = QTreeWidgetItem(["", str(ch.channel_number), ch.cable_id, ch.signal_label, ch.notes])
        item.setData(0, Qt.ItemDataRole.UserRole, ("channel", ch.id))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
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
                menu.addAction("Add Channel", lambda: self._add_channel(obj_id))
                menu.addAction("Delete Slot", lambda: self._delete_slot(obj_id))
            elif tag == "channel":
                menu.addAction("Delete Channel", lambda: self._delete_channel(obj_id))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _find_crate(self, crate_id: str) -> DaqCrate | None:
        return next((c for c in self.project.crates if c.id == crate_id), None)

    def _find_slot(self, slot_id: str) -> tuple[DaqCrate, DaqSlot] | None:
        for crate in self.project.crates:
            for slot in crate.slots:
                if slot.id == slot_id:
                    return crate, slot
        return None

    def _find_channel(self, ch_id: str) -> tuple[DaqSlot, DaqChannel] | None:
        for crate in self.project.crates:
            for slot in crate.slots:
                for ch in slot.channels:
                    if ch.id == ch_id:
                        return slot, ch
        return None

    def _manage_templates(self):
        from app.views.crate_config_editor import CrateConfigEditor
        CrateConfigEditor(self).exec()

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
            model=dlg.model(),
        )
        crate.slots.append(slot)
        crate.slots.sort(key=lambda s: s.slot_number)
        self.refresh()
        self.on_change()

    def _add_channel(self, slot_id: str):
        result = self._find_slot(slot_id)
        if result is None:
            return
        crate, slot = result
        dlg = _ChannelDialog(self, [c.id for c in self.project.cables])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        existing_chs = {ch.channel_number for ch in slot.channels}
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
        )
        slot.channels.append(ch)
        slot.channels.sort(key=lambda c: c.channel_number)
        self.refresh()
        self.on_change()

    def _delete_crate(self, crate_id: str):
        crate = self._find_crate(crate_id)
        if crate is None:
            return
        if QMessageBox.question(self, "Delete", f"Delete crate {crate.name}?",
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
        if QMessageBox.question(self, "Delete", f"Delete slot {slot.slot_number}?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) != QMessageBox.StandardButton.Yes:
            return
        crate.slots.remove(slot)
        self.refresh()
        self.on_change()

    def _delete_channel(self, ch_id: str):
        result = self._find_channel(ch_id)
        if result is None:
            return
        slot, ch = result
        slot.channels.remove(ch)
        self.refresh()
        self.on_change()

    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        tag, obj_id = item.data(0, Qt.ItemDataRole.UserRole)
        text = item.text(col)
        if tag == "crate":
            crate = self._find_crate(obj_id)
            if crate and col == 0:
                crate.name = text
        elif tag == "slot":
            result = self._find_slot(obj_id)
            if result:
                _, slot = result
                if col == 1:
                    slot.module_type = text
        elif tag == "channel":
            result = self._find_channel(obj_id)
            if result:
                _, ch = result
                if col == 2:
                    ch.cable_id = text
                elif col == 3:
                    ch.signal_label = text
                elif col == 4:
                    ch.notes = text
        self.on_change()


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
        self._slots.setToolTip("Number of empty slots to create automatically (0 = none)")

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
        self._model = QLineEdit()
        self._model.setPlaceholderText("e.g. CAEN V785")
        layout.addRow("Slot #:", self._slot)
        layout.addRow("Module Type:", self._module)
        layout.addRow("Model:", self._model)
        btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        layout.addRow(btn)

    def slot_number(self): return self._slot.value()
    def module_type(self): return self._module.currentText()
    def model(self): return self._model.text().strip()


class _ChannelDialog(QDialog):
    def __init__(self, parent, cable_ids: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Add Channel")
        layout = QFormLayout(self)
        self._ch = QSpinBox()
        self._ch.setRange(0, 63)
        self._cable = QComboBox()
        self._cable.setEditable(True)
        self._cable.addItems([""] + cable_ids)
        self._label = QLineEdit()
        self._notes = QLineEdit()
        layout.addRow("Channel #:", self._ch)
        layout.addRow("Cable ID:", self._cable)
        layout.addRow("Signal Label:", self._label)
        layout.addRow("Notes:", self._notes)
        btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        layout.addRow(btn)

    def channel_number(self): return self._ch.value()
    def cable_id(self): return self._cable.currentText().strip()
    def signal_label(self): return self._label.text().strip()
    def notes(self): return self._notes.text().strip()
