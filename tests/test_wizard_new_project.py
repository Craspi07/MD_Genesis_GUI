"""Integration tests for the wizard's page flow (Roadmap Phase 5 wizard
integration): the All-Atom Files page must appear only for the
"Pre-built all-atom system (CHARMM)" input mode and be skipped for
every other mode -- see NewProjectWizard.nextId().
"""
from app.settings import Settings
from ui.wizard_new_project import NewProjectWizard


def _wizard() -> NewProjectWizard:
    settings = Settings()
    settings.distro = "Ubuntu-24.04"
    wizard = NewProjectWizard(settings)
    wizard.show()  # QWizard's page state machine needs this before currentId()/next() work
    return wizard


def test_all_atom_mode_routes_through_all_atom_input_page():
    wizard = _wizard()
    wizard.input_page.all_atom_radio.setChecked(True)

    wizard.next()  # Input -> Model
    assert wizard.currentId() == wizard._id_model

    wizard.next()  # Model -> All-Atom Files
    assert wizard.currentId() == wizard._id_all_atom_input


def test_pdb_mode_skips_all_atom_input_page(tmp_path):
    from app.validators import parse_pdb

    pdb_path = tmp_path / "test.pdb"
    pdb_path.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00\n"
    )
    wizard = _wizard()
    wizard.input_page._load_pdb(str(pdb_path))

    wizard.next()  # Input -> Model
    assert wizard.currentId() == wizard._id_model

    wizard.next()  # Model -> Parameters (All-Atom Files skipped)
    assert wizard.currentId() == wizard._id_parameters


def test_sequence_mode_skips_all_atom_input_page():
    wizard = _wizard()
    wizard.input_page.seq_radio.setChecked(True)
    wizard.input_page.sequence_edit.setPlainText("MKTAYIAKQR")

    wizard.next()  # Input -> Model
    assert wizard.currentId() == wizard._id_model

    wizard.next()  # Model -> Parameters (All-Atom Files skipped)
    assert wizard.currentId() == wizard._id_parameters


def test_build_project_all_atom_mode_populates_aa_fields(tmp_path):
    from app.project import InputMode, ModelType

    top = tmp_path / "top_all36_prot.rtf"
    par = tmp_path / "par_all36m_prot.prm"
    psf = tmp_path / "input.psf"
    pdb = tmp_path / "input.pdb"
    for f in (top, par, psf, pdb):
        f.write_text("x\n")

    wizard = _wizard()
    wizard.input_page.all_atom_radio.setChecked(True)
    wizard.next()
    wizard.model_page.initializePage()
    assert wizard.model_page.selected_model() == ModelType.ALL_ATOM_CHARMM
    wizard.next()

    wizard.all_atom_input_page.top_files.list_widget.addItem(str(top))
    wizard.all_atom_input_page.par_files.list_widget.addItem(str(par))
    wizard.all_atom_input_page.psf_path_edit.setText(str(psf))
    wizard.all_atom_input_page.pdb_path_edit.setText(str(pdb))
    wizard.all_atom_input_page.box_x.setValue(68.26)
    wizard.all_atom_input_page.box_y.setValue(80.24)
    wizard.all_atom_input_page.box_z.setValue(66.59)

    project = wizard._build_project("myaa")

    assert project.model_type == ModelType.ALL_ATOM_CHARMM
    assert project.input_mode == InputMode.ALL_ATOM_PREBUILT
    assert project.aa_top_source_paths == [str(top)]
    assert project.aa_psf_source_path == str(psf)
    assert project.aa_box_x == 68.26
