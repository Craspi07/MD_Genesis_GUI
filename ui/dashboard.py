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

from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QColor, QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.project import Project
from app.project_management import delete_project, rename_project
from app.settings import Settings
from app.wsl import WslBridge

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


class DeleteProjectWorker(QObject):
    """Runs delete_project() off the GUI thread -- it's a blocking WSL
    `rm -rf` call (see app/project_management.py)."""

    finished = pyqtSignal(bool, str)

    def __init__(self, bridge: WslBridge, project: Project):
        super().__init__()
        self.bridge = bridge
        self.project = project

    def run(self) -> None:
        result = delete_project(self.bridge, self.project)
        self.finished.emit(result.success, result.message)


class RenameProjectWorker(QObject):
    """Runs rename_project() off the GUI thread -- it's several blocking
    WSL calls (mv the directory, list + mv its prefixed files, regenerate
    run.inp)."""

    finished = pyqtSignal(bool, str, str)  # success, message, new_local_directory

    def __init__(self, bridge: WslBridge, settings: Settings, project: Project, new_name: str):
        super().__init__()
        self.bridge = bridge
        self.settings = settings
        self.project = project
        self.new_name = new_name

    def run(self) -> None:
        result = rename_project(self.bridge, self.settings, self.project, self.new_name)
        self.finished.emit(result.success, result.message, result.new_local_directory or "")


class ProjectDashboard(QWidget):
    """A row whose project.json can't be loaded (moved/deleted folder,
    corrupt file) is shown as "missing / unreadable" rather than silently
    dropped from the list -- a project vanishing without explanation is
    exactly the kind of workflow confusion this dashboard exists to fix.
    """

    project_open_requested = pyqtSignal(object, str)  # Project, local_directory
    project_deleted = pyqtSignal(str)  # local_directory of the deleted project
    project_renamed = pyqtSignal(str, object, str)  # old_local_directory, Project, new_local_directory

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._rows: List[Optional[Project]] = []  # index-aligned with the table's rows
        self._thread: Optional[QThread] = None
        self._worker: Optional[QObject] = None
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

        self.rename_button = QPushButton("Rename...")
        self.rename_button.clicked.connect(self._on_rename_selected)
        button_row.addWidget(self.rename_button)

        self.delete_button = QPushButton("Delete...")
        self.delete_button.clicked.connect(self._on_delete_selected)
        button_row.addWidget(self.delete_button)

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

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.delete_button.setEnabled(enabled)
        self.rename_button.setEnabled(enabled)
        self.new_project_button.setEnabled(enabled)

    def _cleanup_thread(self) -> None:
        self._thread = None
        self._worker = None
        self._set_actions_enabled(True)

    def _on_delete_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        project = self._rows[row]
        path = self.table.item(row, PATH_COLUMN).text()
        if project is None:
            # Nothing on disk to touch via project_management -- just drop
            # the stale list entry, same as "Remove From List".
            self._on_remove_selected()
            return
        if self._thread is not None:
            self.status_label.setText("An operation is already in progress.")
            return

        confirm = QMessageBox.question(
            self,
            "Delete project",
            f"Permanently delete '{project.name}' and all its files at:\n\n"
            f"{project.directory}\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        bridge = WslBridge(distro=self.settings.distro)
        self.status_label.setText(f"Deleting '{project.name}'...")
        self._set_actions_enabled(False)
        self._thread = QThread(self)
        self._worker = DeleteProjectWorker(bridge, project)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(lambda success, message: self._on_delete_finished(success, message, path))
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_delete_finished(self, success: bool, message: str, path: str) -> None:
        self.status_label.setText(message)
        if success:
            if path in self.settings.recent_projects:
                self.settings.recent_projects.remove(path)
                self.settings.save()
            self.project_deleted.emit(path)
        self.refresh()

    def _on_rename_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        project = self._rows[row]
        path = self.table.item(row, PATH_COLUMN).text()
        if project is None:
            self.status_label.setText("Can't rename: project.json is missing or unreadable.")
            return
        if self._thread is not None:
            self.status_label.setText("An operation is already in progress.")
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Rename project",
            "New project name. This renames the project folder and every generated\n"
            "file, then regenerates run.inp -- any manual edits to run.inp are lost:",
            text=project.name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == project.name:
            return

        bridge = WslBridge(distro=self.settings.distro)
        self.status_label.setText(f"Renaming '{project.name}' to '{new_name}'...")
        self._set_actions_enabled(False)
        self._thread = QThread(self)
        self._worker = RenameProjectWorker(bridge, self.settings, project, new_name)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(
            lambda success, message, new_dir: self._on_rename_finished(success, message, path, project, new_dir)
        )
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_rename_finished(
        self, success: bool, message: str, old_path: str, project: Project, new_local_directory: str
    ) -> None:
        self.status_label.setText(message)
        if success:
            if old_path in self.settings.recent_projects:
                self.settings.recent_projects[self.settings.recent_projects.index(old_path)] = new_local_directory
            else:
                self.settings.recent_projects.insert(0, new_local_directory)
            if self.settings.last_project == old_path:
                self.settings.last_project = new_local_directory
            self.settings.save()
            self.project_renamed.emit(old_path, project, new_local_directory)
        self.refresh()
