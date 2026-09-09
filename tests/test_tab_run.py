from pathlib import Path

from app.log_parser import LogRecord
from app.project import Project
from app.settings import Settings
from ui.tab_run import RunTab


def _tab(tmp_path: Path) -> RunTab:
    project = Project(name="myproj", directory=str(tmp_path))
    project.parameters.n_steps = 10000
    settings = Settings()
    settings.distro = "Ubuntu-24.04"
    return RunTab(project, str(tmp_path), settings)


def test_run_tab_initial_state(tmp_path: Path):
    tab = _tab(tmp_path)
    assert tab.start_button.isEnabled()
    assert not tab.stop_button.isEnabled()
    assert tab.progress_bar.maximum() == 10000


def test_run_tab_updates_progress_and_plot_on_new_records(tmp_path: Path):
    tab = _tab(tmp_path)
    records = [
        LogRecord(step=0, time_ps=0.0, values={"TOTAL_ENE": -100.0, "POTENTIAL_ENE": -150.0, "TEMPERATURE": 300.0}),
        LogRecord(step=1000, time_ps=1.0, values={"TOTAL_ENE": -101.0, "POTENTIAL_ENE": -151.0, "TEMPERATURE": 299.5}),
    ]
    tab._on_new_records(records)

    assert tab.progress_bar.value() == 1000
    assert "POTENTIAL_ENE" in tab._energy_series
    assert tab._energy_series["POTENTIAL_ENE"] == [-150.0, -151.0]
    assert "TOTAL_ENE" in tab.canvas._lines


def test_run_tab_status_changed_to_finished_enables_start(tmp_path: Path):
    tab = _tab(tmp_path)
    tab.start_button.setEnabled(False)
    tab.stop_button.setEnabled(True)
    tab._on_status_changed("finished")
    assert tab.start_button.isEnabled()
    assert not tab.stop_button.isEnabled()
    assert "Finished" in tab.status_label.text() or "finished" in tab.status_label.text()


def test_run_tab_raw_output_appended_to_log_view(tmp_path: Path):
    tab = _tab(tmp_path)
    tab._on_raw_output("INFO: some log line\n")
    assert "INFO: some log line" in tab.raw_log_view.toPlainText()


def test_run_tab_continue_button_disabled_without_restart_file(tmp_path: Path):
    tab = _tab(tmp_path)
    assert not tab.continue_button.isEnabled()


def test_run_tab_continue_button_enabled_with_restart_file(tmp_path: Path):
    (tmp_path / "myproj.rst").write_text("")
    tab = _tab(tmp_path)
    assert tab.continue_button.isEnabled()
