import os
from pathlib import Path

import numpy as np

from app.analysis import (
    write_analysis_control_file,
    run_analysis,
    run_rmsf_analysis,
    run_sasa_analysis,
    rmsf_inputs_available,
    sasa_inputs_available,
    write_sasa_control_file,
    parse_two_column_series,
    parse_contact_map,
    ANALYSIS_TOOLS,
)
from app.project import Project
from app.wsl import WslBridge

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")


def _bridge() -> WslBridge:
    return WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)


def _install_fake_binary(bin_dir: Path, name: str, script_body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/bash\nset -e\n{script_body}\n")
    path.chmod(0o755)


def test_write_analysis_control_file_rmsd(tmp_path: Path):
    project = Project(name="myproj", directory=str(tmp_path))
    filename = write_analysis_control_file("rmsd", project, str(tmp_path))
    assert filename == "rmsd.inp"
    text = (tmp_path / filename).read_text()
    assert "[INPUT]" in text
    assert "[TRAJECTORY]" in text
    assert "[OUTPUT]" in text
    assert "rmsd.txt" in text


def test_qvalue_uses_environment_fact_binary_name():
    assert ANALYSIS_TOOLS["qvalue"][0] == "qval_residcg_analysis"


def test_run_analysis_reports_failure_when_binary_missing(tmp_path: Path):
    project = Project(name="myproj", directory=str(tmp_path))
    result = run_analysis(_bridge(), "rmsd", project, str(tmp_path))
    assert not result.success
    assert result.output_path is None
    assert result.log


def test_parse_two_column_series():
    text = "# comment\n0 1.0\n1 1.5\n2 2.25\n\n"
    xs, ys = parse_two_column_series(text)
    assert list(xs) == [0.0, 1.0, 2.0]
    assert list(ys) == [1.0, 1.5, 2.25]


def test_parse_two_column_series_skips_malformed_lines():
    text = "not a number here\n0 1.0\n"
    xs, ys = parse_two_column_series(text)
    assert len(xs) == 1
    assert xs[0] == 0.0


def test_parse_contact_map():
    text = "1 0 1\n0 1 0\n1 0 1\n"
    matrix = parse_contact_map(text)
    assert matrix.shape == (3, 3)
    assert np.array_equal(matrix, np.array([[1, 0, 1], [0, 1, 0], [1, 0, 1]]))


def test_parse_contact_map_pads_ragged_rows():
    text = "1 0 1\n0 1\n"
    matrix = parse_contact_map(text)
    assert matrix.shape == (2, 3)


def test_contact_map_mode_variants_use_distinct_output_files(tmp_path: Path):
    project = Project(name="myproj", directory=str(tmp_path))
    final_filename = write_analysis_control_file("contact_map", project, str(tmp_path), mode="final")
    avg_filename = write_analysis_control_file("contact_map", project, str(tmp_path), mode="time_averaged")

    assert final_filename != avg_filename
    final_text = (tmp_path / final_filename).read_text()
    avg_text = (tmp_path / avg_filename).read_text()
    assert "contact_map_final.txt" in final_text
    assert "contact_map_time_averaged.txt" in avg_text
    # No GENESIS analysis tool control file confirmed against
    # mdgenesis.org has an "average" [OPTION] keyword (see
    # app/analysis.py's module docstring) -- the fabricated
    # "average = YES" line has been removed, not just moved.
    assert "average = YES" not in avg_text
    assert "[OPTION]" not in avg_text


def test_output_keyword_differs_per_tool():
    assert ANALYSIS_TOOLS["rmsd"][1] == "rmsfile"
    assert ANALYSIS_TOOLS["rg"][1] == "rgfile"
    assert ANALYSIS_TOOLS["contact_map"][1] == "outfile"
    assert ANALYSIS_TOOLS["density"][1] == "mapfile"
    assert ANALYSIS_TOOLS["qvalue"][1] == "qntfile"


# -- RMSF (avecrd_analysis -> flccrd_analysis) -------------------------------
def test_rmsf_inputs_available_requires_psf_and_pdb(tmp_path: Path):
    project = Project(name="myproj", directory=str(tmp_path))
    assert not rmsf_inputs_available(str(tmp_path), project)

    (tmp_path / "myproj_cg.psf").write_text("")
    assert not rmsf_inputs_available(str(tmp_path), project)  # still no .pdb

    (tmp_path / "myproj_cg.pdb").write_text("")
    assert rmsf_inputs_available(str(tmp_path), project)


def test_run_rmsf_analysis_reports_missing_inputs_without_calling_bridge(tmp_path: Path):
    project = Project(name="myproj", directory=str(tmp_path))
    result = run_rmsf_analysis(_bridge(), project, str(tmp_path))
    assert not result.success
    assert "psf" in result.log.lower()


def test_run_rmsf_analysis_full_pipeline_success(tmp_path: Path, monkeypatch):
    (tmp_path / "myproj_cg.psf").write_text("")
    (tmp_path / "myproj_cg.pdb").write_text("ATOM\n")
    project = Project(name="myproj", directory=str(tmp_path))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_binary(
        bin_dir,
        "avecrd_analysis",
        'inp="$1"; prefix="${inp%_avecrd.inp}"; '
        'touch "${prefix}_avecrd_ave.pdb" "${prefix}_avecrd_aft.pdb"',
    )
    _install_fake_binary(
        bin_dir,
        "flccrd_analysis",
        'inp="$1"; prefix="${inp%_flccrd.inp}"; '
        'printf "1 0.5\\n2 0.6\\n" > "${prefix}_rmsf.rms"',
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    result = run_rmsf_analysis(_bridge(), project, str(tmp_path))

    assert result.success, result.log
    xs, ys = parse_two_column_series(result.output_path.read_text())
    assert list(xs) == [1.0, 2.0]
    assert list(ys) == [0.5, 0.6]


def test_run_rmsf_analysis_stops_if_avecrd_step_fails(tmp_path: Path, monkeypatch):
    (tmp_path / "myproj_cg.psf").write_text("")
    (tmp_path / "myproj_cg.pdb").write_text("ATOM\n")
    project = Project(name="myproj", directory=str(tmp_path))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_binary(bin_dir, "avecrd_analysis", 'echo "boom" >&2; exit 1')
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    result = run_rmsf_analysis(_bridge(), project, str(tmp_path))
    assert not result.success
    assert "boom" in result.log


# -- SASA (sasa_analysis) -----------------------------------------------------
def test_sasa_control_file_has_confirmed_and_verify_marked_keywords(tmp_path: Path):
    project = Project(name="myproj", directory=str(tmp_path))
    filename = write_sasa_control_file(project, str(tmp_path), "/opt/genesis/radi_list", "myproj_cg.psf", "myproj_cg.pdb")
    text = (tmp_path / filename).read_text()
    assert "psffile = myproj_cg.psf" in text
    assert "radi_file = /opt/genesis/radi_list" in text
    assert "output_style = history" in text
    assert "# VERIFY" in text  # domain/num_cells sizing is explicitly flagged, not silently guessed


def test_run_sasa_analysis_requires_radius_file_setting(tmp_path: Path):
    (tmp_path / "myproj_cg.psf").write_text("")
    (tmp_path / "myproj_cg.pdb").write_text("ATOM\n")
    project = Project(name="myproj", directory=str(tmp_path))
    result = run_sasa_analysis(_bridge(), project, str(tmp_path), radius_file="")
    assert not result.success
    assert "radius file" in result.log.lower()


def test_run_sasa_analysis_success(tmp_path: Path, monkeypatch):
    (tmp_path / "myproj_cg.psf").write_text("")
    (tmp_path / "myproj_cg.pdb").write_text("ATOM\n")
    project = Project(name="myproj", directory=str(tmp_path))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_binary(
        bin_dir,
        "sasa_analysis",
        'inp="$1"; prefix="${inp%_sasa.inp}"; printf "0 12.3\\n1 12.5\\n" > "${prefix}_sasa.txt"',
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    result = run_sasa_analysis(_bridge(), project, str(tmp_path), radius_file="/opt/genesis/radi_list")

    assert result.success, result.log
    xs, ys = parse_two_column_series(result.output_path.read_text())
    assert list(xs) == [0.0, 1.0]
    assert list(ys) == [12.3, 12.5]
