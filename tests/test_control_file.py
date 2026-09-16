from pathlib import Path

import pytest

from app.control_file import ControlFileConfig, render_control_file, write_control_file
from app.project import ModelType


def _config(**overrides):
    base = dict(
        top_file="system.top",
        gro_file="system.gro",
        output_prefix="run",
        temperature_k=300.0,
        n_steps=1_000_000,
        timestep_fs=10.0,
        output_frequency=1000,
        langevin_friction=0.01,
    )
    base.update(overrides)
    return ControlFileConfig(**base)


def test_render_aicg2p_contains_sections():
    text = render_control_file(_config(box_x=180.0, box_y=180.0, box_z=180.0), ModelType.AICG2P)
    for section in ["[INPUT]", "[OUTPUT]", "[ENERGY]", "[DYNAMICS]", "[CONSTRAINTS]", "[ENSEMBLE]", "[BOUNDARY]"]:
        assert section in text
    assert "forcefield          = RESIDCG" in text
    assert "type       = PBC" in text
    assert "box_size_x = 180.0" in text
    assert "nsteps         = 1000000" in text
    assert "temperature = 300.0" in text


def test_render_aicg2p_requires_box():
    with pytest.raises(ValueError):
        render_control_file(_config(), ModelType.AICG2P)


def test_render_hps_condensate_requires_box():
    with pytest.raises(ValueError):
        render_control_file(_config(), ModelType.HPS_CONDENSATE)

    text = render_control_file(_config(box_x=20.0, box_y=20.0, box_z=200.0), ModelType.HPS_CONDENSATE)
    assert "type       = PBC" in text
    assert "box_size_z = 200.0" in text


def _aicg2p_config(**overrides):
    overrides.setdefault("box_x", 180.0)
    overrides.setdefault("box_y", 180.0)
    overrides.setdefault("box_z", 180.0)
    return _config(**overrides)


def test_timestep_converted_fs_to_ps():
    text = render_control_file(_aicg2p_config(timestep_fs=15.0), ModelType.AICG2P)
    assert "timestep       = 0.0150" in text


def test_no_verify_markers_remain():
    # As of the tutorial 11.4 (FUS) cross-check, every control-file
    # template keyword is confirmed against a real mdgenesis.org tutorial
    # or a real installed GENESIS's `-h ctrl_all` output -- no template
    # keyword is left marked # VERIFY. (app/cgtool.py's HPS/sequence path
    # and app/analysis.py still have real open VERIFY items; this test is
    # specifically about the rendered .inp templates.)
    for model_type, box in [
        (ModelType.AICG2P, dict(box_x=180.0, box_y=180.0, box_z=180.0)),
        (ModelType.HPS_SINGLE, {}),
        (ModelType.HPS_CONDENSATE, dict(box_x=180.0, box_y=180.0, box_z=1800.0)),
        (ModelType.PROTEIN_DNA, {}),
    ]:
        text = render_control_file(_config(**box), model_type)
        assert "VERIFY" not in text


def test_hps_single_energy_block_matches_tutorial_11_4():
    text = render_control_file(_config(), ModelType.HPS_SINGLE)
    for line in [
        "forcefield            = RESIDCG",
        "electrostatic         = CUTOFF",
        "cg_cutoffdist_ele     = 52.0",
        "cg_cutoffdist_126     = 39.0",
        "cg_pairlistdist_ele   = 57.0",
        "cg_pairlistdist_126   = 44.0",
        "cg_sol_ionic_strength = 0.15",
        "cg_IDR_HPS_epsilon    = 0.2",
    ]:
        assert line in text
    assert "type = NOBC" in text


def test_hps_condensate_energy_block_matches_tutorial_11_4():
    text = render_control_file(
        _config(box_x=180.0, box_y=180.0, box_z=1800.0), ModelType.HPS_CONDENSATE
    )
    assert "cg_IDR_HPS_epsilon    = 0.2" in text
    assert "type       = PBC" in text
    assert "box_size_z = 1800.0" in text


def test_integrator_is_engine_dependent():
    # Real installed GENESIS 2.1.6 `cgdyn -h ctrl_all` only accepts
    # integrator [LEAP,VVER] -- no VVER_CG -- while `atdyn -h ctrl_all`
    # accepts [LEAP,VVER,VVER_CG]. A shared control-file section can't
    # hardcode one value for both engines.
    cgdyn_text = render_control_file(_config(engine="cgdyn"), ModelType.HPS_SINGLE)
    integrator_line = next(line for line in cgdyn_text.splitlines() if line.startswith("integrator"))
    assert integrator_line.split()[2] == "VVER"

    atdyn_text = render_control_file(_aicg2p_config(engine="atdyn"), ModelType.AICG2P)
    assert "integrator     = VVER_CG" in atdyn_text


def test_write_control_file_creates_file(tmp_path: Path):
    path = write_control_file(_aicg2p_config(), ModelType.AICG2P, str(tmp_path), filename="run.inp")
    assert path.exists()
    assert path.read_text() == render_control_file(_aicg2p_config(), ModelType.AICG2P)


def test_generated_control_files_have_no_crlf_or_semicolon_comments():
    # Real installed GENESIS 2.1.6 rejected a control file containing CRLF
    # line endings and ";"-prefixed comment lines ("Unknown parameter:
    # [output] ..."). GENESIS's .inp parser only accepts "#" comments and
    # plain LF endings -- see app/text_io.py and DECISIONS.md.
    for model_type, box in [
        (ModelType.AICG2P, dict(box_x=180.0, box_y=180.0, box_z=180.0)),
        (ModelType.HPS_SINGLE, {}),
        (ModelType.HPS_CONDENSATE, dict(box_x=180.0, box_y=180.0, box_z=1800.0)),
        (ModelType.PROTEIN_DNA, {}),
    ]:
        text = render_control_file(_config(**box), model_type)
        assert "\r" not in text
        for line in text.splitlines():
            assert not line.lstrip().startswith(";"), f"semicolon comment in {model_type}: {line!r}"


def test_write_control_file_writes_lf_and_ascii_only(tmp_path: Path):
    path = write_control_file(_aicg2p_config(), ModelType.AICG2P, str(tmp_path))
    raw = path.read_bytes()
    assert b"\r" not in raw
    raw.decode("ascii")  # raises if any non-ASCII byte slipped through


def test_write_control_file_preserves_manual_edits_unless_forced(tmp_path: Path):
    path = write_control_file(_aicg2p_config(), ModelType.AICG2P, str(tmp_path))
    path.write_text("; hand-edited by user\n")

    same_path = write_control_file(_aicg2p_config(), ModelType.AICG2P, str(tmp_path))
    assert same_path.read_text() == "; hand-edited by user\n"

    overwritten_path = write_control_file(_aicg2p_config(), ModelType.AICG2P, str(tmp_path), force=True)
    assert overwritten_path.read_text() != "; hand-edited by user\n"


# -- Roadmap Phase 3: NPT ensemble + position restraints ---------------------
def test_nvt_render_is_unchanged_by_new_optional_sections():
    text = render_control_file(_config(box_x=180.0, box_y=180.0, box_z=180.0), ModelType.AICG2P)
    assert "ensemble    = NVT" in text
    assert "pressure" not in text
    assert "[SELECTION]" not in text
    assert "[RESTRAINTS]" not in text
    assert "groreffile" not in text


def test_npt_ensemble_adds_pressure_and_verify_marked_tpcontrol():
    text = render_control_file(
        _config(box_x=180.0, box_y=180.0, box_z=180.0, ensemble="NPT", pressure_atm=2.5), ModelType.AICG2P
    )
    assert "ensemble    = NPT" in text
    assert "pressure    = 2.5" in text
    assert "# VERIFY" in text  # tpcontrol+NPT compatibility for this CG integrator is not confirmed


def test_npt_rejected_for_model_types_without_a_box():
    with pytest.raises(ValueError):
        render_control_file(_config(ensemble="NPT"), ModelType.HPS_SINGLE)


def test_position_restraints_add_selection_and_restraints_sections():
    text = render_control_file(
        _config(box_x=180.0, box_y=180.0, box_z=180.0, use_position_restraints=True, position_restraint_force_constant=25.0),
        ModelType.AICG2P,
    )
    assert "groreffile = system.gro" in text
    assert "[SELECTION]" in text
    assert "group1 = all" in text
    assert "[RESTRAINTS]" in text
    assert "function1  = POSI" in text
    assert "constant1  = 25.0" in text
    assert "select_index1 = 1" in text


def test_position_restraints_work_without_a_box_too():
    # POSI doesn't need a periodic box -- unlike NPT, this must stay legal
    # for NOBC model types (HPS_SINGLE, PROTEIN_DNA).
    text = render_control_file(_config(use_position_restraints=True), ModelType.HPS_SINGLE)
    assert "[RESTRAINTS]" in text


# -- Roadmap Phase 4: REMD + GaMD --------------------------------------------
def test_remd_adds_section_and_replica_templated_output_files():
    text = render_control_file(
        _config(remd_enabled=True, remd_exchange_period=500, remd_temperatures=[300.0, 310.0, 320.0]),
        ModelType.HPS_SINGLE,
    )
    assert "[REMD]" in text
    assert "nreplica1       = 3" in text
    assert "parameters1     = 300.0 310.0 320.0" in text
    assert "exchange_period = 500" in text
    assert "dcdfile = run_rep{}.dcd" in text
    assert "rstfile = run_rep{}.rst" in text
    assert "logfile = run_rep{}.log" in text
    assert "remfile = run_rep{}.rem" in text
    assert "pdbfile =" not in text  # omitted under REMD, not confirmed to need '{}' too
    assert "# VERIFY" in text


def test_remd_requires_at_least_two_temperatures():
    with pytest.raises(ValueError):
        render_control_file(_config(remd_enabled=True, remd_temperatures=[300.0]), ModelType.HPS_SINGLE)


def test_non_remd_render_has_no_remd_section_or_replica_filenames():
    text = render_control_file(_config(), ModelType.HPS_SINGLE)
    assert "[REMD]" not in text
    assert "_rep{}" not in text
    assert "pdbfile" in text


def test_gamd_adds_section_with_confirmed_defaults():
    text = render_control_file(_config(gamd_enabled=True, gamd_update_period=500, gamd_sigma0_pot=8.0), ModelType.HPS_SINGLE)
    assert "[GAMD]" in text
    assert "gamd          = YES" in text
    assert "boost_type    = POTENTIAL" in text
    assert "update_period = 500" in text
    assert "sigma0_pot    = 8.0" in text
    assert "gamdfile = run.gamd" in text


def test_gamd_rejects_zero_update_period():
    with pytest.raises(ValueError):
        render_control_file(_config(gamd_enabled=True, gamd_update_period=0), ModelType.HPS_SINGLE)


# -- Roadmap Phase 5: all-atom CHARMM ----------------------------------------
def _aa_config(**overrides):
    base = dict(
        top_file="",
        gro_file="",
        output_prefix="run",
        temperature_k=300.0,
        n_steps=1_000_000,
        timestep_fs=2.0,
        output_frequency=1000,
        langevin_friction=1.0,
        box_x=68.26,
        box_y=80.24,
        box_z=66.59,
        aa_top_files=["../toppar/top_all36_prot.rtf"],
        aa_par_files=["../toppar/par_all36m_prot.prm"],
        aa_psf_file="../build/input.psf",
        aa_pdb_file="../build/input.pdb",
    )
    base.update(overrides)
    return ControlFileConfig(**base)


def test_all_atom_charmm_renders_confirmed_sections():
    text = render_control_file(_aa_config(), ModelType.ALL_ATOM_CHARMM)
    for section in ["[INPUT]", "[OUTPUT]", "[DYNAMICS]", "[CONSTRAINTS]", "[ENSEMBLE]", "[ENERGY]", "[BOUNDARY]"]:
        assert section in text
    assert "topfile = ../toppar/top_all36_prot.rtf" in text
    assert "psffile = ../build/input.psf" in text
    assert "pdbfile = ../build/input.pdb" in text
    assert "integrator     = VVER" in text
    assert "integrator     = VVER_CG" not in text  # CG-only integrator must never appear for an all-atom run
    assert "rigid_bond = YES" in text
    assert "fast_water = YES" in text
    assert "forcefield          = CHARMM" in text
    assert "electrostatic       = PME" in text
    assert "vdw_force_switch    = YES" in text


def test_all_atom_charmm_optional_strfile_included_when_given():
    with_str = render_control_file(_aa_config(aa_str_files=["../toppar/toppar_water_ions.str"]), ModelType.ALL_ATOM_CHARMM)
    without_str = render_control_file(_aa_config(), ModelType.ALL_ATOM_CHARMM)
    assert "strfile = ../toppar/toppar_water_ions.str" in with_str
    assert "strfile" not in without_str


def test_all_atom_charmm_requires_prepared_input_files():
    with pytest.raises(ValueError):
        render_control_file(_aa_config(aa_psf_file=None), ModelType.ALL_ATOM_CHARMM)
    with pytest.raises(ValueError):
        render_control_file(_aa_config(aa_pdb_file=None), ModelType.ALL_ATOM_CHARMM)
    with pytest.raises(ValueError):
        render_control_file(_aa_config(aa_top_files=None), ModelType.ALL_ATOM_CHARMM)


def test_all_atom_charmm_requires_a_box_for_pme():
    with pytest.raises(ValueError):
        render_control_file(_aa_config(box_x=None, box_y=None, box_z=None), ModelType.ALL_ATOM_CHARMM)


def test_all_atom_charmm_supports_npt_without_verify_caveat():
    # Unlike CG's VVER_CG, plain VVER + NPT + LANGEVIN is directly confirmed
    # by the User Guide's own compatibility table -- no # VERIFY needed here.
    text = render_control_file(_aa_config(ensemble="NPT", pressure_atm=1.0), ModelType.ALL_ATOM_CHARMM)
    assert "ensemble    = NPT" in text
    assert "pressure    = 1.0" in text
    assert "# VERIFY" not in text


def test_all_atom_charmm_position_restraints_use_pdb_as_reffile():
    text = render_control_file(_aa_config(use_position_restraints=True, position_restraint_force_constant=5.0), ModelType.ALL_ATOM_CHARMM)
    assert "reffile = ../build/input.pdb" in text
    assert "[RESTRAINTS]" in text
    assert "constant1  = 5.0" in text


def test_gamd_verify_comment_only_for_non_atdyn_engine():
    atdyn_text = render_control_file(
        _config(gamd_enabled=True, gamd_update_period=500, engine="atdyn"), ModelType.HPS_SINGLE
    )
    cgdyn_text = render_control_file(
        _config(gamd_enabled=True, gamd_update_period=500, engine="cgdyn"), ModelType.HPS_SINGLE
    )
    assert "cgdyn actually" not in atdyn_text
    assert "cgdyn actually" in cgdyn_text
