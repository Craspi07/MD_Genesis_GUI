"""Project dashboard: home screen listing every recent project with its
model type, last run status, and last-modified time.

Replaces the old static "Welcome to GENESIS Studio" label, which gave no
visibility into existing projects and forced opening one at a time via
File > New Project or manual navigation. See ROADMAP.md Phase 1.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.project import Project
from app.settings import Settings

STATUS_COLORS = {
    "running": "#2b7de9",
    "finished": "#2e9e4f",
    "failed": "#d9433f",
    "stopped": "#b8860b",
    "not_started": "#808080",
}
MISSING_COLOR = "#d9433f"

COLUMN_HEADERS = ["Project", "Model", "Status", "Last modified", "Path"]
PATH_COLUMN = 4


class ProjectDashboard(QWidget):
    """A row whose project.json can't be loaded (moved/deleted folder,
    corrupt file) is shown as "missing / unreadable" rather than silently
    dropped from the list -- a project vanishing without explanation is
    exactly the kind of workflow confusion this dashboard exists to fix.
    """

    project_open_requested = pyqtSignal(object, str)  # Project, local_directory

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._rows: List[Optional[Project]] = []  # index-aligned with the table's rows
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>GENESIS Studio</h2>"))
        layout.addWidget(QLabel("Recent projects — double-click a row to open it."))

        self.table = QTableWidget(0, len(COLUMN_HEADERS))
        self.table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnHidden(PATH_COLUMN, True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table, stretch=1)

        button_row = QHBoxLayout()
        self.new_project_button = QPushButton("New Project...")
        button_row.addWidget(self.new_project_button)

        self.open_button = QPushButton("Open Selected")
        self.open_button.clicked.connect(self._on_open_selected)
        button_row.addWidget(self.open_button)

        self.open_folder_button = QPushButton("Open Containing Folder")
        self.open_folder_button.clicked.connect(self._on_open_folder)
        button_row.addWidget(self.open_folder_button)

        self.remove_button = QPushButton("Remove From List")
        self.remove_button.clicked.connect(self._on_remove_selected)
        button_row.addWidget(self.remove_button)

        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    # -- data ----------------------------------------------------------------
    def refresh(self) -> None:
        paths = list(self.settings.recent_projects)
        self.table.setRowCount(len(paths))
        self._rows = []
        for row, path in enumerate(paths):
            project = self._load_or_none(path)
            self._rows.append(project)
            self._fill_row(row, path, project)

    @staticmethod
    def _load_or_none(path: str) -> Optional[Project]:
        try:
            return Project.load(path)
        except (OSError, ValueError):
            return None

    def _fill_row(self, row: int, path: str, project: Optional[Project]) -> None:
        if project is None:
            self.table.setItem(row, 0, QTableWidgetItem(Path(path).name or path))
            self.table.setItem(row, 1, QTableWidgetItem("--"))
            status_item = QTableWidgetItem("missing / unreadable")
            status_item.setForeground(QColor(MISSING_COLOR))
            self.table.setItem(row, 2, status_item)
            self.table.setItem(row, 3, QTableWidgetItem("--"))
            self.table.setItem(row, PATH_COLUMN, QTableWidgetItem(path))
            return

        self.table.setItem(row, 0, QTableWidgetItem(project.name))
        self.table.setItem(row, 1, QTableWidgetItem(project.model_type.value))
        status_item = QTableWidgetItem(project.last_run_status)
        color = STATUS_COLORS.get(project.last_run_status)
        if color:
            status_item.setForeground(QColor(color))
        self.table.setItem(row, 2, status_item)
        self.table.setItem(row, 3, QTableWidgetItem(self._last_modified(path)))
        self.table.setItem(row, PATH_COLUMN, QTableWidgetItem(path))

    @staticmethod
    def _last_modified(path: str) -> str:
        try:
            mtime = (Path(path) / "project.json").stat().st_mtime
        except OSError:
            return "--"
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

    # -- actions ---------------------------------------------------------------
    def _selected_row(self) -> Optional[int]:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return rows[0].row()

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        self._open_row(row)

    def _on_open_selected(self) -> None:
        row = self._selected_row()
        if row is not None:
            self._open_row(row)

    def _open_row(self, row: int) -> None:
        project = self._rows[row]
        path = self.table.item(row, PATH_COLUMN).text()
        if project is None:
            self.status_label.setText(f"Can't open '{path}': project.json is missing or unreadable.")
            return
        self.status_label.setText("")
        self.project_open_requested.emit(project, path)

    def _on_open_folder(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        path = self.table.item(row, PATH_COLUMN).text()
        if not Path(path).exists():
            self.status_label.setText(f"Folder does not exist: {path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_remove_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        path = self.table.item(row, PATH_COLUMN).text()
        if path in self.settings.recent_projects:
            self.settings.recent_projects.remove(path)
            self.settings.save()
        self.refresh()
