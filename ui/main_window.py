"""Main application window: project dashboard, project tree, tabbed
center, log dock.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QDockWidget,
    QPlainTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QAction,
    QMenu,
    QMessageBox,
)
from PyQt5.QtCore import Qt

from app.settings import Settings
from app.project import Project
from ui.dashboard import ProjectDashboard

DASHBOARD_TAB_INDEX = 0
PROJECT_PATH_ROLE = Qt.UserRole


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GENESIS Studio")
        self.resize(1280, 800)

        self.settings = Settings().load()
        self.current_project: Project | None = None
        self.current_project_dir: str | None = None

        self._build_project_tree()
        self._build_center_tabs()
        self._build_log_dock()
        self._build_menu()
        self._restore_layout()

    # -- construction ------------------------------------------------
    def _build_project_tree(self) -> None:
        self.project_tree = QTreeWidget()
        self.project_tree.setHeaderLabel("Projects")
        self.project_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)

        dock = QDockWidget("Projects", self)
        dock.setWidget(self.project_tree)
        dock.setObjectName("projects_dock")
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.project_dock = dock
        self.refresh_project_views()

    def _build_center_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.dashboard = ProjectDashboard(self.settings)
        self.dashboard.new_project_button.clicked.connect(self._on_new_project)
        self.dashboard.project_open_requested.connect(self.open_project)
        self.tabs.addTab(self.dashboard, "Dashboard")
        self.setCentralWidget(self.tabs)

    def _build_log_dock(self) -> None:
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        dock = QDockWidget("Log", self)
        dock.setObjectName("log_dock")
        dock.setWidget(self.log_view)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.log_dock = dock

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu: QMenu = menubar.addMenu("&File")
        new_project = QAction("&New Project...", self)
        new_project.setShortcut("Ctrl+N")
        new_project.triggered.connect(self._on_new_project)
        file_menu.addAction(new_project)

        open_project = QAction("&Open Project...", self)
        open_project.setShortcut("Ctrl+O")
        open_project.triggered.connect(self._on_open_project)
        file_menu.addAction(open_project)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        run_menu: QMenu = menubar.addMenu("&Run")
        self.run_action = QAction("&Run Simulation", self)
        self.run_action.setShortcut("F5")
        self.run_action.triggered.connect(self._on_run_shortcut)
        run_menu.addAction(self.run_action)

        self.stop_action = QAction("&Stop Simulation", self)
        self.stop_action.setShortcut("Esc")
        self.stop_action.triggered.connect(self._on_stop_shortcut)
        run_menu.addAction(self.stop_action)

        run_menu.addSeparator()
        queue_action = QAction("&Queue Projects...", self)
        queue_action.triggered.connect(self._on_queue)
        run_menu.addAction(queue_action)

        tools_menu: QMenu = menubar.addMenu("&Tools")
        health_check = QAction("&Health Check...", self)
        health_check.triggered.connect(self._on_health_check)
        tools_menu.addAction(health_check)

        benchmark_action = QAction("&Benchmark...", self)
        benchmark_action.triggered.connect(self._on_benchmark)
        tools_menu.addAction(benchmark_action)

    # -- actions -------------------------------------------------------
    def _on_new_project(self) -> None:
        from PyQt5.QtWidgets import QDialog
        from ui.wizard_new_project import NewProjectWizard
        from app.project_creation import local_directory_for

        wizard = NewProjectWizard(self.settings, self)
        if wizard.exec_() != QDialog.Accepted:
            return
        name = wizard.review_page.name_edit.text().strip()
        if not name:
            return
        local_dir = local_directory_for(self.settings, name)
        try:
            project = Project.load(local_dir)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Project creation failed",
                f"The project wizard finished, but '{name}' could not be opened "
                f"from {local_dir}:\n\n{exc}",
            )
            return
        self.settings.add_recent_project(local_dir)
        self.settings.save()
        self.refresh_project_views()
        self.open_project(project, local_dir)

    def _on_open_project(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        from app.project_creation import local_projects_root_for

        start_dir = local_projects_root_for(self.settings)
        if not Path(start_dir).exists():
            start_dir = ""
        local_dir = QFileDialog.getExistingDirectory(self, "Open Project", start_dir)
        if not local_dir:
            return
        try:
            project = Project.load(local_dir)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self,
                "Can't open project",
                f"'{local_dir}' doesn't look like a GENESIS Studio project:\n\n{exc}",
            )
            return
        self.settings.add_recent_project(local_dir)
        self.settings.save()
        self.refresh_project_views()
        self.open_project(project, local_dir)

    def open_project(self, project: Project, local_directory: str) -> None:
        from ui.tab_files import FilesTab
        from ui.tab_run import RunTab
        from ui.tab_analysis import AnalysisTab

        self.current_project = project
        self.current_project_dir = local_directory

        while self.tabs.count() > DASHBOARD_TAB_INDEX + 1:
            self.tabs.removeTab(self.tabs.count() - 1)

        self.files_tab = FilesTab(project, local_directory, self.settings)
        self.tabs.addTab(self.files_tab, "Files")

        self.run_tab = RunTab(project, local_directory, self.settings)
        self.run_tab.runner.status_changed.connect(lambda _status: self.refresh_project_views())
        self.tabs.addTab(self.run_tab, "Run")

        self.analysis_tab = AnalysisTab(project, local_directory, self.settings)
        self.tabs.addTab(self.analysis_tab, "Analysis")

        self.tabs.setCurrentWidget(self.files_tab)
        self.refresh_project_views()

    def refresh_project_views(self) -> None:
        """Keep the dashboard tab and the Projects tree in sync with
        Settings.recent_projects and the currently open project's live
        status. Called after project creation, removal, opening, and on
        every run status change so neither view goes stale mid-session.
        """
        if hasattr(self, "dashboard"):
            self.dashboard.refresh()
        self._refresh_project_tree()

    def _refresh_project_tree(self) -> None:
        self.project_tree.clear()
        paths = list(self.settings.recent_projects)
        if not paths:
            placeholder = QTreeWidgetItem(["No projects yet"])
            self.project_tree.addTopLevelItem(placeholder)
            return

        for path in paths:
            try:
                project = Project.load(path)
            except (OSError, ValueError):
                item = QTreeWidgetItem([f"{Path(path).name} (missing)"])
                item.setData(0, PROJECT_PATH_ROLE, path)
                self.project_tree.addTopLevelItem(item)
                continue

            label = f"{project.name}  [{project.last_run_status}]"
            item = QTreeWidgetItem([label])
            item.setData(0, PROJECT_PATH_ROLE, path)
            self.project_tree.addTopLevelItem(item)
            if path == self.current_project_dir:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                item.setExpanded(True)

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, PROJECT_PATH_ROLE)
        if not path:
            return
        try:
            project = Project.load(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Can't open project", f"{path}:\n\n{exc}")
            return
        self.open_project(project, path)

    def _on_run_shortcut(self) -> None:
        if hasattr(self, "run_tab") and self.run_tab.start_button.isEnabled():
            self.run_tab._on_start()

    def _on_stop_shortcut(self) -> None:
        if hasattr(self, "run_tab") and self.run_tab.stop_button.isEnabled():
            self.run_tab._on_stop()

    def _on_health_check(self) -> None:
        from ui.dialog_settings import SettingsDialog

        dialog = SettingsDialog(self.settings, self)
        dialog.exec_()

    def _on_benchmark(self) -> None:
        if self.current_project is None or self.current_project_dir is None:
            return
        from ui.dialog_benchmark import BenchmarkDialog

        dialog = BenchmarkDialog(self.current_project, self.current_project_dir, self.settings, self)
        dialog.exec_()

    def _on_queue(self) -> None:
        from ui.dialog_queue import QueueDialog

        dialog = QueueDialog(self.settings, self.settings.recent_projects, self)
        dialog.exec_()

    # -- layout persistence --------------------------------------------
    def _restore_layout(self) -> None:
        if self.settings.window_geometry:
            self.restoreGeometry(self.settings.window_geometry)
        if self.settings.window_state:
            self.restoreState(self.settings.window_state)

    def closeEvent(self, event) -> None:
        self.settings.window_geometry = bytes(self.saveGeometry())
        self.settings.window_state = bytes(self.saveState())
        self.settings.save()
        super().closeEvent(event)
