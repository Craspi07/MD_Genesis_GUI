from pathlib import Path

from PyQt5.QtWidgets import QInputDialog, QMessageBox

from app.project import Project
from app.settings import Settings
from app.wsl import WslBridge
from ui.dashboard import DeleteProjectWorker, ProjectDashboard, RenameProjectWorker

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")


def _bridge() -> WslBridge:
    return WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)


def _make_project_dir(tmp_path: Path, name: str, status: str = "not_started") -> Path:
    project_dir = tmp_path / name
    project_dir.mkdir()
    project = Project(name=name, directory=f"~/genesis_projects/{name}")
    project.last_run_status = status
    project.save(str(project_dir))
    return project_dir


def _settings(recent_projects) -> Settings:
    s = Settings()
    s.recent_projects = list(recent_projects)
    return s


def test_dashboard_lists_recent_projects(tmp_path: Path):
    dir_a = _make_project_dir(tmp_path, "alpha", status="finished")
    dir_b = _make_project_dir(tmp_path, "beta", status="running")
    dashboard = ProjectDashboard(_settings([str(dir_a), str(dir_b)]))

    assert dashboard.table.rowCount() == 2
    assert dashboard.table.item(0, 0).text() == "alpha"
    assert dashboard.table.item(0, 2).text() == "finished"
    assert dashboard.table.item(1, 0).text() == "beta"
    assert dashboard.table.item(1, 2).text() == "running"


def test_dashboard_shows_missing_project_without_dropping_it(tmp_path: Path):
    missing_dir = tmp_path / "does_not_exist"
    dashboard = ProjectDashboard(_settings([str(missing_dir)]))

    assert dashboard.table.rowCount() == 1
    assert dashboard.table.item(0, 2).text() == "missing / unreadable"


def test_double_clicking_a_row_emits_open_request(tmp_path: Path):
    project_dir = _make_project_dir(tmp_path, "gamma")
    dashboard = ProjectDashboard(_settings([str(project_dir)]))

    received = []
    dashboard.project_open_requested.connect(lambda project, path: received.append((project, path)))
    dashboard._on_row_double_clicked(0, 0)

    assert len(received) == 1
    project, path = received[0]
    assert project.name == "gamma"
    assert path == str(project_dir)


def test_double_clicking_a_missing_row_reports_status_instead_of_crashing(tmp_path: Path):
    missing_dir = tmp_path / "does_not_exist"
    dashboard = ProjectDashboard(_settings([str(missing_dir)]))

    received = []
    dashboard.project_open_requested.connect(lambda project, path: received.append((project, path)))
    dashboard._on_row_double_clicked(0, 0)

    assert received == []
    assert "missing or unreadable" in dashboard.status_label.text()


def test_remove_selected_updates_settings_and_table(tmp_path: Path):
    dir_a = _make_project_dir(tmp_path, "alpha")
    dir_b = _make_project_dir(tmp_path, "beta")
    settings = _settings([str(dir_a), str(dir_b)])
    dashboard = ProjectDashboard(settings)

    dashboard.table.selectRow(0)
    dashboard._on_remove_selected()

    assert str(dir_a) not in settings.recent_projects
    assert dashboard.table.rowCount() == 1
    assert dashboard.table.item(0, 0).text() == "beta"


def _make_real_project_dir(tmp_path: Path, name: str, status: str = "not_started") -> Path:
    # Unlike _make_project_dir, project.directory points at the real tmp_path
    # dir itself (not the "~/genesis_projects/<name>" placeholder) so the
    # fake WSL bridge's `rm -rf`/`mv` land here instead of a real home dir --
    # same pattern as tests/test_project_management.py.
    project_dir = tmp_path / name
    project_dir.mkdir()
    project = Project(name=name, directory=str(project_dir))
    project.last_run_status = status
    project.save(str(project_dir))
    return project_dir


def test_delete_project_worker_removes_directory_and_emits_finished(tmp_path: Path):
    project_dir = _make_real_project_dir(tmp_path, "worker_delete")
    project = Project.load(str(project_dir))
    project.directory = str(project_dir)

    worker = DeleteProjectWorker(_bridge(), project)
    results = {}
    worker.finished.connect(lambda success, message: results.update(success=success, message=message))
    worker.run()

    assert results["success"] is True
    assert not project_dir.exists()


def test_rename_project_worker_emits_finished_tuple(tmp_path: Path, monkeypatch):
    project_dir = _make_real_project_dir(tmp_path, "worker_rename")
    settings = Settings()
    settings.distro = "Ubuntu-24.04"
    monkeypatch.setattr(Settings, "projects_root_wsl", lambda self: str(tmp_path))
    monkeypatch.setattr(
        "app.project_management.local_directory_for", lambda s, name: str(tmp_path / name)
    )
    project = Project.load(str(project_dir))
    project.directory = str(project_dir)

    worker = RenameProjectWorker(_bridge(), settings, project, "worker_renamed")
    results = {}
    worker.finished.connect(
        lambda success, message, new_dir: results.update(success=success, message=message, new_dir=new_dir)
    )
    worker.run()

    assert results["success"] is True
    assert results["new_dir"] == str(tmp_path / "worker_renamed")


def test_on_delete_finished_removes_from_recent_projects_and_emits_signal(tmp_path: Path):
    dir_a = _make_project_dir(tmp_path, "alpha")
    settings = _settings([str(dir_a)])
    dashboard = ProjectDashboard(settings)

    received = []
    dashboard.project_deleted.connect(received.append)
    dashboard._on_delete_finished(True, "Deleted 'alpha'.", str(dir_a))

    assert str(dir_a) not in settings.recent_projects
    assert received == [str(dir_a)]


def test_on_delete_finished_failure_keeps_recent_projects_and_does_not_emit(tmp_path: Path):
    dir_a = _make_project_dir(tmp_path, "alpha")
    settings = _settings([str(dir_a)])
    dashboard = ProjectDashboard(settings)

    received = []
    dashboard.project_deleted.connect(received.append)
    dashboard._on_delete_finished(False, "Could not delete.", str(dir_a))

    assert str(dir_a) in settings.recent_projects
    assert received == []


def test_on_rename_finished_replaces_recent_projects_entry_and_emits_signal(tmp_path: Path):
    dir_a = _make_project_dir(tmp_path, "alpha")
    settings = _settings([str(dir_a)])
    settings.last_project = str(dir_a)
    dashboard = ProjectDashboard(settings)
    project = Project.load(str(dir_a))
    new_dir = str(tmp_path / "renamed")

    received = []
    dashboard.project_renamed.connect(lambda old, proj, new: received.append((old, proj, new)))
    dashboard._on_rename_finished(True, "Renamed to 'renamed'.", str(dir_a), project, new_dir)

    assert str(dir_a) not in settings.recent_projects
    assert new_dir in settings.recent_projects
    assert settings.last_project == new_dir
    assert received == [(str(dir_a), project, new_dir)]


def test_delete_selected_declined_confirmation_does_not_start_worker(tmp_path: Path, monkeypatch):
    dir_a = _make_real_project_dir(tmp_path, "alpha")
    settings = _settings([str(dir_a)])
    dashboard = ProjectDashboard(settings)
    dashboard.table.selectRow(0)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))

    dashboard._on_delete_selected()

    assert dashboard._thread is None
    assert dir_a.exists()
    assert str(dir_a) in settings.recent_projects


def test_delete_selected_missing_project_falls_back_to_remove_from_list(tmp_path: Path):
    missing_dir = tmp_path / "does_not_exist"
    settings = _settings([str(missing_dir)])
    dashboard = ProjectDashboard(settings)
    dashboard.table.selectRow(0)

    dashboard._on_delete_selected()

    assert str(missing_dir) not in settings.recent_projects
    assert dashboard.table.rowCount() == 0


def test_rename_selected_cancelled_dialog_does_not_start_worker(tmp_path: Path, monkeypatch):
    dir_a = _make_real_project_dir(tmp_path, "alpha")
    settings = _settings([str(dir_a)])
    dashboard = ProjectDashboard(settings)
    dashboard.table.selectRow(0)

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("ignored", False)))

    dashboard._on_rename_selected()

    assert dashboard._thread is None
    assert dir_a.exists()


def test_rename_selected_same_name_is_a_no_op(tmp_path: Path, monkeypatch):
    dir_a = _make_real_project_dir(tmp_path, "alpha")
    settings = _settings([str(dir_a)])
    dashboard = ProjectDashboard(settings)
    dashboard.table.selectRow(0)

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("alpha", True)))

    dashboard._on_rename_selected()

    assert dashboard._thread is None


def test_refresh_reflects_updated_status(tmp_path: Path):
    project_dir = _make_project_dir(tmp_path, "delta", status="running")
    dashboard = ProjectDashboard(_settings([str(project_dir)]))
    assert dashboard.table.item(0, 2).text() == "running"

    project = Project.load(str(project_dir))
    project.last_run_status = "finished"
    project.save(str(project_dir))
    dashboard.refresh()

    assert dashboard.table.item(0, 2).text() == "finished"
