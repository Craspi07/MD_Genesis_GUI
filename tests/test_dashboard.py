from pathlib import Path

from app.project import Project
from app.settings import Settings
from ui.dashboard import ProjectDashboard


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


def test_refresh_reflects_updated_status(tmp_path: Path):
    project_dir = _make_project_dir(tmp_path, "delta", status="running")
    dashboard = ProjectDashboard(_settings([str(project_dir)]))
    assert dashboard.table.item(0, 2).text() == "running"

    project = Project.load(str(project_dir))
    project.last_run_status = "finished"
    project.save(str(project_dir))
    dashboard.refresh()

    assert dashboard.table.item(0, 2).text() == "finished"
