"""Benchmark dialog (F4): run the 4x4/8x2/16x1-style preset sweep on the
current project and optionally apply the fastest one.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QDialogButtonBox,
)

from app.benchmark import run_benchmark, fastest_preset, apply_fastest_preset, BenchmarkResult
from app.project import Project
from app.settings import Settings
from app.wsl import WslBridge


class BenchmarkWorker(QObject):
    finished = pyqtSignal(list)

    def __init__(self, bridge: WslBridge, project: Project, local_directory: str, settings: Settings):
        super().__init__()
        self.bridge = bridge
        self.project = project
        self.local_directory = local_directory
        self.settings = settings

    def run(self) -> None:
        try:
            results = run_benchmark(self.bridge, self.project, self.local_directory, self.settings)
        except Exception as exc:  # noqa: BLE001
            results = [BenchmarkResult(0, 0, None, None, False, str(exc))]
        self.finished.emit(results)


class BenchmarkDialog(QDialog):
    def __init__(self, project: Project, local_directory: str, settings: Settings, parent=None):
        super().__init__(parent)
        self.project = project
        self.local_directory = local_directory
        self.settings = settings
        self.setWindowTitle("Benchmark")
        self.resize(560, 360)

        self._results: List[BenchmarkResult] = []
        self._thread: Optional[QThread] = None
        self._worker: Optional[BenchmarkWorker] = None

        layout = QVBoxLayout(self)

        self.run_button = QPushButton("Run benchmark (2000 steps per preset)")
        self.run_button.clicked.connect(self._on_run)
        layout.addWidget(self.run_button)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["MPI x OMP", "Wall time (s)", "steps/s", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        self.apply_button = QPushButton("Apply fastest preset to project")
        self.apply_button.clicked.connect(self._on_apply)
        self.apply_button.setEnabled(False)
        layout.addWidget(self.apply_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _on_run(self) -> None:
        self.run_button.setEnabled(False)
        self.status_label.setText("Running benchmark presets — this runs each preset to completion inside WSL...")
        self.table.setRowCount(0)

        bridge = WslBridge(distro=self.settings.distro)
        self._thread = QThread(self)
        self._worker = BenchmarkWorker(bridge, self.project, self.local_directory, self.settings)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def _cleanup(self) -> None:
        self.run_button.setEnabled(True)
        self._thread = None
        self._worker = None

    def _on_finished(self, results: List[BenchmarkResult]) -> None:
        self._results = results
        self.table.setRowCount(len(results))
        for row, r in enumerate(results):
            self.table.setItem(row, 0, QTableWidgetItem(f"{r.mpi_ranks} x {r.omp_threads}"))
            self.table.setItem(row, 1, QTableWidgetItem(f"{r.wall_time_seconds:.2f}" if r.wall_time_seconds else "-"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{r.steps_per_second:.2f}" if r.steps_per_second else "-"))
            self.table.setItem(row, 3, QTableWidgetItem("OK" if r.success else f"FAILED: {r.error}"))

        best = fastest_preset(results)
        self.apply_button.setEnabled(best is not None)
        if best:
            self.status_label.setText(f"Fastest: {best.mpi_ranks} x {best.omp_threads} ({best.steps_per_second:.2f} steps/s)")
        else:
            self.status_label.setText("No preset completed successfully.")

    def _on_apply(self) -> None:
        if apply_fastest_preset(self.project, self._results):
            self.status_label.setText(
                f"Applied {self.project.resources.mpi_ranks} x {self.project.resources.omp_threads} to the project."
            )
            self.project.save(self.local_directory)
