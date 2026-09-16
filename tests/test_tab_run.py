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
    assert "TEMPERATURE" in tab.canvas._lines2  # Roadmap Phase 6: separate y-axis
    assert "TEMPERATURE" not in tab.canvas._lines


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


def test_run_tab_continue_regenerates_control_file_with_restart_file(tmp_path: Path, monkeypatch):
    (tmp_path / "myproj.rst").write_text("")
    (tmp_path / "myproj.top").write_text("[ molecules ]\nMOL 1\n")
    (tmp_path / "myproj.gro").write_text("title\n0\n0.0 0.0 0.0\n")
    tab = _tab(tmp_path)
    monkeypatch.setattr(tab.runner, "start", lambda is_continuation=False: None)

    tab._on_continue()

    text = (tmp_path / "run.inp").read_text()
    assert "rstfile    = myproj.rst" in text


def test_run_tab_continue_works_for_all_atom_project(tmp_path: Path, monkeypatch):
    from app.project import ModelType

    (tmp_path / "myproj.rst").write_text("")
    (tmp_path / "top_all36_prot.rtf").write_text("* top\n")
    (tmp_path / "par_all36m_prot.prm").write_text("* par\n")
    (tmp_path / "input.psf").write_text("PSF\n")
    (tmp_path / "input.pdb").write_text("ATOM\n")

    project = Project(name="myproj", directory=str(tmp_path), model_type=ModelType.ALL_ATOM_CHARMM)
    project.parameters.n_steps = 10000
    project.aa_top_source_paths = ["top_all36_prot.rtf"]
    project.aa_par_source_paths = ["par_all36m_prot.prm"]
    project.aa_psf_source_path = "input.psf"
    project.aa_pdb_source_path = "input.pdb"
    project.aa_box_x = 68.26
    project.aa_box_y = 80.24
    project.aa_box_z = 66.59
    settings = Settings()
    settings.distro = "Ubuntu-24.04"
    tab = RunTab(project, str(tmp_path), settings)
    monkeypatch.setattr(tab.runner, "start", lambda is_continuation=False: None)

    tab._on_continue()  # must not raise

    text = (tmp_path / "run.inp").read_text()
    assert "forcefield          = CHARMM" in text
    assert "rstfile = myproj.rst" in text
