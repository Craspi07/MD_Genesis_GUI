from pathlib import Path

from app.analysis import AnalysisRunResult
from app.project import Project, ModelType
from app.settings import Settings
from ui.tab_analysis import AnalysisTab


def _tab(tmp_path: Path, model_type=ModelType.AICG2P) -> AnalysisTab:
    project = Project(name="myproj", directory=str(tmp_path), model_type=model_type)
    settings = Settings()
    settings.distro = "Ubuntu-24.04"
    return AnalysisTab(project, str(tmp_path), settings)


def test_density_button_only_enabled_for_condensate(tmp_path: Path):
    tab = _tab(tmp_path, ModelType.AICG2P)
    assert not tab.density_button.isEnabled()

    tab2 = _tab(tmp_path, ModelType.HPS_CONDENSATE)
    assert tab2.density_button.isEnabled()


def test_on_analysis_finished_series_populates_results(tmp_path: Path):
    tab = _tab(tmp_path)
    output = tmp_path / "rmsd.txt"
    output.write_text("0 0.0\n1 0.1\n2 0.2\n")
    result = AnalysisRunResult(success=True, output_path=output, log="")

    tab._on_analysis_finished("rmsd", "rmsd", result, None)

    assert "rmsd" in tab._series_results
    series = tab._series_results["rmsd"]
    assert list(series.y) == [0.0, 0.1, 0.2]


def test_on_analysis_finished_contact_map_populates_matrix(tmp_path: Path):
    tab = _tab(tmp_path)
    output = tmp_path / "contact_map_final.txt"
    output.write_text("1 0\n0 1\n")
    result = AnalysisRunResult(success=True, output_path=output, log="")

    tab._on_analysis_finished("contact_map_final", "contact_map", result, "final")

    assert "contact_map_final" in tab._matrix_results
    assert tab._matrix_results["contact_map_final"].matrix.shape == (2, 2)


def test_on_analysis_finished_failure_sets_status(tmp_path: Path):
    tab = _tab(tmp_path)
    result = AnalysisRunResult(success=False, output_path=None, log="binary not found")

    tab._on_analysis_finished("rmsd", "rmsd", result, None)

    assert "failed" in tab.status_label.text()


def test_plot_temperature_energy_reads_run_log(tmp_path: Path):
    tab = _tab(tmp_path)
    log_text = (
        "INFO:       STEP       TIME   TOTAL_ENE   POTENTIAL_ENE   TEMPERATURE\n"
        "INFO:          0     0.0000    -1234.50       -1345.60        301.20\n"
        "INFO:       1000     1.0000    -1235.10       -1346.05        300.80\n"
    )
    (tmp_path / "run.log").write_text(log_text)

    tab._plot_temperature_energy()

    assert "timeseries_TOTAL_ENE" in tab._series_results
    assert "timeseries_TEMPERATURE" in tab._series_results
    assert list(tab._series_results["timeseries_TEMPERATURE"].y) == [301.20, 300.80]


def test_plot_temperature_energy_missing_log(tmp_path: Path):
    tab = _tab(tmp_path)
    tab._plot_temperature_energy()
    assert "No run.log" in tab.status_label.text()
