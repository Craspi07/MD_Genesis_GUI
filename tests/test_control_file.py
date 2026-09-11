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
