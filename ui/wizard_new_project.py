"""New Project wizard (F2): Input -> Model -> [All-Atom Files] -> Parameters -> Resources -> Review.

The All-Atom Files page only appears when the Input page's "Pre-built
all-atom system (CHARMM)" mode is selected -- see nextId() below.
"""
from __future__ import annotations

from PyQt5.QtWidgets import QWizard

from app.project import Project, ModelType, InputMode, SimulationParameters, ResourceConfig
from app.settings import Settings
from ui.page_input import InputPage
from ui.page_model import ModelPage, InputState
from ui.page_all_atom_input import AllAtomInputPage
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
        self.all_atom_input_page = AllAtomInputPage()
        self.parameters_page = ParametersPage(self._selected_model_type)
        self.resources_page = ResourcesPage(settings, self._selected_model_type, self._particle_estimate)
        self.review_page = ReviewPage(settings, self._build_project)

        self._id_input = self.addPage(self.input_page)
        self._id_model = self.addPage(self.model_page)
        self._id_all_atom_input = self.addPage(self.all_atom_input_page)
        self._id_parameters = self.addPage(self.parameters_page)
        self._id_resources = self.addPage(self.resources_page)
        self._id_review = self.addPage(self.review_page)

    def nextId(self) -> int:
        # Every other page follows Qt's default sequential order (matching
        # the order pages were added in); the All-Atom Files page is the
        # one exception, skipped for every model except ALL_ATOM_CHARMM.
        if self.currentId() == self._id_model and not self.input_page.is_all_atom_prebuilt():
            return self._id_parameters
        return super().nextId()

    # -- cross-page state ---------------------------------------------------
    def _input_state(self) -> InputState:
        is_sequence = self.input_page.is_sequence_mode()
        is_all_atom_prebuilt = self.input_page.is_all_atom_prebuilt()
        has_dna_hint = False
        if not is_sequence and not is_all_atom_prebuilt and self.input_page.pdb_info is not None:
            for chain in self.input_page.pdb_info.chains:
                seq = chain.sequence
                if seq and sum(c in "ACGT" for c in seq) / len(seq) > 0.9:
                    has_dna_hint = True
                    break
        return InputState(
            is_sequence_mode=is_sequence, has_dna_hint=has_dna_hint, is_all_atom_prebuilt=is_all_atom_prebuilt
        )

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
        is_all_atom = self.input_page.is_all_atom_prebuilt()

        parameters = SimulationParameters(
            temperature_k=self.parameters_page.temperature.value(),
            n_steps=self.parameters_page.n_steps.value(),
            timestep_fs=self.parameters_page.timestep.value(),
            output_frequency=self.parameters_page.output_frequency.value(),
            langevin_friction=self.parameters_page.friction.value(),
            n_copies=self.parameters_page.n_copies.value() if model_type == ModelType.HPS_CONDENSATE else 1,
            ensemble=self.parameters_page.ensemble.currentText(),
            pressure_atm=self.parameters_page.pressure.value(),
            use_position_restraints=self.parameters_page.position_restraints.isChecked(),
            position_restraint_force_constant=self.parameters_page.restraint_force_constant.value(),
            remd_enabled=self.resources_page.remd_enabled.isChecked(),
            remd_n_replicas=self.resources_page.remd_n_replicas.value(),
            remd_exchange_period=self.resources_page.remd_exchange_period.value(),
            remd_temperatures=self.resources_page.parsed_remd_temperatures(),
            gamd_enabled=self.parameters_page.gamd_enabled.isChecked(),
            gamd_update_period=self.parameters_page.gamd_update_period.value(),
        )
        if model_type == ModelType.HPS_CONDENSATE:
            parameters.box_size_nm = self.parameters_page.box_z.value()

        resources = ResourceConfig(
            engine=self.resources_page.selected_engine(),
            mpi_ranks=self.resources_page.mpi_ranks.value(),
            omp_threads=self.resources_page.omp_threads.value(),
            engine_overridden=self.resources_page.engine_combo.currentData() is not None,
        )

        if is_all_atom:
            input_mode = InputMode.ALL_ATOM_PREBUILT
        elif is_sequence:
            input_mode = InputMode.SEQUENCE
        else:
            input_mode = InputMode.PDB

        project = Project(
            name=name,
            directory=f"~/genesis_projects/{name}",
            model_type=model_type,
            input_mode=input_mode,
            input_path=self.input_page.pdb_path if input_mode == InputMode.PDB else "",
            sequence=self.input_page.sequence_text if input_mode == InputMode.SEQUENCE else "",
            parameters=parameters,
            resources=resources,
        )
        if is_all_atom:
            project.aa_top_source_paths = self.all_atom_input_page.top_files.paths()
            project.aa_par_source_paths = self.all_atom_input_page.par_files.paths()
            project.aa_str_source_paths = self.all_atom_input_page.str_files.paths()
            project.aa_psf_source_path = self.all_atom_input_page.psf_path_edit.text().strip()
            project.aa_pdb_source_path = self.all_atom_input_page.pdb_path_edit.text().strip()
            project.aa_box_x = self.all_atom_input_page.box_x.value()
            project.aa_box_y = self.all_atom_input_page.box_y.value()
            project.aa_box_z = self.all_atom_input_page.box_z.value()

        self.review_page.source_pdb_path = self.input_page.pdb_path if input_mode == InputMode.PDB else None
        return project
