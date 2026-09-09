"""Wizard page 5: review + create project (F2.5)."""
from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QLabel,
    QProgressBar,
)

from app.project import Project
from app.project_creation import (
    local_directory_for,
    create_project_files,
    run_cg_tool_pipeline,
    generate_project_control_file,
)
from app.settings import Settings
from app.wsl import WslBridge


class ProjectCreationWorker(QObject):
    finished = pyqtSignal(bool, str)

    def __init__(self, bridge: WslBridge, project: Project, local_directory: str, source_pdb_path: Optional[str]):
        super().__init__()
        self.bridge = bridge
        self.project = project
        self.local_directory = local_directory
        self.source_pdb_path = source_pdb_path

    def run(self) -> None:
        try:
            create_project_files(self.project, self.local_directory, self.source_pdb_path)
            result = run_cg_tool_pipeline(self.bridge, self.project, self.local_directory)
            if not result.success:
                self.finished.emit(False, result.message)
                return
            generate_project_control_file(self.project, self.local_directory)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            self.finished.emit(False, str(exc))
            return
        self.finished.emit(True, "Project created.")


class ReviewPage(QWizardPage):
    def __init__(self, settings: Settings, build_project: Callable[[str], Project], parent=None):
        super().__init__(parent)
        self.setTitle("Review")
        self.setSubTitle("Confirm and create the project.")
        self.settings = settings
        self._build_project = build_project
        self._created = False
        self._thread: Optional[QThread] = None
        self._worker: Optional[ProjectCreationWorker] = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("my_protein")
        self.name_edit.textChanged.connect(self._refresh_summary)
        form.addRow("Project name:", self.name_edit)
        layout.addLayout(form)

        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        layout.addWidget(self.summary)

        self.create_button = QPushButton("Create Project")
        self.create_button.clicked.connect(self._on_create)
        layout.addWidget(self.create_button)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def initializePage(self) -> None:
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        name = self.name_edit.text().strip() or "<unnamed>"
        try:
            project = self._build_project(name)
        except Exception as exc:  # noqa: BLE001
            self.summary.setPlainText(f"Could not build project summary: {exc}")
            return
        local_dir = local_directory_for(self.settings, name)
        lines = [
            f"Name: {project.name}",
            f"Model: {project.model_type.value}",
            f"Input: {project.input_mode.value}",
            f"Temperature: {project.parameters.temperature_k} K",
            f"Steps: {project.parameters.n_steps}",
            f"Timestep: {project.parameters.timestep_fs} fs",
            f"Engine: {project.resources.engine.value}",
            f"MPI ranks x OMP threads: {project.resources.mpi_ranks} x {project.resources.omp_threads}",
            f"Project directory: {local_dir}",
        ]
        if project.model_type.value == "hps_condensate":
            lines.append(f"Copies: {project.parameters.n_copies}")
        self.summary.setPlainText("\n".join(lines))

    def _on_create(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.status_label.setText("Enter a project name first.")
            return
        project = self._build_project(name)
        local_dir = local_directory_for(self.settings, name)
        bridge = WslBridge(distro=self.settings.distro)
        source_pdb = getattr(self, "source_pdb_path", None)

        self.create_button.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("Creating project: running CG-tool inside WSL...")

        self._thread = QThread(self)
        self._worker = ProjectCreationWorker(bridge, project, local_dir, source_pdb)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def _cleanup(self) -> None:
        self._thread = None
        self._worker = None
        self.create_button.setEnabled(True)
        self.progress.setVisible(False)

    def _on_finished(self, success: bool, message: str) -> None:
        self._created = success
        self.status_label.setText(message)
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._created
