"""New Project wizard (F2): Input -> Model -> Parameters -> Resources -> Review."""
from __future__ import annotations

from PyQt5.QtWidgets import QWizard

from app.project import Project, ModelType, InputMode, SimulationParameters, ResourceConfig
from app.settings import Settings
from ui.page_input import InputPage
from ui.page_model import ModelPage, InputState
from ui.page_parameters import ParametersPage
from ui.page_resources import ResourcesPage
from ui.page_review import ReviewPage


class NewProjectWizard(QWizard):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("New Project")
        self.setWizardStyle(QWizard.ModernStyle)
        self.resize(760, 640)

        self.input_page = InputPage()
        self.model_page = ModelPage(self._input_state)
        self.parameters_page = ParametersPage(self._selected_model_type)
        self.resources_page = ResourcesPage(settings, self._selected_model_type, self._particle_estimate)
        self.review_page = ReviewPage(settings, self._build_project)

        self.addPage(self.input_page)
        self.addPage(self.model_page)
        self.addPage(self.parameters_page)
        self.addPage(self.resources_page)
        self.addPage(self.review_page)

    # -- cross-page state ---------------------------------------------------
    def _input_state(self) -> InputState:
        is_sequence = self.input_page.is_sequence_mode()
        has_dna_hint = False
        if not is_sequence and self.input_page.pdb_info is not None:
            for chain in self.input_page.pdb_info.chains:
                seq = chain.sequence
                if seq and sum(c in "ACGT" for c in seq) / len(seq) > 0.9:
                    has_dna_hint = True
                    break
        return InputState(is_sequence_mode=is_sequence, has_dna_hint=has_dna_hint)

    def _selected_model_type(self) -> ModelType:
        return self.model_page.selected_model() or ModelType.AICG2P

    def _particle_estimate(self) -> int:
        # Rough proxy for CG particle count: one bead per residue (backbone-
        # only estimate), times the number of copies if in condensate mode.
        if self.input_page.pdb_info is not None:
            n_residues = self.input_page.pdb_info.total_residues
        elif self.input_page.sequence_text:
            n_residues = len(self.input_page.sequence_text)
        else:
            n_residues = 0
        n_copies = self.parameters_page.n_copies.value() if hasattr(self, "parameters_page") else 1
        return n_residues * max(n_copies, 1)

    def _build_project(self, name: str) -> Project:
        model_type = self._selected_model_type()
        is_sequence = self.input_page.is_sequence_mode()

        parameters = SimulationParameters(
            temperature_k=self.parameters_page.temperature.value(),
            n_steps=self.parameters_page.n_steps.value(),
            timestep_fs=self.parameters_page.timestep.value(),
            output_frequency=self.parameters_page.output_frequency.value(),
            langevin_friction=self.parameters_page.friction.value(),
            n_copies=self.parameters_page.n_copies.value() if model_type == ModelType.HPS_CONDENSATE else 1,
            use_position_restraints=self.parameters_page.position_restraints.isChecked(),
        )
        if model_type == ModelType.HPS_CONDENSATE:
            parameters.box_size_nm = self.parameters_page.box_z.value()

        resources = ResourceConfig(
            engine=self.resources_page.selected_engine(),
            mpi_ranks=self.resources_page.mpi_ranks.value(),
            omp_threads=self.resources_page.omp_threads.value(),
            engine_overridden=self.resources_page.engine_combo.currentData() is not None,
        )

        project = Project(
            name=name,
            directory=f"~/genesis_projects/{name}",
            model_type=model_type,
            input_mode=InputMode.SEQUENCE if is_sequence else InputMode.PDB,
            input_path=self.input_page.pdb_path if not is_sequence else "",
            sequence=self.input_page.sequence_text if is_sequence else "",
            parameters=parameters,
            resources=resources,
        )
        self.review_page.source_pdb_path = self.input_page.pdb_path if not is_sequence else None
        return project
