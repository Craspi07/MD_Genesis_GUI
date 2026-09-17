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


# Real `atdyn -h ctrl_all` output, transcribed directly from GENESIS
# 2.1.6.1's own source (github.com/genesis-release-r-ccs/genesis,
# src/atdyn/at_ensemble.fpp's show_ctrl_ensemble and
# src/atdyn/at_energy.fpp's show_ctrl_energy, 'md' run_mode, show_all=
# true) -- see DECISIONS.md and app/ctrl_reference.py's module docstring
# for the two false-positive bugs this reproduces.
REAL_ATDYN_ENSEMBLE_AND_ENERGY_CTRL_ALL = """
[ENSEMBLE]
ensemble      = NVE       # [NVE,NVT,NPT,NPAT,NPgT]
tpcontrol     = NO        # [NO,BERENDSEN,BUSSI,LANGEVIN]
# temperature   = 298.15    # initial and target temperature (K)
# pressure      = 1.0       # target pressure (atm)
# gamma         = 0.0       # target surface tension (dyn/cm)
# tau_t         = 5.0       # temperature coupling time (ps) in [BERENDSEN,NOSE-HOOVER,BUSSI]
# tau_p         = 5.0       # pressure coupling time (ps)    in [BERENDSEN,BUSSI]
# compressibility = 4.63e-5 # compressibility (atm-1) in [BERENDSEN]
# gamma_t       = 1.0       # thermostat friction (ps-1) in [LANGEVIN]
# gamma_p       = 0.1       # barostat friction (ps-1)   in [LANGEVIN]
# isotropy      = ISO       # [ISO,SEMI-ISO,ANISO,XY-FIXED]

[ENERGY]
forcefield       = CHARMM  # [CHARMM,AAGO,CAGO,KBGO,AMBER,GROAMBER,GROMARTINI]
electrostatic    = PME     # [CUTOFF,PME]
switchdist       = 10.0    # switch distance
cutoffdist       = 12.0    # cutoff distance
pairlistdist     = 13.5    # pair-list distance
"""


def test_parse_ctrl_all_does_not_treat_a_cross_reference_bracket_as_the_keywords_own_enum():
    # The real GENESIS bug this guards against: gamma_t's own comment
    # documents which *tpcontrol* value it applies to ("in [LANGEVIN]"),
    # not gamma_t's own allowed values -- gamma_t is a float.
    ref = parse_ctrl_all(REAL_ATDYN_ENSEMBLE_AND_ENERGY_CTRL_ALL)
    assert ref["ENSEMBLE"]["gamma_t"] is None
    assert ref["ENSEMBLE"]["gamma_p"] is None
    assert ref["ENSEMBLE"]["tau_t"] is None


def test_parse_ctrl_all_still_extracts_a_bare_bracket_enum():
    ref = parse_ctrl_all(REAL_ATDYN_ENSEMBLE_AND_ENERGY_CTRL_ALL)
    assert ref["ENSEMBLE"]["tpcontrol"] == ["NO", "BERENDSEN", "BUSSI", "LANGEVIN"]
    assert ref["ENERGY"]["forcefield"] == ["CHARMM", "AAGO", "CAGO", "KBGO", "AMBER", "GROAMBER", "GROMARTINI"]


def test_validate_control_text_no_longer_flags_gamma_t_against_the_wrong_enum():
    text = "[ENSEMBLE]\nensemble = NVT\ntpcontrol = LANGEVIN\ngamma_t = 0.01\n"
    ref = parse_ctrl_all(REAL_ATDYN_ENSEMBLE_AND_ENERGY_CTRL_ALL)
    warnings = validate_control_text(text, ref)
    assert not any("gamma_t" in w for w in warnings)


def test_validate_control_text_annotates_the_known_residcg_doc_gap():
    # forcefield=RESIDCG is real, valid GENESIS 2.1.6 input (confirmed
    # against ForceFieldTypes/read_ctrl_energy in the real source, and
    # against tutorial 11.1's own pro.inp) -- atdyn's -h ctrl_all just
    # never had its forcefield comment updated to mention it.
    text = "[ENERGY]\nforcefield = RESIDCG\n"
    ref = parse_ctrl_all(REAL_ATDYN_ENSEMBLE_AND_ENERGY_CTRL_ALL)
    warnings = validate_control_text(text, ref)
    assert len(warnings) == 1
    assert "not in this build's allowed values" in warnings[0]
    assert "false positive" in warnings[0]


def test_validate_control_text_annotates_the_known_cg_keyword_doc_gap():
    text = "[ENERGY]\nforcefield = RESIDCG\ncg_sol_ionic_strength = 0.15\n"
    ref = parse_ctrl_all(REAL_ATDYN_ENSEMBLE_AND_ENERGY_CTRL_ALL)
    warnings = validate_control_text(text, ref)
    cg_warnings = [w for w in warnings if "cg_sol_ionic_strength" in w]
    assert len(cg_warnings) == 1
    assert "not a recognized keyword" in cg_warnings[0]
    assert "false positive" in cg_warnings[0]


def test_validate_against_installed_genesis_reports_fetch_failure():
    # fake_wsl proxies to real bash; "not-a-real-engine" isn't installed
    # here, so the fetch itself fails -- must degrade to a warning, not
    # raise.
    bridge = WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)
    warnings = validate_against_installed_genesis(bridge, "not-a-real-engine", "[DYNAMICS]\nintegrator = VVER\n")
    assert len(warnings) == 1
    assert "could not run" in warnings[0]
