from typing import Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsLineItem,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox,
    QDialogButtonBox, QMenu, QApplication
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QPen, QBrush, QFont, QPainterPath, QPainter, QKeyEvent
)

from app.models.project import Project
from app.models.cable import Cable, CABLE_TYPES, SIGNAL_TYPES
from app.models.patch_panel import PatchPanel, PatchPort
from app.models.daq import DaqCrate, DaqSlot, DaqChannel

# ── Layout constants ──────────────────────────────────────────────────────────
PANEL_X  = 40
PANEL_W  = 280
RACK_X   = 680
CRATE_W  = 320
ITEM_GAP = 20
HEADER_H = 32
SLOT_H   = 30
CHAN_H   = 17
PORT_H   = 22
STUB_LEN = 60
CONN_R   = 5

# ── Colors ────────────────────────────────────────────────────────────────────
SIGNAL_COLORS = {
    "Analog":  "#4fc3f7",
    "Digital": "#81c784",
    "HV":      "#e57373",
    "Timing":  "#ffb74d",
    "Trigger": "#ba68c8",
    "Power":   "#fff176",
    "Other":   "#b0bec5",
}

C_PANEL_HDR = QColor("#2e7d32")
C_CRATE_HDR = QColor("#37474f")
C_SLOT_HDR  = QColor("#546e7a")
C_CHAN_A    = QColor("#eceff1")
C_CHAN_B    = QColor("#f5f5f5")
C_RACK_EDGE = QColor("#263238")
C_BORDER    = QColor("#455a64")
C_WHITE     = QColor("#ffffff")
C_CONN_IDLE = QColor("#ffffff")
C_CONN_HOV  = QColor("#ffeb3b")
C_CONN_SEL  = QColor("#ff6b35")
C_DRAG_LINE = QColor("#ff6b35")


def _font(size: int = 8, bold: bool = False) -> QFont:
    f = QFont("Segoe UI, Arial, sans-serif", size)
    f.setBold(bold)
    return f


def _elide(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"


# ── Interactive connector dot ─────────────────────────────────────────────────

class ConnectorItem(QGraphicsEllipseItem):
    """Clickable connector dot attached to a port or DAQ channel."""

    def __init__(self, endpoint_id: str, signal_type: str):
        r = CONN_R
        super().__init__(-r, -r, r * 2, r * 2)
        self.endpoint_id = endpoint_id
        self.signal_type = signal_type
        self.setBrush(QBrush(C_CONN_IDLE))
        self.setPen(QPen(C_BORDER, 1))
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(C_CONN_HOV))
        self.setCursor(Qt.CursorShape.CrossCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(C_CONN_IDLE))
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def set_selected(self, on: bool):
        self.setBrush(QBrush(C_CONN_SEL if on else C_CONN_IDLE))
        self.setPen(QPen(C_CONN_SEL if on else C_BORDER, 1.5 if on else 1))


# ── Interactive cable bezier ──────────────────────────────────────────────────

class CablePath(QGraphicsPathItem):
    """Bezier cable that highlights on hover and offers a delete context menu."""

    def __init__(self, cable: Cable, path: QPainterPath,
                 color: QColor, overview: "SystemOverview"):
        super().__init__(path)
        self._cable = cable
        self._overview = overview
        thin = QPen(color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        thick = QPen(color, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        self._pen_normal = thin
        self._pen_hover  = thick
        self.setPen(thin)
        self.setAcceptHoverEvents(True)
        self.setZValue(5)
        self.setToolTip(
            f"{cable.id}: {cable.from_endpoint}  →  {cable.to_endpoint}\n"
            f"Type: {cable.cable_type}   Signal: {cable.signal_type}"
        )

    def hoverEnterEvent(self, event):
        self.setPen(self._pen_hover)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(self._pen_normal)
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        info = menu.addAction(f"Cable: {self._cable.id}")
        info.setEnabled(False)
        menu.addSeparator()
        del_act = menu.addAction("Delete Cable")
        if menu.exec(event.screenPos().toPoint()) == del_act:
            self._overview._delete_cable(self._cable)


# ── Custom view for connect-mode event capture ────────────────────────────────

class _SceneView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, overview: "SystemOverview"):
        super().__init__(scene)
        self._ov = overview

    def mousePressEvent(self, event):
        if self._ov._connect_mode and event.button() == Qt.MouseButton.LeftButton:
            sp = self.mapToScene(event.pos())
            item = self._item_at(sp)
            self._ov._on_connector_click(
                item if isinstance(item, ConnectorItem) else None, sp
            )
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._ov._connect_mode:
            self._ov._on_drag_move(self.mapToScene(event.pos()))
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape and self._ov._connect_mode:
            self._ov._cancel_drag()
        else:
            super().keyPressEvent(event)

    def _item_at(self, scene_pos: QPointF):
        item = self.scene().itemAt(scene_pos, self.transform())
        # Walk up: ConnectorItem may be the top-level item itself
        while item is not None and not isinstance(item, ConnectorItem):
            item = item.parentItem()
        return item


# ── New cable dialog ──────────────────────────────────────────────────────────

class _NewCableDialog(QDialog):
    def __init__(self, parent, from_ep: str, to_ep: str,
                 signal_type: str, project: Project):
        super().__init__(parent)
        self.setWindowTitle("Create Cable")
        self._project = project
        layout = QFormLayout(self)

        self._id = QLineEdit(project.next_cable_id())
        self._label = QLineEdit()
        self._from = QLineEdit(from_ep)
        self._from.setReadOnly(True)
        self._to = QLineEdit(to_ep)
        self._to.setReadOnly(True)
        self._type = QComboBox()
        self._type.addItems(CABLE_TYPES)
        self._sig = QComboBox()
        self._sig.addItems(SIGNAL_TYPES)
        idx = self._sig.findText(signal_type)
        if idx >= 0:
            self._sig.setCurrentIndex(idx)
        self._len = QDoubleSpinBox()
        self._len.setRange(0, 9999)
        self._len.setSuffix(" m")
        self._notes = QLineEdit()

        layout.addRow("Cable ID:", self._id)
        layout.addRow("Label:", self._label)
        layout.addRow("From:", self._from)
        layout.addRow("To:", self._to)
        layout.addRow("Cable Type:", self._type)
        layout.addRow("Signal Type:", self._sig)
        layout.addRow("Length:", self._len)
        layout.addRow("Notes:", self._notes)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def cable(self) -> Cable:
        return Cable(
            id=self._id.text().strip(),
            label=self._label.text().strip(),
            cable_type=self._type.currentText(),
            signal_type=self._sig.currentText(),
            from_endpoint=self._from.text().strip(),
            to_endpoint=self._to.text().strip(),
            length_m=self._len.value(),
            notes=self._notes.text().strip(),
        )


# ── Main widget ───────────────────────────────────────────────────────────────

class SystemOverview(QWidget):
    """Home tab: full-system visual overview with interactive cable drawing."""

    def __init__(self, project: Project, on_change: Callable = None):
        super().__init__()
        self.project = project
        self.on_change = on_change or (lambda: None)
        self._conn: dict[str, ConnectorItem] = {}  # endpoint_id → ConnectorItem
        self._connect_mode = False
        self._drag_src: ConnectorItem | None = None
        self._drag_line: QGraphicsLineItem | None = None
        self._build_ui()

    def set_project(self, project: Project):
        self.project = project
        self.refresh()

    def refresh(self):
        self._cancel_drag()
        self._scene.clear()
        self._conn.clear()
        self._draw_panels()
        self._draw_racks()
        self._draw_cables()
        self._draw_stubs()

    # ── UI shell ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh)
        btn_fit = QPushButton("Fit View")
        btn_fit.clicked.connect(self._fit_view)
        toolbar.addWidget(btn_refresh)
        toolbar.addWidget(btn_fit)

        self._btn_connect = QPushButton("Connect Mode")
        self._btn_connect.setCheckable(True)
        self._btn_connect.setToolTip(
            "Click to enter connect mode.\n"
            "Click a connector (white dot), then click another to create a cable.\n"
            "Right-click an existing cable to delete it.\n"
            "Press Escape to cancel."
        )
        self._btn_connect.toggled.connect(self._toggle_connect_mode)
        self._btn_connect.setStyleSheet(
            "QPushButton:checked { background: #ff6b35; color: white; font-weight: bold; }"
        )
        toolbar.addWidget(self._btn_connect)

        toolbar.addStretch()
        for sig, color in SIGNAL_COLORS.items():
            lbl = QLabel(f"  {sig}  ")
            lbl.setStyleSheet(
                f"background:{color}; border:1px solid #555; padding:1px 4px; font-size:10px;"
            )
            toolbar.addWidget(lbl)
        layout.addLayout(toolbar)

        self._scene = QGraphicsScene()
        self._view = _SceneView(self._scene, self)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.wheelEvent = self._wheel_zoom
        layout.addWidget(self._view)

        self.refresh()

    def _fit_view(self):
        r = self._scene.itemsBoundingRect()
        if not r.isNull():
            self._view.fitInView(r.adjusted(-20, -20, 20, 20),
                                 Qt.AspectRatioMode.KeepAspectRatio)

    def _wheel_zoom(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._view.scale(factor, factor)

    def _toggle_connect_mode(self, on: bool):
        self._connect_mode = on
        if on:
            self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._cancel_drag()
            self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self._view.unsetCursor()

    # ── Connect-mode event handlers ───────────────────────────────────────────

    def _on_connector_click(self, connector: ConnectorItem | None, scene_pos: QPointF):
        if connector is None:
            self._cancel_drag()
            return

        if self._drag_src is None:
            # start drag
            self._drag_src = connector
            connector.set_selected(True)
            self._drag_line = self._scene.addLine(
                connector.scenePos().x(), connector.scenePos().y(),
                connector.scenePos().x(), connector.scenePos().y(),
                QPen(C_DRAG_LINE, 1.5, Qt.PenStyle.DashLine)
            )
            self._drag_line.setZValue(20)
        else:
            if connector is not self._drag_src:
                self._complete_connection(self._drag_src, connector)
            self._cancel_drag()

    def _on_drag_move(self, scene_pos: QPointF):
        if self._drag_src and self._drag_line:
            sp = self._drag_src.scenePos()
            self._drag_line.setLine(sp.x(), sp.y(), scene_pos.x(), scene_pos.y())

    def _cancel_drag(self):
        if self._drag_src:
            self._drag_src.set_selected(False)
            self._drag_src = None
        if self._drag_line:
            self._scene.removeItem(self._drag_line)
            self._drag_line = None

    def _complete_connection(self, src: ConnectorItem, dst: ConnectorItem):
        dlg = _NewCableDialog(
            self,
            from_ep=src.endpoint_id,
            to_ep=dst.endpoint_id,
            signal_type=src.signal_type or dst.signal_type,
            project=self.project,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cable = dlg.cable()
        if not cable.id:
            return
        self.project.cables.append(cable)
        self.on_change()
        self.refresh()

    def _delete_cable(self, cable: Cable):
        if cable in self.project.cables:
            self.project.cables.remove(cable)
            self.on_change()
            self.refresh()

    # ── Patch panels ──────────────────────────────────────────────────────────

    def _draw_panels(self):
        y = 20.0
        for panel in self.project.patch_panels:
            y = self._draw_one_panel(panel, PANEL_X, y)
            y += ITEM_GAP

    def _draw_one_panel(self, panel: PatchPanel, x: float, y: float) -> float:
        cols = max(panel.cols, 1)
        port_w = PANEL_W / cols

        self._filled_rect(x, y, PANEL_W, HEADER_H, C_PANEL_HDR, C_RACK_EDGE)
        self._label(f"{panel.id}  —  {panel.name}", x + 6, y + 6,
                    PANEL_W - 12, 18, color=C_WHITE, bold=True)

        for row in range(panel.rows):
            for col in range(cols):
                port = panel.port_at(row, col)
                px = x + col * port_w
                py = y + HEADER_H + row * PORT_H
                sig = port.signal_type if port else "Other"
                fill = QColor(SIGNAL_COLORS.get(sig, SIGNAL_COLORS["Other"]))
                self._filled_rect(px, py, port_w, PORT_H, fill, C_BORDER)
                lbl = port.label if (port and port.label) else (port.id if port else "")
                self._label(_elide(lbl, 6), px + 2, py + 3, port_w - 4, PORT_H - 6, size=6)

                if port and port.id:
                    cp = QPointF(x + PANEL_W, py + PORT_H / 2)
                    conn = ConnectorItem(port.id, sig)
                    conn.setPos(cp)
                    self._scene.addItem(conn)
                    self._conn[port.id] = conn

        bottom = y + HEADER_H + panel.rows * PORT_H
        self._scene.addRect(QRectF(x, y, PANEL_W, bottom - y), QPen(C_RACK_EDGE, 2))
        return bottom

    # ── DAQ racks / crates ────────────────────────────────────────────────────

    def _draw_racks(self):
        y = 20.0
        for crate in self.project.crates:
            y = self._draw_one_crate(crate, RACK_X, y)
            y += ITEM_GAP

    def _draw_one_crate(self, crate: DaqCrate, x: float, y: float) -> float:
        inner_h = sum(self._slot_height(s) for s in crate.slots)
        total_h = HEADER_H + inner_h

        ear_w = 14
        rail = QColor("#78909c")
        self._filled_rect(x - ear_w, y, ear_w, total_h, rail, C_RACK_EDGE)
        self._filled_rect(x + CRATE_W, y, ear_w, total_h, rail, C_RACK_EDGE)
        for dy in (8, total_h / 2, total_h - 10):
            for ex in (x - ear_w + 4, x + CRATE_W + 4):
                self._scene.addEllipse(
                    QRectF(ex, y + dy - 3, 6, 6),
                    QPen(C_RACK_EDGE, 1), QBrush(QColor("#546e7a"))
                )

        self._filled_rect(x, y, CRATE_W, HEADER_H, C_CRATE_HDR, C_RACK_EDGE)
        self._label(f"{crate.name or crate.id}  [{crate.crate_type}]",
                    x + 8, y + 7, CRATE_W - 16, 18, color=C_WHITE, bold=True)

        sy = y + HEADER_H
        for slot in crate.slots:
            sy = self._draw_one_slot(slot, x, sy)

        self._scene.addRect(QRectF(x, y, CRATE_W, total_h), QPen(C_RACK_EDGE, 2))
        return y + total_h

    def _slot_height(self, slot: DaqSlot) -> int:
        return SLOT_H + len(slot.channels) * CHAN_H

    def _draw_one_slot(self, slot: DaqSlot, x: float, y: float) -> float:
        self._filled_rect(x, y, CRATE_W, SLOT_H, C_SLOT_HDR, C_BORDER)
        label = f"Sl {slot.slot_number:02d}  {slot.module_type}"
        if slot.model:
            label += f"  {_elide(slot.model, 18)}"
        self._label(label, x + 8, y + 7, CRATE_W - 60, 16, color=C_WHITE)
        self._label(f"{len(slot.channels)} ch", x + CRATE_W - 52, y + 7, 48, 16,
                    color=QColor("#cfd8dc"), size=7)

        cy = y + SLOT_H
        for i, ch in enumerate(slot.channels):
            fill = C_CHAN_A if i % 2 == 0 else C_CHAN_B
            self._filled_rect(x, cy, CRATE_W, CHAN_H, fill, QColor("#bdbdbd"))
            self._label(f"{ch.channel_number:02d}", x + 6, cy + 2, 18, CHAN_H - 4,
                        size=7, bold=True)
            self._label(_elide(ch.signal_label, 14), x + 28, cy + 2, 90, CHAN_H - 4, size=7)
            self._label(_elide(ch.cable_id, 12), x + 126, cy + 2, 80, CHAN_H - 4,
                        size=7, color=QColor("#546e7a"))

            if ch.id:
                cp = QPointF(x, cy + CHAN_H / 2)
                # Infer signal type from linked cable if possible
                linked = self.project.cable_by_id(ch.cable_id) if ch.cable_id else None
                sig = linked.signal_type if linked else "Other"
                conn = ConnectorItem(ch.id, sig)
                conn.setPos(cp)
                self._scene.addItem(conn)
                self._conn[ch.id] = conn

            cy += CHAN_H
        return cy

    # ── Cables ────────────────────────────────────────────────────────────────

    def _draw_cables(self):
        for cable in self.project.cables:
            src_item = self._conn.get(cable.from_endpoint)
            dst_item = self._conn.get(cable.to_endpoint)
            if src_item is None or dst_item is None:
                continue
            color = QColor(SIGNAL_COLORS.get(cable.signal_type, SIGNAL_COLORS["Other"]))
            src = src_item.scenePos()
            dst = dst_item.scenePos()
            path = QPainterPath(src)
            mid_x = (src.x() + dst.x()) / 2
            path.cubicTo(QPointF(mid_x, src.y()), QPointF(mid_x, dst.y()), dst)
            cp = CablePath(cable, path, color, self)
            self._scene.addItem(cp)

    def _draw_stubs(self):
        for cable in self.project.cables:
            src_item = self._conn.get(cable.from_endpoint)
            dst_item = self._conn.get(cable.to_endpoint)

            if src_item is not None and dst_item is None:
                anchor = src_item.scenePos()
                stub_label = cable.to_endpoint
                end = QPointF(anchor.x() + STUB_LEN, anchor.y())
                label_left = False
            elif dst_item is not None and src_item is None:
                anchor = dst_item.scenePos()
                stub_label = cable.from_endpoint
                end = QPointF(anchor.x() - STUB_LEN, anchor.y())
                label_left = True
            else:
                continue

            color = QColor(SIGNAL_COLORS.get(cable.signal_type, SIGNAL_COLORS["Other"]))
            self._scene.addLine(
                anchor.x(), anchor.y(), end.x(), end.y(),
                QPen(color, 1.5, Qt.PenStyle.DashLine)
            )
            self._scene.addEllipse(
                QRectF(end.x() - 4, end.y() - 4, 8, 8),
                QPen(color, 1), QBrush(color)
            )
            t = self._scene.addText(_elide(stub_label, 18))
            t.setFont(_font(6))
            t.setDefaultTextColor(QColor("#555"))
            if label_left:
                t.setPos(end.x() - t.boundingRect().width() - 2, end.y() - 9)
            else:
                t.setPos(end.x() + 2, end.y() - 9)

    # ── Scene helpers ─────────────────────────────────────────────────────────

    def _filled_rect(self, x, y, w, h, fill: QColor, border: QColor):
        self._scene.addRect(QRectF(x, y, w, h), QPen(border, 1), QBrush(fill))

    def _label(self, text: str, x, y, w, h, size: int = 8,
               bold: bool = False, color: QColor = None):
        item = self._scene.addText(text)
        item.setFont(_font(size, bold))
        item.setDefaultTextColor(color or QColor("#212121"))
        item.setPos(x, y)
        item.setTextWidth(w)
