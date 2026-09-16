"""Run tab (F3): start/stop, live progress, and an embedded energy/
temperature plot fed by SimulationRunner's tailed log.
"""
from __future__ import annotations

from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QProgressBar,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
)
from PyQt5.QtCore import Qt

from app.log_parser import CG_SPECIFIC_TERMS
from app.project import Project
from app.runner import SimulationRunner
from app.settings import Settings
from app.wsl import WslBridge
from ui.widgets.mpl_canvas import MplCanvas

PLOTTED_ENERGY_TERMS = ("POTENTIAL_ENE", "TOTAL_ENE")


class RunTab(QWidget):
    def __init__(self, project: Project, local_directory: str, settings: Settings, parent=None):
        super().__init__(parent)
        self.project = project
        self.local_directory = local_directory
        self.settings = settings

        bridge = WslBridge(distro=settings.distro)
        self.runner = SimulationRunner(bridge, project, local_directory)
        self.runner.set_settings(settings)
        self.runner.new_records.connect(self._on_new_records)
        self.runner.status_changed.connect(self._on_status_changed)
        self.runner.raw_output.connect(self._on_raw_output)
        self.runner.error_detected.connect(self._on_error_detected)

        self._steps_seen = []  # (step, cumulative x-index) for the plot x-axis
        self._energy_x: list = []
        self._energy_series: dict = {}

        self._build_ui()

        if project.last_run_status == "running" and project.last_run_pgid:
            self._try_reattach()

    # -- construction ------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("Start (F5)")
        self.start_button.clicked.connect(self._on_start)
        button_row.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop (Esc)")
        self.stop_button.clicked.connect(self._on_stop)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.stop_button)

        self.continue_button = QPushButton("Continue from restart file")
        self.continue_button.clicked.connect(self._on_continue)
        self.continue_button.setEnabled(self._has_restart_file())
        button_row.addWidget(self.continue_button)

        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, max(self.project.parameters.n_steps, 1))
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Not started.")
        layout.addWidget(self.status_label)

        splitter = QSplitter(Qt.Vertical)
        self.canvas = MplCanvas(title="Energy / Temperature", ylabel="value")
        splitter.addWidget(self.canvas)

        self.raw_log_view = QPlainTextEdit()
        self.raw_log_view.setReadOnly(True)
        self.raw_log_view.setMaximumBlockCount(5000)
        splitter.addWidget(self.raw_log_view)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

    def _has_restart_file(self) -> bool:
        return (Path(self.local_directory) / f"{self.project.name}.rst").exists()

    # -- actions -------------------------------------------------------------
    def _on_start(self) -> None:
        self._start_run(is_continuation=False)

    def _start_run(self, is_continuation: bool) -> None:
        self.runner.start(is_continuation=is_continuation)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._reset_plot_state()

    def _on_continue(self) -> None:
        from app.control_file import ControlFileConfig, default_box_size, write_control_file

        rst_name = f"{self.project.name}.rst"
        top_files = list(Path(self.local_directory).glob(f"{self.project.name}*.top"))
        gro_files = list(Path(self.local_directory).glob(f"{self.project.name}*.gro"))
        box_x, box_y, box_z = default_box_size(self.project.model_type, self.project.parameters.box_size_nm)
        config = ControlFileConfig(
            top_file=top_files[0].name if top_files else f"{self.project.name}.top",
            gro_file=gro_files[0].name if gro_files else f"{self.project.name}.gro",
            output_prefix=self.project.name,
            temperature_k=self.project.parameters.temperature_k,
            n_steps=self.project.parameters.n_steps,
            timestep_fs=self.project.parameters.timestep_fs,
            output_frequency=self.project.parameters.output_frequency,
            langevin_friction=self.project.parameters.langevin_friction,
            ensemble=self.project.parameters.ensemble,
            pressure_atm=self.project.parameters.pressure_atm,
            use_position_restraints=self.project.parameters.use_position_restraints,
            position_restraint_force_constant=self.project.parameters.position_restraint_force_constant,
            restart_file=rst_name,
            box_x=box_x,
            box_y=box_y,
            box_z=box_z,
            engine=self.project.resources.engine.value,
        )
        write_control_file(config, self.project.model_type, self.local_directory, filename="run.inp", force=True)
        self._start_run(is_continuation=True)

    def _on_stop(self) -> None:
        reply = QMessageBox.question(
            self,
            "Stop simulation?",
            "This will terminate all MPI ranks for this run. Continue?",
        )
        if reply != QMessageBox.Yes:
            return
        self.runner.stop()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _try_reattach(self) -> None:
        alive = self.runner.reattach(self.project.last_run_pgid)
        if alive:
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status_label.setText("Reattached to a running simulation.")

    # -- runner signal handlers ------------------------------------------------
    def _on_new_records(self, records: list) -> None:
        for record in records:
            x = record.step
            self._energy_x.append(x)
            for term in PLOTTED_ENERGY_TERMS + CG_SPECIFIC_TERMS:
                if term in record.values:
                    self._energy_series.setdefault(term, []).append(record.values[term])
            if "TEMPERATURE" in record.values:
                self._energy_series.setdefault("TEMPERATURE", []).append(record.values["TEMPERATURE"])

        for name, ys in self._energy_series.items():
            xs = self._energy_x[-len(ys):]
            self.canvas.set_series(name, xs, ys)
        self.canvas.rescale_and_draw()

        if records:
            latest = records[-1]
            self.progress_bar.setValue(min(latest.step, self.progress_bar.maximum()))
            summary = self.runner.summary()
            if summary:
                self.summary_label.setText(
                    f"{summary.ns_simulated:.3f} ns simulated, {summary.wall_time_seconds:.0f}s elapsed, "
                    f"{summary.ns_per_day:.2f} ns/day"
                )

    def _reset_plot_state(self) -> None:
        self._energy_x = []
        self._energy_series = {}
        self.canvas.clear()
        self.raw_log_view.clear()

    def _on_status_changed(self, status: str) -> None:
        self.status_label.setText(f"Status: {status}")
        if status in ("finished", "failed"):
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
        if status == "finished":
            summary = self.runner.summary()
            if summary:
                self.summary_label.setText(
                    f"Finished. {summary.ns_simulated:.3f} ns simulated in {summary.wall_time_seconds:.0f}s "
                    f"({summary.ns_per_day:.2f} ns/day)."
                )

    def _on_raw_output(self, text: str) -> None:
        self.raw_log_view.appendPlainText(text.rstrip("\n"))

    def _on_error_detected(self, line: str) -> None:
        self.status_label.setText(f"⚠ {line.strip()}")
