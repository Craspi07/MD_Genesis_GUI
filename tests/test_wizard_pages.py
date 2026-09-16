from pathlib import Path

from ui.page_input import InputPage
from ui.page_model import ModelPage, InputState
from ui.page_parameters import ParametersPage
from ui.page_resources import ResourcesPage
from app.project import ModelType
from app.settings import Settings


def _pdb_text():
    def atom(serial, resname, chain, resseq):
        return (
            f"ATOM  {serial:>5}  CA {resname:>3} {chain}{resseq:>4}"
            f"   {0.0:>8.3f}{0.0:>8.3f}{0.0:>8.3f}{1.00:>6.2f}{0.00:>6.2f}\n"
        )

    lines = []
    for i, resname in enumerate(["ALA", "GLY", "SER"], start=1):
        lines.append(atom(i, resname, "A", i))
    return "".join(lines)


def test_input_page_pdb_mode_completeness(tmp_path: Path):
    page = InputPage()
    assert not page.isComplete()

    pdb_file = tmp_path / "test.pdb"
    pdb_file.write_text(_pdb_text())
    page._load_pdb(str(pdb_file))

    assert page.pdb_info is not None
    assert page.isComplete()


def test_input_page_sequence_mode_completeness():
    page = InputPage()
    page.seq_radio.setChecked(True)
    assert not page.isComplete()

    page.sequence_edit.setPlainText("MKTAYIAKQR")
    assert page.isComplete()
    assert page.sequence_text == "MKTAYIAKQR"

    page.sequence_edit.setPlainText("MKT123XYZ")
    assert not page.isComplete()


def test_model_page_gates_pdb_only_models_in_sequence_mode():
    page = ModelPage(lambda: InputState(is_sequence_mode=True))
    page.initializePage()

    for radio in page.buttons:
        card = page._card_by_button[radio]
        if card.requires_pdb:
            assert not radio.isEnabled()
        else:
            assert radio.isEnabled()

    assert page.selected_model() == ModelType.HPS_SINGLE


def test_model_page_allows_all_non_dna_in_pdb_mode():
    page = ModelPage(lambda: InputState(is_sequence_mode=False, has_dna_hint=False))
    page.initializePage()

    aicg2p_radio = next(r for r in page.buttons if page._card_by_button[r].model_type == ModelType.AICG2P)
    dna_radio = next(r for r in page.buttons if page._card_by_button[r].model_type == ModelType.PROTEIN_DNA)
    assert aicg2p_radio.isEnabled()
    assert not dna_radio.isEnabled()
    assert page.selected_model() == ModelType.AICG2P


# -- Roadmap Phase 3: NPT ensemble + position restraints UI ------------------
def test_ensemble_combo_disabled_for_model_types_without_a_box():
    page = ParametersPage(lambda: ModelType.HPS_SINGLE)
    page.initializePage()
    assert not page.ensemble.isEnabled()
    assert page.ensemble.currentText() == "NVT"


def test_ensemble_combo_enabled_for_model_types_with_a_box():
    page = ParametersPage(lambda: ModelType.AICG2P)
    page.initializePage()
    assert page.ensemble.isEnabled()


def test_pressure_field_only_enabled_when_npt_selected():
    page = ParametersPage(lambda: ModelType.AICG2P)
    page.initializePage()
    assert not page.pressure.isEnabled()

    page.ensemble.setCurrentText("NPT")
    assert page.pressure.isEnabled()

    page.ensemble.setCurrentText("NVT")
    assert not page.pressure.isEnabled()


def test_restraint_force_constant_only_enabled_when_checked():
    page = ParametersPage(lambda: ModelType.AICG2P)
    page.initializePage()
    assert not page.restraint_force_constant.isEnabled()

    page.position_restraints.setChecked(True)
    assert page.restraint_force_constant.isEnabled()


def test_gamd_update_period_only_enabled_when_checked_and_gets_nonzero_default():
    page = ParametersPage(lambda: ModelType.AICG2P)
    page.initializePage()
    assert not page.gamd_update_period.isEnabled()
    assert page.gamd_update_period.value() == 0

    page.gamd_enabled.setChecked(True)
    assert page.gamd_update_period.isEnabled()
    assert page.gamd_update_period.value() > 0  # a checked-but-zero period would fail to render


def _resources_page(model_type=ModelType.AICG2P):
    return ResourcesPage(Settings(), lambda: model_type, lambda: 100)


def test_remd_fields_disabled_until_checkbox_enabled():
    page = _resources_page()
    page.initializePage()
    assert not page.remd_n_replicas.isEnabled()
    assert not page.remd_temperatures.isEnabled()
    assert not page.remd_exchange_period.isEnabled()

    page.remd_enabled.setChecked(True)
    assert page.remd_n_replicas.isEnabled()
    assert page.remd_temperatures.isEnabled()
    assert page.remd_exchange_period.isEnabled()


def test_remd_parses_space_separated_temperatures():
    page = _resources_page()
    page.remd_temperatures.setText("298.15 311.79 321.18 330.82")
    assert page.parsed_remd_temperatures() == [298.15, 311.79, 321.18, 330.82]


def test_remd_incomplete_until_temperature_count_matches_replica_count():
    page = _resources_page()
    page.initializePage()
    page.remd_enabled.setChecked(True)
    page.remd_n_replicas.setValue(4)
    assert not page.isComplete()  # no temperatures entered yet

    page.remd_temperatures.setText("298.15 311.79 321.18")
    assert not page.isComplete()  # only 3, needs 4

    page.remd_temperatures.setText("298.15 311.79 321.18 330.82")
    assert page.isComplete()


def test_remd_scales_command_preview_ranks():
    page = _resources_page()
    page.initializePage()
    page.mpi_ranks.setValue(2)
    page.remd_enabled.setChecked(True)
    page.remd_n_replicas.setValue(3)
    assert "-np 6" in page.command_preview.toPlainText()
