from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QHeaderView, QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from app.graph.signal_tracer import trace_path, all_connected
from app.models.project import Project


class SignalTracerView(QWidget):
    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self._build_ui()

    def set_project(self, project: Project):
        self.project = project
        self.path_table.setRowCount(0)
        self.all_table.setRowCount(0)

    def refresh(self):
        pass

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Query bar
        search = QHBoxLayout()
        search.addWidget(QLabel("Start point:"))
        self.query_box = QLineEdit()
        self.query_box.setPlaceholderText("Endpoint name, cable ID, or DAQ channel ID…")
        self.query_box.returnPressed.connect(self._trace)
        search.addWidget(self.query_box)
        btn = QPushButton("Trace")
        btn.clicked.connect(self._trace)
        search.addWidget(btn)
        layout.addLayout(search)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Path table — shows each distinct path to a DAQ endpoint
        path_widget = QWidget()
        pv = QVBoxLayout(path_widget)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(QLabel("Signal Paths (start → DAQ channel):"))
        self.path_table = QTableWidget(0, 2)
        self.path_table.setHorizontalHeaderLabels(["Path", "Via (edges)"])
        self.path_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.path_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.path_table.setAlternatingRowColors(True)
        pv.addWidget(self.path_table)
        splitter.addWidget(path_widget)

        # All-connected table
        all_widget = QWidget()
        av = QVBoxLayout(all_widget)
        av.setContentsMargins(0, 0, 0, 0)
        av.addWidget(QLabel("All connected endpoints:"))
        self.all_table = QTableWidget(0, 2)
        self.all_table.setHorizontalHeaderLabels(["Endpoint / Node", "Via (edge)"])
        self.all_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.all_table.setAlternatingRowColors(True)
        av.addWidget(self.all_table)
        splitter.addWidget(all_widget)

        layout.addWidget(splitter)

    def _trace(self):
        start = self.query_box.text().strip()
        if not start:
            return

        # Paths to DAQ channels
        paths = trace_path(self.project, start)
        self.path_table.setRowCount(0)
        for path in paths:
            nodes = [n for n, _ in path]
            edges = [e for _, e in path if e]
            row = self.path_table.rowCount()
            self.path_table.insertRow(row)
            self.path_table.setItem(row, 0, QTableWidgetItem(" → ".join(nodes)))
            self.path_table.setItem(row, 1, QTableWidgetItem(", ".join(edges)))

        if not paths:
            self.path_table.insertRow(0)
            item = QTableWidgetItem("No DAQ channel path found from this endpoint.")
            item.setForeground(QColor("#888"))
            self.path_table.setItem(0, 0, item)

        # All connected
        connected = all_connected(self.project, start)
        self.all_table.setRowCount(0)
        for node, edge in connected:
            row = self.all_table.rowCount()
            self.all_table.insertRow(row)
            self.all_table.setItem(row, 0, QTableWidgetItem(node))
            self.all_table.setItem(row, 1, QTableWidgetItem(edge))
