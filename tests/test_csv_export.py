from pathlib import Path

import numpy as np

from app.csv_export import export_to_csv
from app.excel_export import AnalysisSeries, AnalysisMatrix


def test_export_series_writes_header_and_rows(tmp_path: Path):
    series = {
        "rmsd": AnalysisSeries(label="RMSD", x_label="Frame", y_label="RMSD (nm)", x=np.array([0.0, 1.0]), y=np.array([0.1, 0.2]))
    }
    written = export_to_csv(series, {}, str(tmp_path))
    assert len(written) == 1
    text = Path(written[0]).read_text()
    assert text.splitlines() == ["Frame,RMSD (nm)", "0.0,0.1", "1.0,0.2"]


def test_export_matrix_writes_rows_without_header(tmp_path: Path):
    matrices = {"cm": AnalysisMatrix(label="Contact map", matrix=np.array([[1, 0], [0, 1]]))}
    written = export_to_csv({}, matrices, str(tmp_path))
    assert len(written) == 1
    text = Path(written[0]).read_text()
    assert text.splitlines() == ["1,0", "0,1"]


def test_export_sanitizes_unsafe_filename_characters(tmp_path: Path):
    series = {
        "x": AnalysisSeries(label="Contact map (final frame)", x_label="a", y_label="b", x=np.array([0.0]), y=np.array([1.0]))
    }
    written = export_to_csv(series, {}, str(tmp_path))
    assert Path(written[0]).name == "Contact map (final frame).csv"


def test_export_creates_output_directory_if_missing(tmp_path: Path):
    series = {"x": AnalysisSeries(label="X", x_label="a", y_label="b", x=np.array([0.0]), y=np.array([1.0]))}
    out_dir = tmp_path / "nested" / "dir"
    written = export_to_csv(series, {}, str(out_dir))
    assert Path(written[0]).exists()
