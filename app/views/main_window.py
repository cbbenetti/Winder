from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QFileDialog,
    QMessageBox, QInputDialog, QLabel
)
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtCore import Qt

from app.models.project import Project
from app.storage.project_file import load_project, save_project, EXTENSION
from app.views.cable_editor import CableEditor
from app.views.patch_panel_view import PatchPanelView
from app.views.daq_mapper import DaqMapper
from app.views.signal_tracer_view import SignalTracerView
from app.views.system_overview import SystemOverview


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.current_path: Path | None = None
        self.dirty = False

        self.setWindowTitle("Winder")
        self.resize(1200, 800)

        self._build_menu()
        self._build_tabs()
        self._build_status()
        self._refresh_status()

    def _build_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        file_menu.addAction(self._action("&New", self._new, QKeySequence.StandardKey.New))
        file_menu.addAction(self._action("&Open…", self._open, QKeySequence.StandardKey.Open))
        file_menu.addAction(self._action("&Save", self._save, QKeySequence.StandardKey.Save))
        file_menu.addAction(self._action("Save &As…", self._save_as, QKeySequence("Ctrl+Shift+S")))
        file_menu.addSeparator()
        file_menu.addAction(self._action("E&xit", self.close, QKeySequence.StandardKey.Quit))

        export_menu = mb.addMenu("&Export")
        export_menu.addAction(self._action("Cable Schedule (Excel)…", lambda: self._export("cable_excel")))
        export_menu.addAction(self._action("Cable Schedule (CSV)…", lambda: self._export("cable_csv")))
        export_menu.addSeparator()
        export_menu.addAction(self._action("Patch Panel Schedule (Excel)…", lambda: self._export("panel_excel")))
        export_menu.addSeparator()
        export_menu.addAction(self._action("DAQ Channel List (Excel)…", lambda: self._export("daq_excel")))
        export_menu.addSeparator()
        export_menu.addAction(self._action("Full System Report (PDF)…", lambda: self._export("pdf")))

        help_menu = mb.addMenu("&Help")
        help_menu.addAction(self._action("&About", self._about))

    def _action(self, label: str, slot, shortcut=None) -> QAction:
        act = QAction(label, self)
        act.triggered.connect(slot)
        if shortcut:
            act.setShortcut(shortcut)
        return act

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

    def _build_status(self):
        sb = QStatusBar()
        self.status_file = QLabel()
        self.status_counts = QLabel()
        sb.addWidget(self.status_file)
        sb.addPermanentWidget(self.status_counts)
        self.setStatusBar(sb)

    def _refresh_status(self):
        if self.current_path:
            label = str(self.current_path.name)
        else:
            label = "Untitled"
        if self.dirty:
            label += " *"
        self.status_file.setText(label)
        cables = len(self.project.cables)
        panels = len(self.project.patch_panels)
        crates = len(self.project.crates)
        self.status_counts.setText(
            f"cables: {cables}  panels: {panels}  crates: {crates}"
        )

    def _mark_dirty(self):
        self.dirty = True
        self._refresh_status()

    def _on_tab_change(self, index: int):
        widget = self.tabs.widget(index)
        if hasattr(widget, "refresh"):
            widget.refresh()

    def _reload_all(self):
        self.overview.set_project(self.project)
        self.cable_editor.set_project(self.project)
        self.panel_view.set_project(self.project)
        self.daq_mapper.set_project(self.project)
        self.tracer_view.set_project(self.project)
        self.dirty = False
        self._refresh_status()

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
        if not path:
            return
        try:
            self.project = load_project(path)
            self.current_path = Path(path)
            self._reload_all()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")

    def _save(self):
        if self.current_path is None:
            self._save_as()
        else:
            try:
                save_project(self.project, self.current_path)
                self.dirty = False
                self._refresh_status()
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

    def _export(self, kind: str):
        from app.storage.exporter import (
            export_cable_excel, export_cable_csv,
            export_panel_excel, export_daq_excel, export_pdf
        )
        handlers = {
            "cable_excel": ("Save Cable Schedule", "Excel (*.xlsx)", export_cable_excel),
            "cable_csv":   ("Save Cable Schedule", "CSV (*.csv)",   export_cable_csv),
            "panel_excel": ("Save Panel Schedule", "Excel (*.xlsx)", export_panel_excel),
            "daq_excel":   ("Save DAQ Channel List", "Excel (*.xlsx)", export_daq_excel),
            "pdf":         ("Save System Report",  "PDF (*.pdf)",   export_pdf),
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

    def _about(self):
        QMessageBox.about(
            self, "About Winder",
            "Winder\nCable & DAQ Labeling Tool\n\nFor nuclear data acquisition systems."
        )

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
