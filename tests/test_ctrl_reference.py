from pathlib import Path

from app.ctrl_reference import (
    parse_ctrl_all,
    validate_control_text,
    validate_against_installed_genesis,
)
from app.control_file import ControlFileConfig, render_control_file
from app.project import ModelType
from app.wsl import WslBridge

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")

# Real `<engine> -h ctrl_all` output, as pasted by the user 2026-09-10 --
# see DECISIONS.md. Real ctrl_all output has [SECTION] headers around
# blocks like this; only the [DYNAMICS] block was actually captured, so
# these fixtures wrap it in one for testing.
CGDYN_CTRL_ALL = """
[DYNAMICS]
integrator    = LEAP      # [LEAP,VVER]
nsteps        = 100       # number of MD steps
timestep      = 0.001     # timestep (ps)
eneout_period = 10        # energy output period
# crdout_period = 0         # coordinates output period
# velout_period = 0         # velocities output period
"""

ATDYN_CTRL_ALL = """
[DYNAMICS]
integrator    = LEAP      # [LEAP,VVER, VVER_CG]
nsteps        = 100       # number of MD steps
timestep      = 0.001     # timestep (ps)
eneout_period = 10        # energy output period
# qmsave_period = 0         # Interval for saving QM files
# crdout_period = 0         # coordinates output period
"""


def test_parse_ctrl_all_extracts_allowed_values():
    ref = parse_ctrl_all(CGDYN_CTRL_ALL)
    assert ref["DYNAMICS"]["integrator"] == ["LEAP", "VVER"]


def test_parse_ctrl_all_registers_commented_out_keywords():
    ref = parse_ctrl_all(CGDYN_CTRL_ALL)
    assert "crdout_period" in ref["DYNAMICS"]
    assert ref["DYNAMICS"]["crdout_period"] is None  # no bracketed list -> unconstrained


def test_parse_ctrl_all_keyword_with_no_bracket_list_is_unconstrained():
    ref = parse_ctrl_all(CGDYN_CTRL_ALL)
    assert ref["DYNAMICS"]["nsteps"] is None


def test_validate_control_text_flags_unsupported_value():
    # This is the actual VVER_CG-on-cgdyn bug (DECISIONS.md, 2026-09-10),
    # reproduced directly: rendering with the WRONG engine's value against
    # the RIGHT engine's reference must be caught.
    text = "[DYNAMICS]\nintegrator     = VVER_CG\n"
    ref = parse_ctrl_all(CGDYN_CTRL_ALL)
    warnings = validate_control_text(text, ref)
    assert any("VVER_CG" in w and "not in this build's allowed values" in w for w in warnings)


def test_validate_control_text_passes_for_correct_engine_value():
    text = "[DYNAMICS]\nintegrator     = VVER\n"
    ref = parse_ctrl_all(CGDYN_CTRL_ALL)
    assert validate_control_text(text, ref) == []

    text_atdyn = "[DYNAMICS]\nintegrator     = VVER_CG\n"
    ref_atdyn = parse_ctrl_all(ATDYN_CTRL_ALL)
    assert validate_control_text(text_atdyn, ref_atdyn) == []


def test_validate_control_text_flags_unknown_keyword():
    text = "[DYNAMICS]\ntotally_made_up_keyword = 1\n"
    ref = parse_ctrl_all(CGDYN_CTRL_ALL)
    warnings = validate_control_text(text, ref)
    assert any("not a recognized keyword" in w for w in warnings)


def test_validate_control_text_flags_unknown_section():
    text = "[NOT_A_REAL_SECTION]\nintegrator = VVER\n"
    ref = parse_ctrl_all(CGDYN_CTRL_ALL)
    warnings = validate_control_text(text, ref)
    assert any("not found in the installed GENESIS" in w for w in warnings)


def test_validate_control_text_ignores_commented_lines_in_rendered_file():
    text = "[DYNAMICS]\n# integrator = VVER_CG\n"
    ref = parse_ctrl_all(CGDYN_CTRL_ALL)
    assert validate_control_text(text, ref) == []


def test_our_own_rendered_cgdyn_control_file_passes_against_real_reference():
    # The actual regression guard: render this app's own current
    # cgdyn-engine control file and validate it against the real
    # DYNAMICS block the user's installed cgdyn produced.
    cfg = ControlFileConfig(
        top_file="x.top", gro_file="x.gro", output_prefix="run",
        temperature_k=300.0, n_steps=1000, timestep_fs=10.0,
        output_frequency=100, langevin_friction=0.01, engine="cgdyn",
    )
    text = render_control_file(cfg, ModelType.HPS_SINGLE)
    ref = parse_ctrl_all(CGDYN_CTRL_ALL)
    warnings = validate_control_text(text, ref)
    integrator_warnings = [w for w in warnings if "integrator" in w]
    assert integrator_warnings == []


def test_validate_against_installed_genesis_reports_fetch_failure():
    # fake_wsl proxies to real bash; "not-a-real-engine" isn't installed
    # here, so the fetch itself fails -- must degrade to a warning, not
    # raise.
    bridge = WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)
    warnings = validate_against_installed_genesis(bridge, "not-a-real-engine", "[DYNAMICS]\nintegrator = VVER\n")
    assert len(warnings) == 1
    assert "could not run" in warnings[0]
