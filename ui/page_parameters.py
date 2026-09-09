"""Wizard page 3: simulation parameters (F2.3)."""
from __future__ import annotations

from typing import Callable

from PyQt5.QtWidgets import (
    QWizardPage,
    QFormLayout,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
)

from app.project import ModelType
from app.presets import defaults_for


class ParametersPage(QWizardPage):
    def __init__(self, get_model_type: Callable[[], ModelType], parent=None):
        super().__init__(parent)
        self.setTitle("Parameters")
        self.setSubTitle("Tune the simulation. Defaults come from the chosen model.")
        self._get_model_type = get_model_type
        self._current_model_type = None

        outer = QVBoxLayout(self)
        form = QFormLayout()
        outer.addLayout(form)

        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(50.0, 500.0)
        self.temperature.setSuffix(" K")
        self.temperature.setToolTip("Simulation temperature. Typical range: 250-320 K for physiological conditions.")
        form.addRow("Temperature:", self.temperature)

        self.n_steps = QSpinBox()
        self.n_steps.setRange(1000, 2_000_000_000)
        self.n_steps.setSingleStep(100000)
        self.n_steps.setToolTip("Total number of integration steps. More steps = longer, more converged sampling.")
        form.addRow("Number of steps:", self.n_steps)

        self.timestep = QDoubleSpinBox()
        self.timestep.setRange(0.1, 50.0)
        self.timestep.setSuffix(" fs")
        self.timestep.setToolTip("Integration timestep. CG models tolerate larger timesteps than all-atom (typically 5-20 fs).")
        form.addRow("Timestep:", self.timestep)

        self.output_frequency = QSpinBox()
        self.output_frequency.setRange(1, 1_000_000)
        self.output_frequency.setToolTip("How often (in steps) to write trajectory/energy/restart output.")
        form.addRow("Output frequency:", self.output_frequency)

        self.friction = QDoubleSpinBox()
        self.friction.setRange(0.0001, 10.0)
        self.friction.setDecimals(4)
        self.friction.setToolTip("Langevin friction coefficient (ps^-1). Typical range: 0.001-1.0 for CG models.")
        form.addRow("Langevin friction:", self.friction)

        self.box_x = QDoubleSpinBox()
        self.box_y = QDoubleSpinBox()
        self.box_z = QDoubleSpinBox()
        for box in (self.box_x, self.box_y, self.box_z):
            box.setRange(1.0, 10000.0)
            box.setSuffix(" nm")
        box_row = QHBoxLayout()
        box_row.addWidget(self.box_x)
        box_row.addWidget(self.box_y)
        box_row.addWidget(self.box_z)
        auto_box_button = QPushButton("Auto from system size")
        auto_box_button.setToolTip("Estimate a reasonable box from the chain length and copy count.")
        auto_box_button.clicked.connect(self._auto_box_size)
        box_row.addWidget(auto_box_button)
        form.addRow("Box size (x/y/z):", box_row)

        self.n_copies = QSpinBox()
        self.n_copies.setRange(1, 2000)
        self.n_copies.setToolTip("Number of chain copies placed in the slab box (condensate mode only).")
        form.addRow("Number of copies:", self.n_copies)

        self.position_restraints = QCheckBox("Apply position restraints")
        self.position_restraints.setToolTip("Restrain heavy atoms near their starting positions (useful during equilibration).")
        form.addRow("", self.position_restraints)

        self.eta_label = QLabel("Estimated wall time: not yet benchmarked. Use Tools > Benchmark after creating the project.")
        self.eta_label.setWordWrap(True)
        outer.addWidget(self.eta_label)

    def initializePage(self) -> None:
        model_type = self._get_model_type()
        self._current_model_type = model_type
        defaults = defaults_for(model_type)

        self.temperature.setValue(defaults.get("temperature_k", 300.0))
        self.n_steps.setValue(defaults.get("n_steps", 1_000_000))
        self.timestep.setValue(defaults.get("timestep_fs", 10.0))
        self.output_frequency.setValue(defaults.get("output_frequency", 1000))
        self.friction.setValue(defaults.get("langevin_friction", 0.01))

        is_condensate = model_type == ModelType.HPS_CONDENSATE
        self.n_copies.setEnabled(is_condensate)
        self.box_x.setEnabled(is_condensate)
        self.box_y.setEnabled(is_condensate)
        self.box_z.setEnabled(is_condensate)
        if is_condensate:
            self.n_copies.setValue(defaults.get("n_copies", 50))
            self.box_x.setValue(defaults.get("box_x_nm", 20.0))
            self.box_y.setValue(defaults.get("box_y_nm", 20.0))
            self.box_z.setValue(defaults.get("box_z_nm", 200.0))
        else:
            self.n_copies.setValue(1)

    def _auto_box_size(self) -> None:
        # Rough heuristic: ~0.5 nm per residue extent plus margin, scaled by
        # copy count along z for the slab dimension.
        n_copies = self.n_copies.value() if self.n_copies.isEnabled() else 1
        base = 20.0
        self.box_x.setValue(base)
        self.box_y.setValue(base)
        self.box_z.setValue(base + 5.0 * n_copies)

    def isComplete(self) -> bool:
        return True
