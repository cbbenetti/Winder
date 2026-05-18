from typing import Callable

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsLineItem,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox,
    QDialogButtonBox, QMenu,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QSizeF
from PyQt6.QtGui import (
    QColor, QPen, QBrush, QFont, QPainterPath, QPainter, QKeyEvent,
)

from app.models.project import Project
from app.models.cable import Cable, CABLE_TYPES, SIGNAL_TYPES
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
PORT_H   = 22
STUB_LEN = 60
CONN_R   = 8
EAR_W    = 14   # rack ear width

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


# ── Resize handle ─────────────────────────────────────────────────────────────

class _ResizeHandle(QGraphicsRectItem):
    """Drag handle pinned to a block corner or edge for resizing."""
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
    """Clickable connector dot on a port or DAQ channel."""

    def __init__(self, endpoint_id: str, signal_type: str):
        r = CONN_R
        super().__init__(-r, -r, r * 2, r * 2)
        self.endpoint_id = endpoint_id
        self.signal_type = signal_type
        self.setBrush(QBrush(C_CONN_IDLE))
        self.setPen(QPen(C_BORDER, 2))
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
        self.setPen(QPen(C_CONN_SEL if on else C_BORDER, 2))


# ── Patch panel block ─────────────────────────────────────────────────────────

class PanelBlock(QGraphicsRectItem):
    """Movable, resizable patch panel drawn via QPainter."""

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

    # ── Public resize API ──────────────────────────────────────────────────────

    def set_size(self, w: float, h: float):
        self._display_w = w
        self._display_h = h
        self.setRect(0, 0, w, h)
        self._rebuild_connectors()
        self._overview._update_cables()
        self.update()

    # ── Connector management ───────────────────────────────────────────────────

    def _rebuild_connectors(self):
        for child in list(self.childItems()):
            if isinstance(child, ConnectorItem):
                self._overview._conn.pop(child.endpoint_id, None)
                child.setParentItem(None)
                if child.scene():
                    child.scene().removeItem(child)

        cols = max(self._panel.cols, 1)
        rows = max(self._panel.rows, 1)
        port_h = max((self._display_h - HEADER_H) / rows, 8.0)

        for row in range(rows):
            for col in range(cols):
                port = self._panel.port_at(row, col)
                if port is None:
                    port_id = f"{self._panel.id}-{chr(65 + row)}{col + 1:02d}"
                    port = PatchPort(id=port_id, row=row, col=col)
                    self._panel.ports.append(port)
                if port.id:
                    sig = port.signal_type or "Other"
                    conn = ConnectorItem(port.id, sig)
                    conn.setPos(self._display_w, HEADER_H + row * port_h + port_h / 2)
                    conn.setParentItem(self)
                    self._overview._conn[port.id] = conn

        self._handle.setPos(self._display_w, self._display_h)

    # ── Qt overrides ───────────────────────────────────────────────────────────

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
        port_w = w / cols
        port_h = max((h - HEADER_H) / rows, 8.0)

        # Header bar
        painter.fillRect(QRectF(0, 0, w, HEADER_H), C_PANEL_HDR)
        painter.setPen(QPen(C_WHITE))
        painter.setFont(_font(8, True))
        painter.drawText(
            QRectF(6, 0, w - 12, HEADER_H), Qt.AlignmentFlag.AlignVCenter,
            _elide(f"{self._panel.id}  —  {self._panel.name}", 32),
        )

        # Port grid
        for row in range(rows):
            for col in range(cols):
                port = self._panel.port_at(row, col)
                sig = (port.signal_type if port else None) or "Other"
                fill = QColor(SIGNAL_COLORS.get(sig, SIGNAL_COLORS["Other"]))
                px, py = col * port_w, HEADER_H + row * port_h
                painter.fillRect(QRectF(px, py, port_w, port_h), fill)
                painter.setPen(QPen(C_BORDER, 0.5))
                painter.drawRect(QRectF(px, py, port_w, port_h))
                if port:
                    lbl = port.label or (port.id[-4:] if port.id else "")
                    painter.setPen(QPen(QColor("#212121")))
                    painter.setFont(_font(max(5, min(7, int(port_w / 6)))))
                    painter.drawText(
                        QRectF(px + 1, py + 1, port_w - 2, port_h - 2),
                        Qt.AlignmentFlag.AlignCenter, _elide(lbl, 5),
                    )

        # Outer border
        painter.setPen(QPen(C_RACK_EDGE, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(0, 0, w, h))


# ── DAQ crate block ───────────────────────────────────────────────────────────

class CrateBlock(QGraphicsRectItem):
    """Movable, width-resizable DAQ crate block drawn via QPainter."""

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
        self._rebuild_connectors()

    # ── Public resize API ──────────────────────────────────────────────────────

    def set_width(self, w: float):
        self._display_w = w
        h = self._content_h(self._crate)
        self._display_h = h
        self.setRect(0, 0, w, h)
        self._rebuild_connectors()
        self._overview._update_cables()
        self.update()

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _content_h(crate: DaqCrate) -> float:
        h = float(HEADER_H)
        for slot in crate.slots:
            h += SLOT_H
            if slot.module:
                h += MODULE_H + len(slot.module.channels) * CHAN_H
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
                cy += MODULE_H
                for ch in slot.module.channels:
                    if ch.id:
                        linked = (self._overview.project.cable_by_id(ch.cable_id)
                                  if ch.cable_id else None)
                        sig = linked.signal_type if linked else "Other"
                        conn = ConnectorItem(ch.id, sig)
                        conn.setPos(0.0, cy + CHAN_H / 2)
                        conn.setParentItem(self)
                        self._overview._conn[ch.id] = conn
                    cy += CHAN_H

        h = self._content_h(self._crate)
        self._handle.setPos(self._display_w + EAR_W, h / 2)

    # ── Qt overrides ───────────────────────────────────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if hasattr(self, "_overview"):
                self._overview._update_cables()
        return super().itemChange(change, value)

    def boundingRect(self) -> QRectF:
        h = self._content_h(self._crate)
        return QRectF(-EAR_W, 0, self._display_w + EAR_W * 2, h)

    def paint(self, painter: QPainter, option, widget=None):
        w = self._display_w
        h = self._content_h(self._crate)

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

        # Slots, modules, and channels
        cy = float(HEADER_H)
        for slot in self._crate.slots:
            # Slot bar
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
                # Module bar
                mod_color = QColor(mod.color)
                painter.fillRect(QRectF(0, cy, w, MODULE_H), mod_color)
                painter.setPen(QPen(C_WHITE))
                painter.setFont(_font(8, True))
                painter.drawText(
                    QRectF(8, cy, w - 60, MODULE_H), Qt.AlignmentFlag.AlignVCenter,
                    _elide(mod.name or mod.id, 22),
                )
                painter.setFont(_font(7))
                painter.setPen(QPen(QColor("#cfd8dc")))
                painter.drawText(
                    QRectF(w - 70, cy, 66, MODULE_H),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                    f"{mod.module_type}  {len(mod.channels)} ch",
                )
                cy += MODULE_H

                for i, ch in enumerate(mod.channels):
                    fill = C_CHAN_A if i % 2 == 0 else C_CHAN_B
                    painter.fillRect(QRectF(0, cy, w, CHAN_H), fill)
                    painter.setPen(QPen(QColor("#bdbdbd"), 0.5))
                    painter.drawLine(QPointF(0, cy + CHAN_H), QPointF(w, cy + CHAN_H))
                    painter.setFont(_font(7, True))
                    painter.setPen(QPen(QColor("#212121")))
                    painter.drawText(
                        QRectF(6, cy, 22, CHAN_H), Qt.AlignmentFlag.AlignVCenter,
                        f"{ch.channel_number:02d}",
                    )
                    painter.setFont(_font(7))
                    painter.drawText(
                        QRectF(32, cy, 90, CHAN_H), Qt.AlignmentFlag.AlignVCenter,
                        _elide(ch.signal_label, 14),
                    )
                    painter.setPen(QPen(QColor("#546e7a")))
                    painter.drawText(
                        QRectF(130, cy, 90, CHAN_H), Qt.AlignmentFlag.AlignVCenter,
                        _elide(ch.cable_id, 12),
                    )
                    cy += CHAN_H

        # Crate border
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

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.addAction(f"Cable: {self._cable.id}").setEnabled(False)
        menu.addSeparator()
        del_act = menu.addAction("Delete Cable")
        if menu.exec(event.screenPos().toPoint()) == del_act:
            self._overview._delete_cable(self._cable)


# ── Custom view ───────────────────────────────────────────────────────────────

class _SceneView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, overview: "SystemOverview"):
        super().__init__(scene)
        self._ov = overview

    def mousePressEvent(self, event):
        if self._ov._connect_mode and event.button() == Qt.MouseButton.LeftButton:
            sp = self.mapToScene(event.pos())
            self._ov._on_connector_click(self._connector_at(sp), sp)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._ov._connect_mode:
            self._ov._on_drag_move(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape and self._ov._connect_mode:
            self._ov._cancel_drag()
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


# ── New cable dialog ──────────────────────────────────────────────────────────

class _NewCableDialog(QDialog):
    def __init__(self, parent, from_ep: str, to_ep: str,
                 signal_type: str, project: Project):
        super().__init__(parent)
        self.setWindowTitle("Create Cable")
        layout = QFormLayout(self)
        self._id    = QLineEdit(project.next_cable_id())
        self._label = QLineEdit()
        self._from  = QLineEdit(from_ep);  self._from.setReadOnly(True)
        self._to    = QLineEdit(to_ep);    self._to.setReadOnly(True)
        self._type  = QComboBox();         self._type.addItems(CABLE_TYPES)
        self._sig   = QComboBox();         self._sig.addItems(SIGNAL_TYPES)
        idx = self._sig.findText(signal_type)
        if idx >= 0:
            self._sig.setCurrentIndex(idx)
        self._len   = QDoubleSpinBox();    self._len.setRange(0, 9999); self._len.setSuffix(" m")
        self._notes = QLineEdit()
        layout.addRow("Cable ID:",     self._id)
        layout.addRow("Label:",        self._label)
        layout.addRow("From:",         self._from)
        layout.addRow("To:",           self._to)
        layout.addRow("Cable Type:",   self._type)
        layout.addRow("Signal Type:",  self._sig)
        layout.addRow("Length:",       self._len)
        layout.addRow("Notes:",        self._notes)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
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
    """Home tab: visual rack diagram with movable/resizable blocks and
    interactive cable drawing."""

    def __init__(self, project: Project, on_change: Callable = None):
        super().__init__()
        self.project = project
        self.on_change = on_change or (lambda: None)
        # persistent layout: "panel:PP01" / "crate:CRATE01" → {x,y,w,h}
        self._layout: dict[str, dict] = {}
        self._blocks: dict[str, QGraphicsRectItem] = {}
        self._conn:   dict[str, ConnectorItem] = {}
        self._cable_items:  list = []
        self._stub_items:   list = []
        self._bundle_items: list = []
        self._connect_mode = False
        self._drag_src: ConnectorItem | None = None
        self._drag_line: QGraphicsLineItem | None = None
        self._build_ui()

    def set_project(self, project: Project):
        self.project = project
        self._layout.clear()
        self.refresh()

    def refresh(self):
        self._save_layout()
        self._cancel_drag()
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
        toolbar.addWidget(btn_refresh)
        toolbar.addWidget(btn_fit)

        self._btn_connect = QPushButton("Connect Mode")
        self._btn_connect.setCheckable(True)
        self._btn_connect.setToolTip(
            "Click a connector (white dot) to start, click another to create a cable.\n"
            "Right-click a cable to delete it.  Escape cancels."
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
            bh = saved.get("h", HEADER_H + panel.rows * PORT_H) if saved \
                else float(HEADER_H + panel.rows * PORT_H)
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

    # ── Cables (incremental update) ───────────────────────────────────────────

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

    def _draw_cables(self):
        for cable in self.project.cables:
            src_c = self._conn.get(cable.from_endpoint)
            dst_c = self._conn.get(cable.to_endpoint)
            if src_c is None or dst_c is None:
                continue
            color = QColor(SIGNAL_COLORS.get(cable.signal_type, SIGNAL_COLORS["Other"]))
            src, dst = src_c.scenePos(), dst_c.scenePos()
            path = QPainterPath(src)
            mid_x = (src.x() + dst.x()) / 2
            path.cubicTo(QPointF(mid_x, src.y()), QPointF(mid_x, dst.y()), dst)
            cp = CablePath(cable, path, color, self)
            self._scene.addItem(cp)
            self._cable_items.append(cp)

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
            src_pts = []
            dst_pts = []
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
            # Fan-out thin lines from average point to each individual connector
            for p in src_pts:
                fan = self._scene.addLine(ax, ay, p.x(), p.y(), QPen(color, 1.5))
                fan.setZValue(4)
                self._bundle_items.append(fan)
            for p in dst_pts:
                fan = self._scene.addLine(bx, by, p.x(), p.y(), QPen(color, 1.5))
                fan.setZValue(4)
                self._bundle_items.append(fan)
        # Fade individual cable paths that belong to a bundle
        for item in self._cable_items:
            if isinstance(item, CablePath) and item._cable.id in bundled_cable_ids:
                item.setOpacity(0.35)

    # ── Connect mode ──────────────────────────────────────────────────────────

    def _toggle_connect_mode(self, on: bool):
        self._connect_mode = on
        if on:
            self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._cancel_drag()
            self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self._view.unsetCursor()

    def _on_connector_click(self, connector: "ConnectorItem | None", scene_pos: QPointF):
        if connector is None:
            return  # ignore misses; Escape cancels
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
        dlg = _NewCableDialog(
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

    def _delete_cable(self, cable: Cable):
        if cable in self.project.cables:
            self.project.cables.remove(cable)
            self.on_change()
            self._update_cables()
