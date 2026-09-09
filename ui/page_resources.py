"""Wizard page 4: engine + MPI/OMP resource picker (F2.4)."""
from __future__ import annotations

from typing import Callable

from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QPushButton,
    QHBoxLayout,
    QPlainTextEdit,
    QLabel,
)

from app.project import ModelType, Engine
from app.settings import Settings


class ResourcesPage(QWizardPage):
    def __init__(
        self,
        settings: Settings,
        get_model_type: Callable[[], ModelType],
        get_particle_estimate: Callable[[], int],
        parent=None,
    ):
        super().__init__(parent)
        self.setTitle("Resources")
        self.setSubTitle("Choose the engine and how many cores to use.")
        self.settings = settings
        self._get_model_type = get_model_type
        self._get_particle_estimate = get_particle_estimate
        self._auto_engine = Engine.ATDYN
        self._user_overrode_engine = False
        self._defaults_applied = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Auto (recommended)", None)
        self.engine_combo.addItem("atdyn", Engine.ATDYN)
        self.engine_combo.addItem("cgdyn", Engine.CGDYN)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        form.addRow("Engine:", self.engine_combo)

        self.engine_reason_label = QLabel("")
        self.engine_reason_label.setWordWrap(True)
        form.addRow("", self.engine_reason_label)

        preset_row = QHBoxLayout()
        for label, ranks, threads in [("4 x 4", 4, 4), ("8 x 2", 8, 2), ("16 x 1", 16, 1)]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked, r=ranks, t=threads: self._apply_preset(r, t))
            preset_row.addWidget(button)
        half_button = QPushButton("Leave half the machine free")
        half_button.clicked.connect(self._apply_half_preset)
        preset_row.addWidget(half_button)
        form.addRow("Presets:", preset_row)

        self.mpi_ranks = QSpinBox()
        self.mpi_ranks.setRange(1, 256)
        self.mpi_ranks.valueChanged.connect(self._update_preview)
        form.addRow("MPI ranks:", self.mpi_ranks)

        self.omp_threads = QSpinBox()
        self.omp_threads.setRange(1, 256)
        self.omp_threads.valueChanged.connect(self._update_preview)
        form.addRow("OMP threads/rank:", self.omp_threads)

        self.core_usage_label = QLabel("")
        form.addRow("", self.core_usage_label)

        layout.addWidget(QLabel("Exact command that will be launched:"))
        self.command_preview = QPlainTextEdit()
        self.command_preview.setReadOnly(True)
        self.command_preview.setMaximumHeight(120)
        layout.addWidget(self.command_preview)

    def initializePage(self) -> None:
        model_type = self._get_model_type()
        n_particles = self._get_particle_estimate()
        if model_type == ModelType.HPS_CONDENSATE:
            self._auto_engine = Engine.CGDYN
            reason = "Auto-selected cgdyn: condensate/multi-chain systems always use cgdyn."
        elif n_particles >= 5000:
            self._auto_engine = Engine.CGDYN
            reason = f"Auto-selected cgdyn: estimated {n_particles} CG particles (>= 5000)."
        else:
            self._auto_engine = Engine.ATDYN
            reason = f"Auto-selected atdyn: single chain, estimated {n_particles} CG particles (< 5000)."
        self.engine_reason_label.setText(reason)

        if not self._user_overrode_engine:
            self.engine_combo.setCurrentIndex(0)

        if not self._defaults_applied:
            self._defaults_applied = True
            default_ranks = 4
            self.mpi_ranks.setValue(default_ranks)
            self.omp_threads.setValue(max(self.settings.total_cores // default_ranks, 1))
        self._update_preview()

    def _on_engine_changed(self, index: int) -> None:
        self._user_overrode_engine = self.engine_combo.currentData() is not None
        self._update_preview()

    def _apply_preset(self, ranks: int, threads: int) -> None:
        self.mpi_ranks.setValue(ranks)
        self.omp_threads.setValue(threads)

    def _apply_half_preset(self) -> None:
        half = max(self.settings.total_cores // 2, 1)
        # keep it simple: half the ranks at 1 thread each, or scale down
        # proportionally from a 4x4-style split
        ranks = max(half // 4, 1)
        threads = max(half // ranks, 1)
        self.mpi_ranks.setValue(ranks)
        self.omp_threads.setValue(threads)

    def selected_engine(self) -> Engine:
        data = self.engine_combo.currentData()
        return data if data is not None else self._auto_engine

    def _update_preview(self) -> None:
        ranks = self.mpi_ranks.value()
        threads = self.omp_threads.value()
        used = ranks * threads
        self.core_usage_label.setText(f"{used} of {self.settings.total_cores} cores requested.")

        engine = self.selected_engine()
        mpi_args = self.settings.mpi_args_for(threads)
        cmd = (
            f"setsid bash -c '\n"
            f"  echo $$ > run.pgid\n"
            f"  export OMP_NUM_THREADS={threads}\n"
            f"  exec mpirun -np {ranks} {mpi_args} {engine.value} run.inp > run.log 2>&1\n"
            f"' &"
        )
        self.command_preview.setPlainText(cmd)

    def isComplete(self) -> bool:
        return self.mpi_ranks.value() > 0 and self.omp_threads.value() > 0
