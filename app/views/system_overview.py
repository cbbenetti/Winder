import math
from typing import Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsLineItem,
    QGraphicsPolygonItem,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox,
    QDialogButtonBox, QMenu, QFileDialog,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QSizeF
from PyQt6.QtGui import (
    QColor, QPen, QBrush, QFont, QPainterPath, QPainter, QKeyEvent, QPolygonF,
    QImage,
)

from app.models.project import Project
from app.models.cable import Cable, SIGNAL_TYPES
from app.models.patch_panel import PatchPanel, PatchPort
from app.models.daq import DaqCrate, DaqSlot, DaqModule, DaqChannel

# ── Layout constants ──────────────────────────────────────────────────────────
PANEL_X  = 40
PANEL_W  = 280
RACK_X   = 680
CRATE_W  = 320
ITEM_GAP = 20
HEADER_H = 32
SLOT_H   = 24
MODULE_H = 22
CHAN_H   = 17
SECTION_H = 14   # height of INPUTS/OUTPUTS sub-header rows
PORT_H     = 22
PORT_ROW_H = 16
STUB_LEN   = 60
CONN_R   = 8
EAR_W    = 14

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
C_PANEL_HDR  = QColor("#2e7d32")
C_CRATE_HDR  = QColor("#37474f")
C_SLOT_HDR   = QColor("#546e7a")
C_CHAN_A     = QColor("#eceff1")
C_CHAN_B     = QColor("#f5f5f5")
C_RACK_EDGE  = QColor("#263238")
C_BORDER     = QColor("#455a64")
C_WHITE      = QColor("#ffffff")
C_CONN_IDLE  = QColor("#ffffff")
C_CONN_IN    = QColor("#b3e5fc")   # light blue for input connectors
C_CONN_OUT   = QColor("#fce4ec")   # light pink for output connectors
C_CONN_HOV   = QColor("#ffeb3b")
C_CONN_SEL   = QColor("#ff6b35")
C_DRAG_LINE  = QColor("#ff6b35")
C_IN_HDR     = QColor("#e3f2fd")
C_OUT_HDR    = QColor("#fce4ec")
C_IN_TEXT    = QColor("#1565c0")
C_OUT_TEXT   = QColor("#c62828")


def _font(size: int = 8, bold: bool = False) -> QFont:
    f = QFont("Segoe UI, Arial, sans-serif", size)
    f.setBold(bold)
    return f


def _elide(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"


def _coupled_groups(channels) -> "tuple[list, list]":
    """Group channels by connector name. Returns (input_groups, output_groups),
    each a list of (connector_name, [DaqChannel]) in insertion order."""
    in_groups: dict = {}
    out_groups: dict = {}
    for ch in channels:
        if ch.role == "output":
            key = ch.connector or "Output"
            out_groups.setdefault(key, []).append(ch)
        else:
            key = ch.connector or "Input"
            in_groups.setdefault(key, []).append(ch)
    return list(in_groups.items()), list(out_groups.items())


# ── Resize handle ─────────────────────────────────────────────────────────────

class _ResizeHandle(QGraphicsRectItem):
    _SZ = 10

    def __init__(self, block: "QGraphicsRectItem", horizontal_only: bool = False):
        s = self._SZ
        super().__init__(-s / 2, -s / 2, s, s)
        self._block = block
        self._horiz = horizontal_only
        self.setBrush(QBrush(QColor("#90a4ae")))
        self.setPen(QPen(C_RACK_EDGE, 1))
        self.setCursor(
            Qt.CursorShape.SizeHorCursor if horizontal_only
            else Qt.CursorShape.SizeFDiagCursor
        )
        self.setZValue(15)
        self._active = False
        self._origin = QPointF()
        self._start_w = self._start_h = 0.0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._active = True
            self._origin = event.scenePos()
            self._start_w = self._block._display_w
            self._start_h = getattr(self._block, "_display_h", 0.0)
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._active:
            return
        d = event.scenePos() - self._origin
        if self._horiz:
            self._block.set_width(max(100.0, self._start_w + d.x()))
        else:
            self._block.set_size(
                max(100.0, self._start_w + d.x()),
                max(float(HEADER_H + 24), self._start_h + d.y()),
            )
        event.accept()

    def mouseReleaseEvent(self, event):
        self._active = False
        event.accept()


# ── Connector dot ─────────────────────────────────────────────────────────────

class ConnectorItem(QGraphicsEllipseItem):
    def __init__(self, endpoint_id: str, signal_type: str, role: str = ""):
        r = CONN_R
        super().__init__(-r, -r, r * 2, r * 2)
        self.endpoint_id = endpoint_id
        self.signal_type = signal_type
        if role == "input":
            self._idle_brush = QBrush(C_CONN_IN)
        elif role == "output":
            self._idle_brush = QBrush(C_CONN_OUT)
        else:
            self._idle_brush = QBrush(C_CONN_IDLE)
        self.setBrush(self._idle_brush)
        self.setPen(QPen(C_BORDER, 2))
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(C_CONN_HOV))
        self.setCursor(Qt.CursorShape.CrossCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(self._idle_brush)
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def set_selected(self, on: bool):
        self.setBrush(QBrush(C_CONN_SEL if on else self._idle_brush))
        self.setPen(QPen(C_CONN_SEL if on else C_BORDER, 2))


# ── Patch panel block ─────────────────────────────────────────────────────────

class PanelBlock(QGraphicsRectItem):
    def __init__(self, panel: PatchPanel, overview: "SystemOverview",
                 x: float, y: float, display_w: float, display_h: float):
        super().__init__(0, 0, display_w, display_h)
        self._panel = panel
        self._overview = overview
        self._display_w = display_w
        self._display_h = display_h
        self.setPos(x, y)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.GlobalColor.transparent))
        self._handle = _ResizeHandle(self)
        self._handle.setParentItem(self)
        self._rebuild_connectors()

    def set_size(self, w: float, h: float):
        self._display_w = w
        self._rebuild_connectors()
        self._overview._update_cables()
        self.update()

    def _rebuild_connectors(self):
        for child in list(self.childItems()):
            if isinstance(child, ConnectorItem):
                self._overview._conn.pop(child.endpoint_id, None)
                child.setParentItem(None)
                if child.scene():
                    child.scene().removeItem(child)

        cols = max(self._panel.cols, 1)
        rows = max(self._panel.rows, 1)
        block_h = float(HEADER_H + rows * cols * PORT_ROW_H)
        self._display_h = block_h
        self.setRect(0, 0, self._display_w, block_h)

        for row in range(rows):
            for col in range(cols):
                port = self._panel.port_at(row, col)
                if port is None:
                    port_id = f"{self._panel.id}-{chr(65 + row)}{col + 1:02d}"
                    port = PatchPort(id=port_id, row=row, col=col)
                    self._panel.ports.append(port)
                if port.id:
                    idx = row * cols + col
                    y = HEADER_H + idx * PORT_ROW_H + PORT_ROW_H / 2
                    sig = port.signal_type or "Other"
                    conn_front = ConnectorItem(port.id, sig)
                    conn_front.setPos(self._display_w, y)
                    conn_front.setParentItem(self)
                    self._overview._conn[port.id] = conn_front
                    rear_id = f"{port.id}:rear"
                    conn_rear = ConnectorItem(rear_id, sig)
                    conn_rear.setPos(0.0, y)
                    conn_rear.setParentItem(self)
                    self._overview._conn[rear_id] = conn_rear

        self._handle.setPos(self._display_w, block_h)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if hasattr(self, "_overview"):
                self._overview._update_cables()
        return super().itemChange(change, value)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._display_w, self._display_h)

    def paint(self, painter: QPainter, option, widget=None):
        w, h = self._display_w, self._display_h
        cols = max(self._panel.cols, 1)
        rows = max(self._panel.rows, 1)

        painter.fillRect(QRectF(0, 0, w, HEADER_H), C_PANEL_HDR)
        painter.setPen(QPen(C_WHITE))
        painter.setFont(_font(8, True))
        painter.drawText(
            QRectF(6, 0, w - 12, HEADER_H), Qt.AlignmentFlag.AlignVCenter,
            _elide(f"{self._panel.id}  —  {self._panel.name}", 32),
        )

        for row in range(rows):
            for col in range(cols):
                port = self._panel.port_at(row, col)
                idx = row * cols + col
                py = HEADER_H + idx * PORT_ROW_H
                sig = (port.signal_type if port else None) or "Other"
                fill = QColor(SIGNAL_COLORS.get(sig, SIGNAL_COLORS["Other"]))
                painter.fillRect(QRectF(0, py, w, PORT_ROW_H), fill)
                painter.setPen(QPen(C_BORDER, 0.5))
                painter.drawRect(QRectF(0, py, w, PORT_ROW_H))
                if port:
                    auto_lbl = f"{chr(65 + row)}{col + 1:02d}"
                    lbl = port.label or auto_lbl
                    painter.setPen(QPen(QColor("#212121")))
                    painter.setFont(_font(7))
                    painter.drawText(
                        QRectF(6, py, w * 0.6, PORT_ROW_H),
                        Qt.AlignmentFlag.AlignVCenter, _elide(lbl, 10),
                    )
                    if port.label and port.label != auto_lbl:
                        painter.setFont(_font(6))
                        painter.setPen(QPen(QColor("#555")))
                        painter.drawText(
                            QRectF(w * 0.6, py, w * 0.4 - 6, PORT_ROW_H),
                            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                            auto_lbl,
                        )

        painter.setPen(QPen(C_RACK_EDGE, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(0, 0, w, h))


# ── DAQ crate block ───────────────────────────────────────────────────────────

class CrateBlock(QGraphicsRectItem):
    def __init__(self, crate: DaqCrate, overview: "SystemOverview",
                 x: float, y: float, display_w: float):
        h = self._content_h(crate)
        super().__init__(0, 0, display_w, h)
        self._crate = crate
        self._overview = overview
        self._display_w = display_w
        self._display_h = h
        self.setPos(x, y)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.GlobalColor.transparent))
        self._handle = _ResizeHandle(self, horizontal_only=True)
        self._handle.setParentItem(self)
        self._module_bar_rects: list = []
        self._press_pos = QPointF()
        self._rebuild_connectors()

    def set_width(self, w: float):
        self._display_w = w
        h = self._content_h(self._crate)
        self._display_h = h
        self.setRect(0, 0, w, h)
        self._rebuild_connectors()
        self._overview._update_cables()
        self.update()

    @staticmethod
    def _content_h(crate: DaqCrate) -> float:
        h = float(HEADER_H)
        for slot in crate.slots:
            h += SLOT_H
            if slot.module:
                mod = slot.module
                h += MODULE_H
                if not mod.collapsed:
                    inputs  = [ch for ch in mod.channels if ch.role != "output"]
                    outputs = [ch for ch in mod.channels if ch.role == "output"]
                    if mod.coupled_io:
                        in_grps, out_grps = _coupled_groups(mod.channels)
                        if in_grps or out_grps:
                            num_rows = max(
                                max((len(g) for _, g in in_grps), default=0),
                                max((len(g) for _, g in out_grps), default=0),
                            )
                            h += SECTION_H + num_rows * CHAN_H
                    else:
                        h += len(mod.channels) * CHAN_H
                        if inputs and outputs:
                            h += SECTION_H * 2  # "INPUTS ▸" + "◂ OUTPUTS" headers
        return max(h, float(HEADER_H + 24))

    def _rebuild_connectors(self):
        for child in list(self.childItems()):
            if isinstance(child, ConnectorItem):
                self._overview._conn.pop(child.endpoint_id, None)
                child.setParentItem(None)
                if child.scene():
                    child.scene().removeItem(child)

        cy = float(HEADER_H)
        for slot in self._crate.slots:
            cy += SLOT_H
            if slot.module:
                mod = slot.module
                cy += MODULE_H
                if not mod.collapsed:
                    inputs  = [ch for ch in mod.channels if ch.role != "output"]
                    outputs = [ch for ch in mod.channels if ch.role == "output"]
                    has_both = bool(inputs) and bool(outputs)

                    if mod.coupled_io:
                        in_grps, out_grps = _coupled_groups(mod.channels)
                        N_in  = len(in_grps)
                        N_out = len(out_grps)
                        total_cols = max(N_in + 1 + N_out, 1)
                        col_w = self._display_w / total_cols
                        cy += SECTION_H  # skip column-header row
                        num_rows = max(
                            max((len(g) for _, g in in_grps), default=0),
                            max((len(g) for _, g in out_grps), default=0),
                        )
                        for k in range(num_rows):
                            for i, (_, grp) in enumerate(in_grps):
                                if k < len(grp):
                                    ch = grp[k]
                                    if ch.id:
                                        linked = (self._overview.project.cable_by_id(ch.cable_id)
                                                  if ch.cable_id else None)
                                        sig = linked.signal_type if linked else "Other"
                                        conn = ConnectorItem(ch.id, sig, role="input")
                                        conn.setPos((i + 0.5) * col_w, cy + CHAN_H / 2)
                                        conn.setParentItem(self)
                                        self._overview._conn[ch.id] = conn
                            for j, (_, grp) in enumerate(out_grps):
                                if k < len(grp):
                                    ch = grp[k]
                                    if ch.id:
                                        linked = (self._overview.project.cable_by_id(ch.cable_id)
                                                  if ch.cable_id else None)
                                        sig = linked.signal_type if linked else "Other"
                                        conn = ConnectorItem(ch.id, sig, role="output")
                                        conn.setPos((N_in + 1 + j + 0.5) * col_w, cy + CHAN_H / 2)
                                        conn.setParentItem(self)
                                        self._overview._conn[ch.id] = conn
                            cy += CHAN_H
                    else:
                        if has_both:
                            cy += SECTION_H  # "INPUTS ▸" header
                        for ch in inputs:
                            if ch.id:
                                linked = (self._overview.project.cable_by_id(ch.cable_id)
                                          if ch.cable_id else None)
                                sig = linked.signal_type if linked else "Other"
                                conn = ConnectorItem(ch.id, sig, role="input")
                                conn.setPos(0.0, cy + CHAN_H / 2)
                                conn.setParentItem(self)
                                self._overview._conn[ch.id] = conn
                            cy += CHAN_H
                        if has_both:
                            cy += SECTION_H  # "◂ OUTPUTS" header
                        for ch in outputs:
                            if ch.id:
                                linked = (self._overview.project.cable_by_id(ch.cable_id)
                                          if ch.cable_id else None)
                                sig = linked.signal_type if linked else "Other"
                                conn = ConnectorItem(ch.id, sig, role="output")
                                conn.setPos(self._display_w, cy + CHAN_H / 2)
                                conn.setParentItem(self)
                                self._overview._conn[ch.id] = conn
                            cy += CHAN_H

        h = self._content_h(self._crate)
        self._handle.setPos(self._display_w + EAR_W, h / 2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if hasattr(self, "_overview"):
                self._overview._update_cables()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self._press_pos = event.scenePos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            delta = event.scenePos() - self._press_pos
            if abs(delta.x()) < 5 and abs(delta.y()) < 5:
                lp = event.pos()
                for rect, mod in self._module_bar_rects:
                    if rect.contains(lp):
                        mod.collapsed = not mod.collapsed
                        self.prepareGeometryChange()
                        self._display_h = self._content_h(self._crate)
                        self.setRect(0, 0, self._display_w, self._display_h)
                        self._rebuild_connectors()
                        self.update()
                        self._overview.on_change()
                        self._overview._update_cables()
                        break

    def boundingRect(self) -> QRectF:
        h = self._content_h(self._crate)
        return QRectF(-EAR_W, 0, self._display_w + EAR_W * 2, h)

    def paint(self, painter: QPainter, option, widget=None):
        w = self._display_w
        h = self._content_h(self._crate)
        self._module_bar_rects = []

        # Rack ears
        for ex, ew in ((-EAR_W, EAR_W), (w, EAR_W)):
            painter.fillRect(QRectF(ex, 0, ew, h), QColor("#78909c"))
            painter.setPen(QPen(C_RACK_EDGE, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(ex, 0, ew, h))
        for dy in (8.0, h / 2, h - 10.0):
            for ex in (-EAR_W + 4, w + 4):
                painter.setBrush(QBrush(QColor("#546e7a")))
                painter.setPen(QPen(C_RACK_EDGE, 0.5))
                painter.drawEllipse(QRectF(ex, dy - 3, 6, 6))

        # Crate header
        painter.fillRect(QRectF(0, 0, w, HEADER_H), C_CRATE_HDR)
        painter.setPen(QPen(C_WHITE))
        painter.setFont(_font(8, True))
        painter.drawText(
            QRectF(8, 0, w - 16, HEADER_H), Qt.AlignmentFlag.AlignVCenter,
            _elide(f"{self._crate.name or self._crate.id}  [{self._crate.crate_type}]", 38),
        )

        cy = float(HEADER_H)
        for slot in self._crate.slots:
            painter.fillRect(QRectF(0, cy, w, SLOT_H), C_SLOT_HDR)
            painter.setPen(QPen(C_WHITE))
            painter.setFont(_font(8))
            painter.drawText(
                QRectF(8, cy, w - 16, SLOT_H), Qt.AlignmentFlag.AlignVCenter,
                f"Slot {slot.slot_number:02d}"
            )
            cy += SLOT_H

            if slot.module:
                mod = slot.module
                inputs  = [ch for ch in mod.channels if ch.role != "output"]
                outputs = [ch for ch in mod.channels if ch.role == "output"]
                has_both = bool(inputs) and bool(outputs)

                mod_color = QColor(mod.color)
                mod_rect = QRectF(0, cy, w, MODULE_H)
                self._module_bar_rects.append((mod_rect, mod))
                painter.fillRect(mod_rect, mod_color)
                painter.setPen(QPen(C_WHITE))
                painter.setFont(_font(8, True))
                icon = "▶ " if mod.collapsed else "▼ "
                painter.drawText(
                    QRectF(8, cy, w - 80, MODULE_H), Qt.AlignmentFlag.AlignVCenter,
                    _elide(icon + (mod.name or mod.id), 24),
                )
                painter.setFont(_font(7))
                painter.setPen(QPen(QColor("#cfd8dc")))
                if has_both:
                    io_label = f"{mod.module_type}  {len(inputs)}in/{len(outputs)}out"
                else:
                    io_label = f"{mod.module_type}  {len(mod.channels)} ch"
                painter.drawText(
                    QRectF(w - 90, cy, 86, MODULE_H),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                    io_label,
                )
                cy += MODULE_H

                if not mod.collapsed:
                    if mod.coupled_io:
                        # ── Coupled: column-per-connector layout ──────────────
                        in_grps, out_grps = _coupled_groups(mod.channels)
                        N_in  = len(in_grps)
                        N_out = len(out_grps)
                        total_cols = max(N_in + 1 + N_out, 1)
                        col_w = w / total_cols

                        # Column header row
                        painter.fillRect(QRectF(0, cy, w, SECTION_H), QColor("#e8eaf6"))
                        for i, (spec_name, _) in enumerate(in_grps):
                            painter.setFont(_font(6, True))
                            painter.setPen(QPen(C_IN_TEXT))
                            painter.drawText(
                                QRectF(i * col_w + 1, cy, col_w - 2, SECTION_H),
                                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter,
                                _elide(spec_name, 10),
                            )
                        for j, (spec_name, _) in enumerate(out_grps):
                            painter.setFont(_font(6, True))
                            painter.setPen(QPen(C_OUT_TEXT))
                            painter.drawText(
                                QRectF((N_in + 1 + j) * col_w + 1, cy, col_w - 2, SECTION_H),
                                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter,
                                _elide(spec_name, 10),
                            )
                        # Column separator lines in header
                        painter.setPen(QPen(QColor("#9fa8da"), 0.5))
                        for c in range(1, total_cols):
                            painter.drawLine(QPointF(c * col_w, cy), QPointF(c * col_w, cy + SECTION_H))
                        cy += SECTION_H

                        num_rows = max(
                            max((len(g) for _, g in in_grps), default=0),
                            max((len(g) for _, g in out_grps), default=0),
                        )
                        for k in range(num_rows):
                            fill = C_CHAN_A if k % 2 == 0 else C_CHAN_B
                            painter.fillRect(QRectF(0, cy, w, CHAN_H), fill)

                            # Column separators
                            painter.setPen(QPen(QColor("#bdbdbd"), 0.5))
                            for c in range(1, total_cols):
                                painter.drawLine(QPointF(c * col_w, cy), QPointF(c * col_w, cy + CHAN_H))
                            painter.drawLine(QPointF(0, cy + CHAN_H), QPointF(w, cy + CHAN_H))

                            # Input columns
                            for i, (_, grp) in enumerate(in_grps):
                                if k < len(grp):
                                    ch = grp[k]
                                    x = i * col_w
                                    painter.setFont(_font(6))
                                    painter.setPen(QPen(C_IN_TEXT))
                                    painter.drawText(
                                        QRectF(x + CONN_R * 2 + 1, cy, col_w - CONN_R * 2 - 2, CHAN_H),
                                        Qt.AlignmentFlag.AlignVCenter,
                                        _elide(ch.signal_label or ch.cable_id or "", 7),
                                    )

                            # Channel number (center column)
                            ch_num = None
                            if in_grps and k < len(in_grps[0][1]):
                                ch_num = in_grps[0][1][k].channel_number
                            elif out_grps and k < len(out_grps[0][1]):
                                ch_num = out_grps[0][1][k].channel_number
                            if ch_num is not None:
                                painter.setFont(_font(7, True))
                                painter.setPen(QPen(QColor("#212121")))
                                painter.drawText(
                                    QRectF(N_in * col_w, cy, col_w, CHAN_H),
                                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter,
                                    f"{ch_num:02d}",
                                )

                            # Output columns
                            for j, (_, grp) in enumerate(out_grps):
                                if k < len(grp):
                                    ch = grp[k]
                                    x = (N_in + 1 + j) * col_w
                                    painter.setFont(_font(6))
                                    painter.setPen(QPen(C_OUT_TEXT))
                                    painter.drawText(
                                        QRectF(x + 1, cy, col_w - CONN_R * 2 - 2, CHAN_H),
                                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                                        _elide(ch.signal_label or ch.cable_id or "", 7),
                                    )
                            cy += CHAN_H
                    else:
                        # ── Uncoupled: stacked sections ──────────────────────
                        if has_both:
                            painter.fillRect(QRectF(0, cy, w, SECTION_H), C_IN_HDR)
                            painter.setFont(_font(6, True))
                            painter.setPen(QPen(C_IN_TEXT))
                            painter.drawText(
                                QRectF(4, cy, w - 8, SECTION_H),
                                Qt.AlignmentFlag.AlignVCenter,
                                "INPUTS ▸",
                            )
                            cy += SECTION_H

                        for i, ch in enumerate(inputs):
                            fill = C_CHAN_A if i % 2 == 0 else C_CHAN_B
                            painter.fillRect(QRectF(0, cy, w, CHAN_H), fill)
                            painter.setPen(QPen(QColor("#bdbdbd"), 0.5))
                            painter.drawLine(QPointF(0, cy + CHAN_H), QPointF(w, cy + CHAN_H))
                            painter.setFont(_font(7, True))
                            painter.setPen(QPen(QColor("#212121")))
                            painter.drawText(QRectF(6, cy, 22, CHAN_H), Qt.AlignmentFlag.AlignVCenter,
                                             f"{ch.channel_number:02d}")
                            painter.setFont(_font(7))
                            painter.drawText(QRectF(32, cy, 90, CHAN_H), Qt.AlignmentFlag.AlignVCenter,
                                             _elide(ch.signal_label, 14))
                            painter.setPen(QPen(QColor("#546e7a")))
                            painter.drawText(QRectF(130, cy, 90, CHAN_H), Qt.AlignmentFlag.AlignVCenter,
                                             _elide(ch.cable_id, 12))
                            cy += CHAN_H

                        if has_both:
                            painter.fillRect(QRectF(0, cy, w, SECTION_H), C_OUT_HDR)
                            painter.setFont(_font(6, True))
                            painter.setPen(QPen(C_OUT_TEXT))
                            painter.drawText(
                                QRectF(4, cy, w - 8, SECTION_H),
                                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                                "◂ OUTPUTS",
                            )
                            cy += SECTION_H

                        for i, ch in enumerate(outputs):
                            fill = C_CHAN_A if i % 2 == 0 else C_CHAN_B
                            painter.fillRect(QRectF(0, cy, w, CHAN_H), fill)
                            painter.setPen(QPen(QColor("#bdbdbd"), 0.5))
                            painter.drawLine(QPointF(0, cy + CHAN_H), QPointF(w, cy + CHAN_H))
                            painter.setFont(_font(7, True))
                            painter.setPen(QPen(QColor("#212121")))
                            painter.drawText(QRectF(6, cy, 22, CHAN_H), Qt.AlignmentFlag.AlignVCenter,
                                             f"{ch.channel_number:02d}")
                            painter.setFont(_font(7))
                            painter.drawText(QRectF(32, cy, 90, CHAN_H), Qt.AlignmentFlag.AlignVCenter,
                                             _elide(ch.signal_label, 14))
                            painter.setPen(QPen(QColor("#546e7a")))
                            painter.drawText(QRectF(130, cy, 90, CHAN_H), Qt.AlignmentFlag.AlignVCenter,
                                             _elide(ch.cable_id, 12))
                            cy += CHAN_H

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(C_RACK_EDGE, 2))
        painter.drawRect(QRectF(0, 0, w, h))


# ── Cable bezier ──────────────────────────────────────────────────────────────

class CablePath(QGraphicsPathItem):
    def __init__(self, cable: Cable, path: QPainterPath,
                 color: QColor, overview: "SystemOverview"):
        super().__init__(path)
        self._cable = cable
        self._overview = overview
        thin  = QPen(color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        thick = QPen(color, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        self._pen_n, self._pen_h = thin, thick
        self.setPen(thin)
        self.setAcceptHoverEvents(True)
        self.setZValue(5)
        self.setToolTip(
            f"{cable.id}: {cable.from_endpoint}  →  {cable.to_endpoint}\n"
            f"Type: {cable.cable_type}   Signal: {cable.signal_type}"
        )

    def hoverEnterEvent(self, event):
        self.setPen(self._pen_h)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(self._pen_n)
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._overview._connect_mode:
            self._edit_cable()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.addAction(f"Cable: {self._cable.id}").setEnabled(False)
        menu.addSeparator()
        edit_act = menu.addAction("Edit Cable…")
        del_act  = menu.addAction("Delete Cable")
        result = menu.exec(event.screenPos().toPoint())
        if result == edit_act:
            self._edit_cable()
        elif result == del_act:
            self._overview._delete_cable(self._cable)

    def _edit_cable(self):
        ep_ids = sorted(self._overview._conn.keys())
        dlg = _CableDialog(
            None,
            from_ep=self._cable.from_endpoint,
            to_ep=self._cable.to_endpoint,
            signal_type=self._cable.signal_type,
            project=self._overview.project,
            cable=self._cable,
            endpoint_ids=ep_ids,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to(self._cable)
            self._overview.on_change()
            self._overview._update_cables()


# ── Custom view ───────────────────────────────────────────────────────────────

class _SceneView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, overview: "SystemOverview"):
        super().__init__(scene)
        self._ov = overview

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            sp = self.mapToScene(event.pos())
            conn = self._connector_at(sp)
            if self._ov._connect_mode:
                self._ov._on_connector_click(conn, sp)
                return
            if conn is not None and self._ov._start_reroute(conn):
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._ov._connect_mode:
            self._ov._on_drag_move(self.mapToScene(event.pos()))
            event.accept()
            return
        if self._ov._reroute_mode:
            self._ov._on_reroute_move(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._ov._reroute_mode:
            sp = self.mapToScene(event.pos())
            conn = self._connector_at(sp)
            if conn is not None:
                self._ov._complete_reroute(conn)
            else:
                self._ov._cancel_reroute()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            if self._ov._connect_mode:
                self._ov._cancel_drag()
            elif self._ov._reroute_mode:
                self._ov._cancel_reroute()
        else:
            super().keyPressEvent(event)

    def _connector_at(self, scene_pos: QPointF) -> "ConnectorItem | None":
        r = CONN_R + 6
        for item in self.scene().items(
            QRectF(scene_pos.x() - r, scene_pos.y() - r, r * 2, r * 2)
        ):
            if isinstance(item, ConnectorItem):
                return item
        return None


# ── Cable dialogs ─────────────────────────────────────────────────────────────

class _CableDialog(QDialog):
    """Create or edit a cable. Pass cable=None for create mode (endpoints fixed)."""

    def __init__(self, parent, from_ep: str, to_ep: str,
                 signal_type: str, project: Project,
                 cable: "Cable | None" = None,
                 endpoint_ids: "list[str] | None" = None):
        super().__init__(parent)
        from app.storage.cable_type import load_cable_types
        self._cts = load_cable_types()
        editing = cable is not None
        self.setWindowTitle("Edit Cable" if editing else "Create Cable")
        layout = QFormLayout(self)

        self._id = QLineEdit(cable.id if editing else project.next_cable_id())
        self._id.setReadOnly(True)
        self._label = QLineEdit(cable.label if editing else "")

        layout.addRow("Cable ID:", self._id)
        layout.addRow("Label:", self._label)

        if editing and endpoint_ids is not None:
            eps = sorted(set(endpoint_ids) | {from_ep, to_ep})
            self._from_combo = QComboBox()
            self._from_combo.setEditable(True)
            self._from_combo.addItems(eps)
            self._from_combo.setCurrentText(from_ep)
            self._to_combo = QComboBox()
            self._to_combo.setEditable(True)
            self._to_combo.addItems(eps)
            self._to_combo.setCurrentText(to_ep)
            layout.addRow("From:", self._from_combo)
            layout.addRow("To:", self._to_combo)
            self._editing = True
        else:
            self._from_line = QLineEdit(from_ep)
            self._from_line.setReadOnly(True)
            self._to_line = QLineEdit(to_ep)
            self._to_line.setReadOnly(True)
            layout.addRow("From:", self._from_line)
            layout.addRow("To:", self._to_line)
            self._editing = False

        # Cable type
        self._type = QComboBox()
        type_names = [ct.name for ct in self._cts]
        self._type.addItems(type_names)
        init_type = cable.cable_type if editing else (self._cts[0].id if self._cts else "")
        init_type_name = next((ct.name for ct in self._cts if ct.id == init_type), init_type)
        self._type.setCurrentText(init_type_name)

        self._sig = QComboBox()
        self._sig.addItems(SIGNAL_TYPES)
        idx = self._sig.findText(cable.signal_type if editing else signal_type)
        if idx >= 0:
            self._sig.setCurrentIndex(idx)

        self._len = QDoubleSpinBox()
        self._len.setRange(0, 9999)
        self._len.setSuffix(" m")
        self._len.setValue(cable.length_m if editing else 0.0)

        self._notes = QLineEdit(cable.notes if editing else "")

        self._dir = QComboBox()
        self._dir.addItems(["", "→ forward", "← reverse", "↔ both"])
        self._dir.setCurrentText(cable.direction if editing else "")

        layout.addRow("Cable Type:", self._type)
        layout.addRow("Signal Type:", self._sig)
        layout.addRow("Length:", self._len)
        layout.addRow("Notes:", self._notes)
        layout.addRow("Direction:", self._dir)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _get_from(self) -> str:
        return self._from_combo.currentText().strip() if self._editing else self._from_line.text().strip()

    def _get_to(self) -> str:
        return self._to_combo.currentText().strip() if self._editing else self._to_line.text().strip()

    def _get_cable_type_id(self) -> str:
        name = self._type.currentText()
        return next((ct.id for ct in self._cts if ct.name == name), name)

    def apply_to(self, cable: Cable):
        cable.label = self._label.text().strip()
        cable.cable_type = self._get_cable_type_id()
        cable.signal_type = self._sig.currentText()
        cable.from_endpoint = self._get_from()
        cable.to_endpoint = self._get_to()
        cable.length_m = self._len.value()
        cable.notes = self._notes.text().strip()
        cable.direction = self._dir.currentText()

    def cable(self) -> Cable:
        c = Cable(id=self._id.text().strip())
        self.apply_to(c)
        return c


# ── Main widget ───────────────────────────────────────────────────────────────

class SystemOverview(QWidget):
    def __init__(self, project: Project, on_change: Callable = None):
        super().__init__()
        self.project = project
        self.on_change = on_change or (lambda: None)
        self._layout: dict[str, dict] = {}
        self._blocks: dict[str, QGraphicsRectItem] = {}
        self._conn:   dict[str, ConnectorItem] = {}
        self._cable_items:  list = []
        self._stub_items:   list = []
        self._bundle_items: list = []
        # Connect mode state
        self._connect_mode = False
        self._drag_src: ConnectorItem | None = None
        self._drag_line: QGraphicsLineItem | None = None
        # Reroute mode state
        self._reroute_mode = False
        self._reroute_cable: Cable | None = None
        self._reroute_end: str = ""
        self._reroute_fixed_pos = QPointF()
        self._reroute_drag_line: QGraphicsLineItem | None = None
        self._build_ui()

    def set_project(self, project: Project):
        self.project = project
        self._layout.clear()
        self.refresh()

    def refresh(self):
        self._save_layout()
        self._cancel_drag()
        self._cancel_reroute()
        self._scene.clear()
        self._blocks.clear()
        self._conn.clear()
        self._cable_items.clear()
        self._stub_items.clear()
        self._bundle_items.clear()
        self._draw_panels()
        self._draw_racks()
        self._draw_cables()
        self._draw_stubs()
        self._draw_bundles()

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
        btn_export = QPushButton("Export Image…")
        btn_export.clicked.connect(self._export_image_dialog)
        toolbar.addWidget(btn_refresh)
        toolbar.addWidget(btn_fit)
        toolbar.addWidget(btn_export)

        self._btn_connect = QPushButton("Connect Mode")
        self._btn_connect.setCheckable(True)
        self._btn_connect.setToolTip(
            "Click a connector dot to start, click another to create a cable.\n"
            "Outside connect mode: drag a cable's endpoint dot to reroute it.\n"
            "Double-click a cable to edit its properties.\n"
            "Right-click a cable to edit or delete.  Escape cancels."
        )
        self._btn_connect.toggled.connect(self._toggle_connect_mode)
        self._btn_connect.setStyleSheet(
            "QPushButton:checked { background:#ff6b35; color:white; font-weight:bold; }"
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

    # ── Export image ──────────────────────────────────────────────────────────

    def _export_image_dialog(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Overview Image", "",
            "PNG Image (*.png);;SVG Image (*.svg)"
        )
        if path:
            self.export_image(path)

    def export_image(self, path: str) -> None:
        rect = self._scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        if rect.isNull():
            return
        path = str(path)
        if path.lower().endswith(".svg"):
            try:
                from PyQt6.QtSvg import QSvgGenerator
                gen = QSvgGenerator()
                gen.setFileName(path)
                gen.setSize(rect.size().toSize())
                gen.setViewBox(rect)
                p = QPainter(gen)
                self._scene.render(p, source=rect)
                p.end()
                return
            except ImportError:
                path = path[:-4] + ".png"

        scale = 2
        sz = rect.size().toSize() * scale
        image = QImage(sz, QImage.Format.Format_ARGB32)
        image.fill(QColor("#ffffff"))
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._scene.render(p, target=QRectF(0, 0, sz.width(), sz.height()), source=rect)
        p.end()
        if not path.lower().endswith(".png"):
            path += ".png"
        image.save(path)

    # ── Layout persistence ────────────────────────────────────────────────────

    def _save_layout(self):
        for key, block in self._blocks.items():
            p = block.scenePos()
            entry: dict = {"x": p.x(), "y": p.y(), "w": block._display_w}
            if isinstance(block, PanelBlock):
                entry["h"] = block._display_h
            self._layout[key] = entry

    # ── Draw blocks ───────────────────────────────────────────────────────────

    def _draw_panels(self):
        y = 20.0
        for panel in self.project.patch_panels:
            key = f"panel:{panel.id}"
            saved = self._layout.get(key)
            bx = saved["x"] if saved else PANEL_X
            by = saved["y"] if saved else y
            bw = saved["w"] if saved else float(PANEL_W)
            bh = float(HEADER_H + panel.rows * panel.cols * PORT_ROW_H)
            block = PanelBlock(panel, self, bx, by, bw, bh)
            self._scene.addItem(block)
            self._blocks[key] = block
            y = max(y, by + bh + ITEM_GAP)

    def _draw_racks(self):
        y = 20.0
        for crate in self.project.crates:
            key = f"crate:{crate.id}"
            saved = self._layout.get(key)
            bx = saved["x"] if saved else float(RACK_X)
            by = saved["y"] if saved else y
            bw = saved["w"] if saved else float(CRATE_W)
            block = CrateBlock(crate, self, bx, by, bw)
            self._scene.addItem(block)
            self._blocks[key] = block
            h = CrateBlock._content_h(crate)
            y = max(y, by + h + ITEM_GAP)

    # ── Cables ────────────────────────────────────────────────────────────────

    def _update_cables(self):
        for item in self._cable_items + self._stub_items + self._bundle_items:
            if item.scene():
                self._scene.removeItem(item)
        self._cable_items.clear()
        self._stub_items.clear()
        self._bundle_items.clear()
        self._draw_cables()
        self._draw_stubs()
        self._draw_bundles()

    @staticmethod
    def _arrowhead(tip: QPointF, tangent: QPointF, color: QColor) -> "QGraphicsPolygonItem | None":
        length = math.hypot(tangent.x(), tangent.y())
        if length < 1e-6:
            return None
        ux, uy = tangent.x() / length, tangent.y() / length
        px, py = -uy, ux
        sz, hw = 10.0, 5.0
        poly = QPolygonF([
            QPointF(tip.x(), tip.y()),
            QPointF(tip.x() - sz * ux + hw * px, tip.y() - sz * uy + hw * py),
            QPointF(tip.x() - sz * ux - hw * px, tip.y() - sz * uy - hw * py),
        ])
        item = QGraphicsPolygonItem(poly)
        item.setBrush(QBrush(color))
        item.setPen(QPen(color, 1))
        item.setZValue(6)
        return item

    def _draw_cables(self):
        for cable in self.project.cables:
            src_c = self._conn.get(cable.from_endpoint)
            dst_c = self._conn.get(cable.to_endpoint)
            if src_c is None or dst_c is None:
                continue
            color = QColor(SIGNAL_COLORS.get(cable.signal_type, SIGNAL_COLORS["Other"]))
            src, dst = src_c.scenePos(), dst_c.scenePos()
            mid_x = (src.x() + dst.x()) / 2
            ctrl1, ctrl2 = QPointF(mid_x, src.y()), QPointF(mid_x, dst.y())
            path = QPainterPath(src)
            path.cubicTo(ctrl1, ctrl2, dst)
            cp = CablePath(cable, path, color, self)
            self._scene.addItem(cp)
            self._cable_items.append(cp)
            if cable.direction in ("→ forward", "↔ both"):
                ah = self._arrowhead(dst, dst - ctrl2, color)
                if ah:
                    self._scene.addItem(ah)
                    self._cable_items.append(ah)
            if cable.direction in ("← reverse", "↔ both"):
                ah = self._arrowhead(src, src - ctrl1, color)
                if ah:
                    self._scene.addItem(ah)
                    self._cable_items.append(ah)

    def _draw_stubs(self):
        for cable in self.project.cables:
            src_c = self._conn.get(cable.from_endpoint)
            dst_c = self._conn.get(cable.to_endpoint)
            if src_c is not None and dst_c is None:
                anchor, label = src_c.scenePos(), cable.to_endpoint
                end = QPointF(anchor.x() + STUB_LEN, anchor.y())
                left = False
            elif dst_c is not None and src_c is None:
                anchor, label = dst_c.scenePos(), cable.from_endpoint
                end = QPointF(anchor.x() - STUB_LEN, anchor.y())
                left = True
            else:
                continue
            color = QColor(SIGNAL_COLORS.get(cable.signal_type, SIGNAL_COLORS["Other"]))
            line = self._scene.addLine(
                anchor.x(), anchor.y(), end.x(), end.y(),
                QPen(color, 1.5, Qt.PenStyle.DashLine)
            )
            dot = self._scene.addEllipse(
                QRectF(end.x() - 4, end.y() - 4, 8, 8), QPen(color, 1), QBrush(color)
            )
            t = self._scene.addText(_elide(label, 18))
            t.setFont(_font(6))
            t.setDefaultTextColor(QColor("#555"))
            t.setPos(
                end.x() - t.boundingRect().width() - 2 if left else end.x() + 2,
                end.y() - 9,
            )
            self._stub_items.extend([line, dot, t])

    def _draw_bundles(self):
        bundled_cable_ids: set[str] = set()
        for bundle in self.project.bundles:
            if not bundle.cable_ids:
                continue
            src_pts, dst_pts = [], []
            for cid in bundle.cable_ids:
                cable = self.project.cable_by_id(cid)
                if cable is None:
                    continue
                src_c = self._conn.get(cable.from_endpoint)
                dst_c = self._conn.get(cable.to_endpoint)
                if src_c:
                    src_pts.append(src_c.scenePos())
                if dst_c:
                    dst_pts.append(dst_c.scenePos())
                if src_c and dst_c:
                    bundled_cable_ids.add(cid)
            if not src_pts or not dst_pts:
                continue
            ax = sum(p.x() for p in src_pts) / len(src_pts)
            ay = sum(p.y() for p in src_pts) / len(src_pts)
            bx = sum(p.x() for p in dst_pts) / len(dst_pts)
            by = sum(p.y() for p in dst_pts) / len(dst_pts)
            color = QColor(bundle.color)
            color.setAlphaF(0.55)
            mid_x = (ax + bx) / 2
            path = QPainterPath(QPointF(ax, ay))
            path.cubicTo(QPointF(mid_x, ay), QPointF(mid_x, by), QPointF(bx, by))
            bundle_path = self._scene.addPath(
                path, QPen(color, 6, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            )
            bundle_path.setZValue(4)
            bundle_path.setToolTip(f"Bundle: {bundle.name}  ({len(bundle.cable_ids)} cables)")
            self._bundle_items.append(bundle_path)
            for p in src_pts:
                fan = self._scene.addLine(ax, ay, p.x(), p.y(), QPen(color, 1.5))
                fan.setZValue(4)
                self._bundle_items.append(fan)
            for p in dst_pts:
                fan = self._scene.addLine(bx, by, p.x(), p.y(), QPen(color, 1.5))
                fan.setZValue(4)
                self._bundle_items.append(fan)
        for item in self._cable_items:
            if isinstance(item, CablePath) and item._cable.id in bundled_cable_ids:
                item.setOpacity(0.35)

    # ── Connect mode ──────────────────────────────────────────────────────────

    def _toggle_connect_mode(self, on: bool):
        self._connect_mode = on
        if on:
            self._cancel_reroute()
            self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._cancel_drag()
            self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self._view.unsetCursor()

    def _on_connector_click(self, connector: "ConnectorItem | None", scene_pos: QPointF):
        if connector is None:
            return
        if self._drag_src is None:
            self._drag_src = connector
            connector.set_selected(True)
            self._drag_line = self._scene.addLine(
                connector.scenePos().x(), connector.scenePos().y(),
                connector.scenePos().x(), connector.scenePos().y(),
                QPen(C_DRAG_LINE, 1.5, Qt.PenStyle.DashLine),
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
            if self._drag_line.scene():
                self._scene.removeItem(self._drag_line)
            self._drag_line = None

    def _complete_connection(self, src: ConnectorItem, dst: ConnectorItem):
        dlg = _CableDialog(
            self, src.endpoint_id, dst.endpoint_id,
            src.signal_type or dst.signal_type, self.project,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cable = dlg.cable()
        if not cable.id:
            return
        self.project.cables.append(cable)
        self.on_change()
        self._update_cables()

    # ── Reroute mode ──────────────────────────────────────────────────────────

    def _start_reroute(self, conn: ConnectorItem) -> bool:
        ep = conn.endpoint_id
        cable = None
        reroute_end = ""
        for c in self.project.cables:
            if c.from_endpoint == ep:
                cable = c
                reroute_end = "from"
                break
            if c.to_endpoint == ep:
                cable = c
                reroute_end = "to"
                break
        if cable is None:
            return False

        self._reroute_mode = True
        self._reroute_cable = cable
        self._reroute_end = reroute_end

        fixed_ep = cable.to_endpoint if reroute_end == "from" else cable.from_endpoint
        fixed_conn = self._conn.get(fixed_ep)
        self._reroute_fixed_pos = fixed_conn.scenePos() if fixed_conn else conn.scenePos()

        self._reroute_drag_line = self._scene.addLine(
            self._reroute_fixed_pos.x(), self._reroute_fixed_pos.y(),
            conn.scenePos().x(), conn.scenePos().y(),
            QPen(C_DRAG_LINE, 2, Qt.PenStyle.DashLine),
        )
        self._reroute_drag_line.setZValue(20)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        return True

    def _on_reroute_move(self, scene_pos: QPointF):
        if self._reroute_drag_line:
            self._reroute_drag_line.setLine(
                self._reroute_fixed_pos.x(), self._reroute_fixed_pos.y(),
                scene_pos.x(), scene_pos.y(),
            )

    def _complete_reroute(self, conn: ConnectorItem):
        if self._reroute_cable is None:
            return
        old_ep = (self._reroute_cable.from_endpoint if self._reroute_end == "from"
                  else self._reroute_cable.to_endpoint)
        if conn.endpoint_id == old_ep:
            self._cancel_reroute()
            return
        if self._reroute_end == "from":
            self._reroute_cable.from_endpoint = conn.endpoint_id
        else:
            self._reroute_cable.to_endpoint = conn.endpoint_id
        self.on_change()
        self._cancel_reroute()
        self._update_cables()

    def _cancel_reroute(self):
        self._reroute_mode = False
        self._reroute_cable = None
        self._reroute_end = ""
        if self._reroute_drag_line and self._reroute_drag_line.scene():
            self._scene.removeItem(self._reroute_drag_line)
        self._reroute_drag_line = None
        if not self._connect_mode:
            self._view.unsetCursor()

    # ── Cable delete ──────────────────────────────────────────────────────────

    def _delete_cable(self, cable: Cable):
        if cable in self.project.cables:
            self.project.cables.remove(cable)
            self.on_change()
            self._update_cables()
