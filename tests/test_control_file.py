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


def test_verify_markers_present():
    text = render_control_file(_config(), ModelType.HPS_SINGLE)
    assert "VERIFY" in text


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


def test_write_control_file_preserves_manual_edits_unless_forced(tmp_path: Path):
    path = write_control_file(_aicg2p_config(), ModelType.AICG2P, str(tmp_path))
    path.write_text("; hand-edited by user\n")

    same_path = write_control_file(_aicg2p_config(), ModelType.AICG2P, str(tmp_path))
    assert same_path.read_text() == "; hand-edited by user\n"

    overwritten_path = write_control_file(_aicg2p_config(), ModelType.AICG2P, str(tmp_path), force=True)
    assert overwritten_path.read_text() != "; hand-edited by user\n"
