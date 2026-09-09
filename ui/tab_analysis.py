"""Analysis tab (F5): run GENESIS *_analysis tools, plot results, export
to Excel, and optionally hand the trajectory off to VMD.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Optional

import numpy as np
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QLabel,
    QFileDialog,
)

from app.analysis import (
    ANALYSIS_TOOLS,
    run_analysis,
    parse_two_column_series,
    parse_contact_map,
    AnalysisRunResult,
)
from app.excel_export import AnalysisSeries, AnalysisMatrix, export_to_excel
from app.log_parser import GenesisLogParser
from app.project import Project, ModelType
from app.settings import Settings
from app.wsl import WslBridge
from ui.widgets.mpl_canvas import MplCanvas

# "density" deliberately excluded: mdgenesis.org's density_analysis example
# (mdgenesis.org/examples/density_density_analysis/) confirms its real
# output is a binary CCP4 3D electron-density map (mapfile) plus a .pdb,
# not the two-column z-profile text this dict used to assume -- see
# app/analysis.py's module docstring and DECISIONS.md. It's handled
# separately in _on_analysis_finished rather than through
# parse_two_column_series, which would fail/garbage-parse binary data.
SERIES_ANALYSES = {
    "rmsd": ("Frame", "RMSD (nm)"),
    "rg": ("Frame", "Rg (nm)"),
    "qvalue": ("Frame", "Q-value"),
}


class AnalysisWorker(QObject):
    finished = pyqtSignal(str, str, object, object)  # key, analysis_type, AnalysisRunResult, mode

    def __init__(self, bridge: WslBridge, analysis_type: str, project: Project, local_directory: str, mode: Optional[str]):
        super().__init__()
        self.bridge = bridge
        self.analysis_type = analysis_type
        self.project = project
        self.local_directory = local_directory
        self.mode = mode

    def run(self) -> None:
        key = f"{self.analysis_type}_{self.mode}" if self.mode else self.analysis_type
        try:
            result = run_analysis(self.bridge, self.analysis_type, self.project, self.local_directory, mode=self.mode)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            result = AnalysisRunResult(success=False, output_path=None, log=str(exc))
        self.finished.emit(key, self.analysis_type, result, self.mode)


class AnalysisTab(QWidget):
    def __init__(self, project: Project, local_directory: str, settings: Settings, parent=None):
        super().__init__(parent)
        self.project = project
        self.local_directory = local_directory
        self.settings = settings
        self.bridge = WslBridge(distro=settings.distro)

        self._series_results: Dict[str, AnalysisSeries] = {}
        self._matrix_results: Dict[str, AnalysisMatrix] = {}
        self._threads = []  # keep references alive while running

        layout = QVBoxLayout(self)

        button_grid = QGridLayout()
        self._add_button(button_grid, 0, 0, "RMSD", lambda: self._run("rmsd"))
        self._add_button(button_grid, 0, 1, "Radius of gyration", lambda: self._run("rg"))
        self._add_button(button_grid, 0, 2, "Q-value", lambda: self._run("qvalue"))
        self._add_button(button_grid, 1, 0, "Contact map (final frame)", lambda: self._run("contact_map", "final"))
        self._add_button(button_grid, 1, 1, "Contact map (time-averaged)", lambda: self._run("contact_map", "time_averaged"))
        self._add_button(button_grid, 1, 2, "Temperature / energy over time", self._plot_temperature_energy)
        self.density_button = self._add_button(button_grid, 2, 0, "Density profile (z)", lambda: self._run("density"))
        self.density_button.setEnabled(project.model_type == ModelType.HPS_CONDENSATE)
        layout.addLayout(button_grid)

        self.canvas = MplCanvas(title="Analysis result", ylabel="value")
        layout.addWidget(self.canvas)

        bottom_row = QHBoxLayout()
        save_png_button = QPushButton("Save PNG")
        save_png_button.clicked.connect(self._save_png)
        bottom_row.addWidget(save_png_button)

        export_button = QPushButton("Export to Excel")
        export_button.clicked.connect(self._export_excel)
        bottom_row.addWidget(export_button)

        vmd_button = QPushButton("Open in VMD")
        vmd_button.clicked.connect(self._open_in_vmd)
        bottom_row.addWidget(vmd_button)

        bottom_row.addStretch(1)
        layout.addLayout(bottom_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _add_button(self, grid: QGridLayout, row: int, col: int, label: str, handler) -> QPushButton:
        button = QPushButton(label)
        button.clicked.connect(handler)
        grid.addWidget(button, row, col)
        return button

    # -- running analyses ----------------------------------------------------
    def _run(self, analysis_type: str, mode: Optional[str] = None) -> None:
        self.status_label.setText(f"Running {ANALYSIS_TOOLS[analysis_type][3]}...")
        thread = QThread(self)
        worker = AnalysisWorker(self.bridge, analysis_type, self.project, self.local_directory, mode)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_analysis_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda: self._threads.remove((thread, worker)) if (thread, worker) in self._threads else None)
        self._threads.append((thread, worker))
        thread.start()

    def _on_analysis_finished(self, key: str, analysis_type: str, result: AnalysisRunResult, mode: Optional[str]) -> None:
        if not result.success:
            self.status_label.setText(f"{key} failed: {result.log.strip()[-300:]}")
            return

        if analysis_type == "density":
            # density_analysis writes a binary CCP4 3D map (+ a .pdb), not
            # a text series -- see SERIES_ANALYSES's comment and
            # app/analysis.py's module docstring. Nothing here can plot
            # that, so just point the user at the file.
            self.status_label.setText(
                f"{key} complete: wrote {result.output_path} (binary CCP4 map — open in VMD/PyMOL, not plottable here)."
            )
            return

        text = result.output_path.read_text(errors="replace")

        if analysis_type == "contact_map":
            matrix = parse_contact_map(text)
            label = "Contact map (time-averaged)" if mode == "time_averaged" else "Contact map (final frame)"
            self._matrix_results[key] = AnalysisMatrix(label=label, matrix=matrix)
            self.canvas.axes.cla()
            self.canvas.axes.imshow(matrix, cmap="viridis", origin="lower")
            self.canvas.axes.set_title(label)
            self.canvas.draw_idle()
        else:
            x_label, y_label = SERIES_ANALYSES.get(analysis_type, ("Frame", "Value"))
            xs, ys = parse_two_column_series(text)
            label = ANALYSIS_TOOLS[analysis_type][3]
            self._series_results[key] = AnalysisSeries(label=label, x_label=x_label, y_label=y_label, x=xs, y=ys)
            self.canvas.clear()
            self.canvas.set_series(label, xs, ys)
            self.canvas.axes.set_xlabel(x_label)
            self.canvas.axes.set_ylabel(y_label)
            self.canvas.rescale_and_draw()

        self.status_label.setText(f"{key} complete.")

    def _plot_temperature_energy(self) -> None:
        log_path = Path(self.local_directory) / "run.log"
        if not log_path.exists():
            self.status_label.setText("No run.log found yet — run the simulation first.")
            return
        parser = GenesisLogParser()
        parser.feed(log_path.read_text(errors="replace"))
        if not parser.records:
            self.status_label.setText("run.log has no parsed energy records yet.")
            return

        steps = [r.step for r in parser.records]
        self.canvas.clear()
        for term in ("POTENTIAL_ENE", "TOTAL_ENE", "TEMPERATURE"):
            values = [r.values.get(term) for r in parser.records if term in r.values]
            if values:
                xs = steps[: len(values)]
                self.canvas.set_series(term, xs, values)
                self._series_results[f"timeseries_{term}"] = AnalysisSeries(
                    label=f"{term} over time", x_label="Step", y_label=term, x=np.array(xs), y=np.array(values)
                )
        self.canvas.axes.set_xlabel("Step")
        self.canvas.rescale_and_draw()
        self.status_label.setText("Plotted temperature/energy from run.log.")

    # -- export / misc ---------------------------------------------------------
    def _save_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save plot as PNG", "", "PNG images (*.png)")
        if path:
            self.canvas.figure.savefig(path)
            self.status_label.setText(f"Saved {path}")

    def _export_excel(self) -> None:
        if not self._series_results and not self._matrix_results:
            self.status_label.setText("No analysis results to export yet.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export to Excel", "analysis.xlsx", "Excel files (*.xlsx)")
        if not path:
            return
        export_to_excel(self.project, self._series_results, self._matrix_results, path)
        self.status_label.setText(f"Exported to {path}")

    def _open_in_vmd(self) -> None:
        vmd_path = self.settings.vmd_path
        if not Path(vmd_path).exists():
            self.status_label.setText(f"VMD not found at {vmd_path}. Set the path in Settings.")
            return
        dcd_path = str(Path(self.local_directory) / f"{self.project.name}.dcd")
        try:
            subprocess.Popen([vmd_path, dcd_path])
            self.status_label.setText("Launched VMD.")
        except OSError as exc:
            self.status_label.setText(f"Could not launch VMD: {exc}")
