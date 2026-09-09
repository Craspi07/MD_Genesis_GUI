from pathlib import Path

import numpy as np

from app.analysis import (
    write_analysis_control_file,
    run_analysis,
    parse_two_column_series,
    parse_contact_map,
    ANALYSIS_TOOLS,
)
from app.project import Project
from app.wsl import WslBridge

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")


def _bridge() -> WslBridge:
    return WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)


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
