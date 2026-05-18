from typing import Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPushButton,
    QComboBox, QLabel, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QGroupBox, QFormLayout, QLineEdit, QSpinBox,
    QMessageBox, QInputDialog, QDialog, QDialogButtonBox, QComboBox as QCB
)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPen, QBrush, QFont

from app.models.patch_panel import PatchPanel, PatchPort
from app.models.cable import SIGNAL_TYPES
from app.models.project import Project


PORT_W = 60
PORT_H = 36
GAP = 4

SIGNAL_COLORS = {
    "Analog":  "#4fc3f7",
    "Digital": "#81c784",
    "HV":      "#e57373",
    "Timing":  "#ffb74d",
    "Trigger": "#ba68c8",
    "Power":   "#fff176",
    "Other":   "#b0bec5",
}


class PortItem(QGraphicsRectItem):
    def __init__(self, port: PatchPort, on_click):
        super().__init__(0, 0, PORT_W, PORT_H)
        self.port = port
        self.on_click = on_click
        color = SIGNAL_COLORS.get(port.signal_type, "#b0bec5")
        self.setBrush(QBrush(QColor(color)))
        self.setPen(QPen(QColor("#333"), 1))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        font = QFont("Monospace", 7)
        text = QGraphicsTextItem(port.label or port.id, self)
        text.setFont(font)
        text.setPos(2, 2)
        text.setTextWidth(PORT_W - 4)

    def mousePressEvent(self, event):
        self.on_click(self.port)


class PatchPanelView(QWidget):
    def __init__(self, project: Project, on_change: Callable):
        super().__init__()
        self.project = project
        self.on_change = on_change
        self._selected_port: PatchPort | None = None
        self._build_ui()
        self.refresh()

    def set_project(self, project: Project):
        self.project = project
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Panel selector toolbar
        top = QHBoxLayout()
        top.addWidget(QLabel("Panel:"))
        self.panel_selector = QComboBox()
        self.panel_selector.currentIndexChanged.connect(self._on_panel_selected)
        top.addWidget(self.panel_selector)
        btn_add = QPushButton("+ Add Panel")
        btn_add.clicked.connect(self._add_panel)
        btn_del = QPushButton("Remove Panel")
        btn_del.clicked.connect(self._remove_panel)
        top.addWidget(btn_add)
        top.addWidget(btn_del)
        top.addStretch()
        layout.addLayout(top)

        # Splitter: scene + detail panel
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setMinimumWidth(400)
        splitter.addWidget(self.view)

        self.detail_box = self._build_detail_panel()
        splitter.addWidget(self.detail_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        # Legend
        legend = QHBoxLayout()
        for sig, color in SIGNAL_COLORS.items():
            lbl = QLabel(f"  {sig}  ")
            lbl.setStyleSheet(f"background:{color}; border:1px solid #333; padding:2px;")
            legend.addWidget(lbl)
        legend.addStretch()
        layout.addLayout(legend)

    def _build_detail_panel(self) -> QGroupBox:
        box = QGroupBox("Port Details")
        form = QFormLayout(box)

        self.det_id = QLineEdit()
        self.det_id.setReadOnly(True)
        self.det_label = QLineEdit()
        self.det_label.editingFinished.connect(self._save_port_detail)
        self.det_signal = QComboBox()
        self.det_signal.addItems(SIGNAL_TYPES)
        self.det_signal.currentTextChanged.connect(self._save_port_detail)
        self.det_front = QLineEdit()
        self.det_front.setPlaceholderText("Cable ID")
        self.det_front.editingFinished.connect(self._save_port_detail)
        self.det_rear = QLineEdit()
        self.det_rear.setPlaceholderText("Cable ID")
        self.det_rear.editingFinished.connect(self._save_port_detail)
        self.det_notes = QLineEdit()
        self.det_notes.editingFinished.connect(self._save_port_detail)

        form.addRow("Port ID:", self.det_id)
        form.addRow("Label:", self.det_label)
        form.addRow("Signal Type:", self.det_signal)
        form.addRow("Front Cable:", self.det_front)
        form.addRow("Rear Cable:", self.det_rear)
        form.addRow("Notes:", self.det_notes)
        return box

    def _current_panel(self) -> PatchPanel | None:
        idx = self.panel_selector.currentIndex()
        if idx < 0 or idx >= len(self.project.patch_panels):
            return None
        return self.project.patch_panels[idx]

    def refresh(self):
        current_text = self.panel_selector.currentText()
        self.panel_selector.blockSignals(True)
        try:
            self.panel_selector.clear()
            for p in self.project.patch_panels:
                self.panel_selector.addItem(f"{p.id} — {p.name}")
            idx = self.panel_selector.findText(current_text)
            self.panel_selector.setCurrentIndex(max(0, idx))
        finally:
            self.panel_selector.blockSignals(False)
        self._draw_panel()

    def _on_panel_selected(self, _):
        self._draw_panel()

    def _draw_panel(self):
        self.scene.clear()
        panel = self._current_panel()
        if panel is None:
            return
        for row in range(panel.rows):
            for col in range(panel.cols):
                x = col * (PORT_W + GAP)
                y = row * (PORT_H + GAP)
                port = panel.port_at(row, col)
                if port is None:
                    port = PatchPort(
                        id=f"{panel.id}-{chr(65+row)}{col+1:02d}",
                        row=row, col=col
                    )
                    panel.ports.append(port)
                item = PortItem(port, self._on_port_click)
                item.setPos(x, y)
                self.scene.addItem(item)

            # Row label
            lbl = self.scene.addText(chr(65 + row))
            lbl.setPos(-20, row * (PORT_H + GAP) + PORT_H // 4)

        for col in range(panel.cols):
            lbl = self.scene.addText(str(col + 1))
            lbl.setPos(col * (PORT_W + GAP) + PORT_W // 3, -20)

    def _on_port_click(self, port: PatchPort):
        self._selected_port = port
        self.det_id.setText(port.id)
        self.det_label.setText(port.label)
        idx = self.det_signal.findText(port.signal_type)
        self.det_signal.setCurrentIndex(max(0, idx))
        self.det_front.setText(port.front_cable_id)
        self.det_rear.setText(port.rear_cable_id)
        self.det_notes.setText(port.notes)

    def _save_port_detail(self):
        if self._selected_port is None:
            return
        port = self._selected_port
        port.label = self.det_label.text()
        port.signal_type = self.det_signal.currentText()
        port.front_cable_id = self.det_front.text().strip()
        port.rear_cable_id = self.det_rear.text().strip()
        port.notes = self.det_notes.text()
        self._draw_panel()
        self.on_change()

    def _add_panel(self):
        dlg = _PanelDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        panel = PatchPanel(
            id=self.project.next_panel_id(),
            name=dlg.name(),
            rows=dlg.rows(),
            cols=dlg.cols(),
        )
        self.project.patch_panels.append(panel)
        self.refresh()
        self.panel_selector.setCurrentIndex(len(self.project.patch_panels) - 1)
        self.on_change()

    def _remove_panel(self):
        panel = self._current_panel()
        if panel is None:
            return
        reply = QMessageBox.question(
            self, "Remove Panel", f"Remove panel {panel.id} — {panel.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.project.patch_panels.remove(panel)
        self.refresh()
        self.on_change()


class _PanelDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Add Patch Panel")
        layout = QFormLayout(self)
        self._name = QLineEdit("New Panel")
        self._rows = QSpinBox()
        self._rows.setRange(1, 24)
        self._rows.setValue(4)
        self._cols = QSpinBox()
        self._cols.setRange(1, 48)
        self._cols.setValue(12)
        layout.addRow("Name:", self._name)
        layout.addRow("Rows:", self._rows)
        layout.addRow("Columns:", self._cols)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def name(self): return self._name.text().strip()
    def rows(self): return self._rows.value()
    def cols(self): return self._cols.value()
