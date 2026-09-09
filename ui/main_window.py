"""Main application window: project tree, tabbed center, log dock."""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QLabel,
    QVBoxLayout,
    QTabWidget,
    QDockWidget,
    QPlainTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QAction,
    QMenu,
)
from PyQt5.QtCore import Qt

from app.settings import Settings
from app.project import Project


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
        placeholder = QTreeWidgetItem(["No project open"])
        self.project_tree.addTopLevelItem(placeholder)

        dock = QDockWidget("Projects", self)
        dock.setWidget(self.project_tree)
        dock.setObjectName("projects_dock")
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.project_dock = dock

    def _build_center_tabs(self) -> None:
        self.tabs = QTabWidget()
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        label = QLabel(
            "Welcome to GENESIS Studio.\n\n"
            "Use File > New Project to set up a coarse-grained simulation."
        )
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.tabs.addTab(welcome, "Welcome")
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

        tools_menu: QMenu = menubar.addMenu("&Tools")
        health_check = QAction("&Health Check...", self)
        health_check.triggered.connect(self._on_health_check)
        tools_menu.addAction(health_check)

    # -- actions -------------------------------------------------------
    def _on_new_project(self) -> None:
        from PyQt5.QtWidgets import QDialog
        from ui.wizard_new_project import NewProjectWizard
        from app.project_creation import local_directory_for

        wizard = NewProjectWizard(self.settings, self)
        if wizard.exec_() == QDialog.Accepted:
            name = wizard.review_page.name_edit.text().strip()
            if name:
                local_dir = local_directory_for(self.settings, name)
                self.settings.add_recent_project(local_dir)
                self.settings.save()
                try:
                    project = Project.load(local_dir)
                except (OSError, ValueError):
                    project = None
                if project is not None:
                    self.open_project(project, local_dir)

    def open_project(self, project: Project, local_directory: str) -> None:
        from ui.tab_files import FilesTab
        from ui.tab_run import RunTab

        self.current_project = project
        self.current_project_dir = local_directory

        while self.tabs.count():
            self.tabs.removeTab(0)

        self.files_tab = FilesTab(project, local_directory)
        self.tabs.addTab(self.files_tab, "Files")

        self.run_tab = RunTab(project, local_directory, self.settings)
        self.tabs.addTab(self.run_tab, "Run")

        self.project_tree.clear()
        root = QTreeWidgetItem([project.name])
        self.project_tree.addTopLevelItem(root)
        root.setExpanded(True)

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
