import json
from datetime import date
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QFileDialog,
    QMessageBox, QInputDialog, QLabel, QDialog, QFormLayout,
    QLineEdit, QTextEdit, QDialogButtonBox,
)
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtCore import Qt

from app.models.project import Project
from app.storage.project_file import load_project, save_project, EXTENSION
from app.storage import recent_files as _rf
from app.views.cable_editor import CableEditor
from app.views.patch_panel_view import PatchPanelView
from app.views.daq_mapper import DaqMapper
from app.views.signal_tracer_view import SignalTracerView
from app.views.system_overview import SystemOverview

_UNDO_MAX = 50


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.current_path: Path | None = None
        self.dirty = False
        self._undo_stack: list[str] = []
        self._redo_stack: list[str] = []
        self._last_snapshot = ""

        self.setWindowTitle("Winder")
        self.resize(1200, 800)

        self._build_menu()
        self._build_tabs()
        self._build_status()
        self._last_snapshot = self._snapshot()
        self._refresh_status()

    # ── Snapshot helpers ──────────────────────────────────────────────────────

    def _snapshot(self) -> str:
        return json.dumps(self.project.to_dict())

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        file_menu.addAction(self._action("&New", self._new, QKeySequence.StandardKey.New))
        file_menu.addAction(self._action("&Open…", self._open, QKeySequence.StandardKey.Open))
        file_menu.addAction(self._action("&Save", self._save, QKeySequence.StandardKey.Save))
        file_menu.addAction(self._action("Save &As…", self._save_as, QKeySequence("Ctrl+Shift+S")))
        file_menu.addSeparator()
        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._refresh_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self._action("Project &Properties…", self._project_properties))
        file_menu.addSeparator()
        file_menu.addAction(self._action("E&xit", self.close, QKeySequence.StandardKey.Quit))

        edit_menu = mb.addMenu("&Edit")
        self._undo_action = self._action("&Undo", self._undo, QKeySequence.StandardKey.Undo)
        self._redo_action = self._action("&Redo", self._redo, QKeySequence.StandardKey.Redo)
        self._undo_action.setEnabled(False)
        self._redo_action.setEnabled(False)
        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)

        export_menu = mb.addMenu("&Export")
        export_menu.addAction(self._action("Cable Schedule (Excel)…", lambda: self._export("cable_excel")))
        export_menu.addAction(self._action("Cable Schedule (CSV)…", lambda: self._export("cable_csv")))
        export_menu.addSeparator()
        export_menu.addAction(self._action("Patch Panel Schedule (Excel)…", lambda: self._export("panel_excel")))
        export_menu.addSeparator()
        export_menu.addAction(self._action("DAQ Channel List (Excel)…", lambda: self._export("daq_excel")))
        export_menu.addSeparator()
        export_menu.addAction(self._action("Full System Report (PDF)…", lambda: self._export("pdf")))
        export_menu.addSeparator()
        export_menu.addAction(self._action("System Overview (PNG/SVG)…", lambda: self._export("overview_image")))

        help_menu = mb.addMenu("&Help")
        help_menu.addAction(self._action("&About", self._about))

    def _refresh_recent_menu(self):
        self._recent_menu.clear()
        recent = _rf.load_recent()
        if not recent:
            act = self._recent_menu.addAction("(none)")
            act.setEnabled(False)
        else:
            for path in recent:
                act = self._recent_menu.addAction(Path(path).name)
                act.setToolTip(path)
                act.triggered.connect(lambda checked, p=path: self._open_path(p))
            self._recent_menu.addSeparator()
            self._recent_menu.addAction("Clear Recent", _rf.clear_recent)

    def _action(self, label: str, slot, shortcut=None) -> QAction:
        act = QAction(label, self)
        act.triggered.connect(slot)
        if shortcut:
            act.setShortcut(shortcut)
        return act

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.overview = SystemOverview(self.project, self._mark_dirty)
        self.cable_editor = CableEditor(self.project, self._mark_dirty)
        self.panel_view = PatchPanelView(self.project, self._mark_dirty)
        self.daq_mapper = DaqMapper(self.project, self._mark_dirty)
        self.tracer_view = SignalTracerView(self.project)

        self.tabs.addTab(self.overview, "System Overview")
        self.tabs.addTab(self.cable_editor, "Cables")
        self.tabs.addTab(self.panel_view, "Patch Panels")
        self.tabs.addTab(self.daq_mapper, "DAQ System")
        self.tabs.addTab(self.tracer_view, "Signal Tracer")
        self.tabs.currentChanged.connect(self._on_tab_change)
        self.setCentralWidget(self.tabs)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status(self):
        sb = QStatusBar()
        self.status_file = QLabel()
        self.status_counts = QLabel()
        sb.addWidget(self.status_file)
        sb.addPermanentWidget(self.status_counts)
        self.setStatusBar(sb)

    def _refresh_status(self):
        label = str(self.current_path.name) if self.current_path else "Untitled"
        if self.dirty:
            label += " *"
        self.status_file.setText(label)
        self.status_counts.setText(
            f"cables: {len(self.project.cables)}"
            f"  panels: {len(self.project.patch_panels)}"
            f"  crates: {len(self.project.crates)}"
        )

    # ── Dirty / undo / redo ───────────────────────────────────────────────────

    def _mark_dirty(self):
        self._undo_stack.append(self._last_snapshot)
        if len(self._undo_stack) > _UNDO_MAX:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._last_snapshot = self._snapshot()
        self._undo_action.setEnabled(True)
        self._redo_action.setEnabled(False)
        self.dirty = True
        self._refresh_status()

    def _undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        snap = self._undo_stack.pop()
        self._last_snapshot = snap
        self.project = Project.from_dict(json.loads(snap))
        self._reload_views()
        self.dirty = True
        self._refresh_status()
        self._undo_action.setEnabled(bool(self._undo_stack))
        self._redo_action.setEnabled(True)

    def _redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        snap = self._redo_stack.pop()
        self._last_snapshot = snap
        self.project = Project.from_dict(json.loads(snap))
        self._reload_views()
        self.dirty = True
        self._refresh_status()
        self._undo_action.setEnabled(True)
        self._redo_action.setEnabled(bool(self._redo_stack))

    def _reload_views(self):
        self.overview.set_project(self.project)
        self.cable_editor.set_project(self.project)
        self.panel_view.set_project(self.project)
        self.daq_mapper.set_project(self.project)
        self.tracer_view.set_project(self.project)

    def _reload_all(self):
        self._reload_views()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._last_snapshot = self._snapshot()
        self._undo_action.setEnabled(False)
        self._redo_action.setEnabled(False)
        self.dirty = False
        self._refresh_status()

    def _on_tab_change(self, index: int):
        widget = self.tabs.widget(index)
        if hasattr(widget, "refresh"):
            widget.refresh()

    # ── File actions ──────────────────────────────────────────────────────────

    def _new(self):
        if not self._confirm_discard():
            return
        name, ok = QInputDialog.getText(self, "New Project", "Project name:")
        if not ok or not name.strip():
            return
        self.project = Project(name=name.strip())
        self.current_path = None
        self._reload_all()

    def _open(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", f"Winder Files (*{EXTENSION})"
        )
        if path:
            self._open_path(path)

    def _open_path(self, path: str):
        try:
            self.project = load_project(path)
            self.current_path = Path(path)
            self._reload_all()
            _rf.add_recent(path)
            self._refresh_recent_menu()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")

    def _save(self):
        if self.current_path is None:
            self._save_as()
        else:
            try:
                self.project.modified = date.today().isoformat()
                save_project(self.project, self.current_path)
                self.dirty = False
                self._last_snapshot = self._snapshot()
                self._refresh_status()
                _rf.add_recent(str(self.current_path))
                self._refresh_recent_menu()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save:\n{e}")

    def _save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", self.project.name + EXTENSION,
            f"Winder Files (*{EXTENSION})"
        )
        if not path:
            return
        self.current_path = Path(path)
        self._save()

    # ── Export ────────────────────────────────────────────────────────────────

    def _export(self, kind: str):
        from app.storage.exporter import (
            export_cable_excel, export_cable_csv,
            export_panel_excel, export_daq_excel, export_pdf
        )
        if kind == "overview_image":
            path, _ = QFileDialog.getSaveFileName(
                self, "Export Overview Image", "",
                "PNG Image (*.png);;SVG Image (*.svg)"
            )
            if not path:
                return
            self.tabs.setCurrentWidget(self.overview)
            try:
                self.overview.export_image(path)
                QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))
            return

        handlers = {
            "cable_excel": ("Save Cable Schedule",    "Excel (*.xlsx)", export_cable_excel),
            "cable_csv":   ("Save Cable Schedule",    "CSV (*.csv)",    export_cable_csv),
            "panel_excel": ("Save Panel Schedule",    "Excel (*.xlsx)", export_panel_excel),
            "daq_excel":   ("Save DAQ Channel List",  "Excel (*.xlsx)", export_daq_excel),
            "pdf":         ("Save System Report",     "PDF (*.pdf)",    export_pdf),
        }
        title, filt, func = handlers[kind]
        path, _ = QFileDialog.getSaveFileName(self, title, "", filt)
        if not path:
            return
        try:
            func(self.project, path)
            QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ── Project Properties ────────────────────────────────────────────────────

    def _project_properties(self):
        dlg = _ProjectPropertiesDialog(self.project, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mark_dirty()
            self._refresh_status()

    # ── About ─────────────────────────────────────────────────────────────────

    def _about(self):
        QMessageBox.about(
            self, "About Winder",
            "Winder\nCable & DAQ Labeling Tool\n\nFor nuclear data acquisition systems."
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
        )
        return reply == QMessageBox.StandardButton.Discard

    def closeEvent(self, event):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()


class _ProjectPropertiesDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Project Properties")
        self.setMinimumWidth(380)
        layout = QFormLayout(self)

        self._name = QLineEdit(project.name)
        self._author = QLineEdit(project.author)
        self._revision = QLineEdit(project.revision)
        self._description = QTextEdit(project.description)
        self._description.setMaximumHeight(80)

        layout.addRow("Name:", self._name)
        layout.addRow("Author:", self._author)
        layout.addRow("Revision:", self._revision)
        layout.addRow("Description:", self._description)

        info = QLabel(
            f"Created: {project.created}   Modified: {project.modified or '—'}"
        )
        info.setStyleSheet("color: #666; font-size: 10px;")
        layout.addRow(info)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _accept(self):
        self.project.name = self._name.text().strip() or self.project.name
        self.project.author = self._author.text().strip()
        self.project.revision = self._revision.text().strip()
        self.project.description = self._description.toPlainText().strip()
        self.accept()
