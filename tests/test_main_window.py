from pathlib import Path

from PyQt5.QtWidgets import QMessageBox

from app.project import Project
from ui.main_window import MainWindow


def _make_project_dir(tmp_path: Path, name: str) -> Path:
    project_dir = tmp_path / name
    project_dir.mkdir()
    Project(name=name, directory=f"~/genesis_projects/{name}").save(str(project_dir))
    return project_dir


def test_main_window_starts_on_dashboard_tab(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    assert window.tabs.tabText(0) == "Dashboard"
    assert window.tabs.count() == 1


def test_opening_a_project_adds_tabs_after_dashboard(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    project_dir = _make_project_dir(tmp_path, "proj1")
    project = Project.load(str(project_dir))

    window.open_project(project, str(project_dir))

    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["Dashboard", "Files", "Run", "Analysis"]
    assert window.tabs.currentWidget() is window.files_tab


def test_opening_a_second_project_replaces_tabs_not_dashboard(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    dir_a = _make_project_dir(tmp_path, "proj_a")
    dir_b = _make_project_dir(tmp_path, "proj_b")

    window.open_project(Project.load(str(dir_a)), str(dir_a))
    window.open_project(Project.load(str(dir_b)), str(dir_b))

    assert window.tabs.count() == 4
    assert window.current_project.name == "proj_b"


def test_project_tree_lists_all_recent_projects(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    dir_a = _make_project_dir(tmp_path, "proj_a")
    dir_b = _make_project_dir(tmp_path, "proj_b")
    window.settings.recent_projects = [str(dir_a), str(dir_b)]

    window.refresh_project_views()

    assert window.project_tree.topLevelItemCount() == 2
    labels = [window.project_tree.topLevelItem(i).text(0) for i in range(2)]
    assert any("proj_a" in label for label in labels)
    assert any("proj_b" in label for label in labels)


def test_double_clicking_tree_item_opens_project(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    project_dir = _make_project_dir(tmp_path, "proj_tree")
    window.settings.recent_projects = [str(project_dir)]
    window.refresh_project_views()

    item = window.project_tree.topLevelItem(0)
    window._on_tree_item_double_clicked(item, 0)

    assert window.current_project is not None
    assert window.current_project.name == "proj_tree"


def test_open_project_via_file_menu_loads_and_opens_project(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    project_dir = _make_project_dir(tmp_path, "reopened_proj")

    monkeypatch.setattr(
        "PyQt5.QtWidgets.QFileDialog.getExistingDirectory", staticmethod(lambda *a, **k: str(project_dir))
    )

    window._on_open_project()

    assert window.current_project is not None
    assert window.current_project.name == "reopened_proj"
    assert str(project_dir) in window.settings.recent_projects
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["Dashboard", "Files", "Run", "Analysis"]


def test_open_project_cancelled_dialog_does_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()

    monkeypatch.setattr("PyQt5.QtWidgets.QFileDialog.getExistingDirectory", staticmethod(lambda *a, **k: ""))

    window._on_open_project()

    assert window.current_project is None
    assert window.tabs.count() == 1


def test_open_project_invalid_directory_shows_message(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    not_a_project = tmp_path / "not_a_project"
    not_a_project.mkdir()

    monkeypatch.setattr(
        "PyQt5.QtWidgets.QFileDialog.getExistingDirectory", staticmethod(lambda *a, **k: str(not_a_project))
    )
    warned = {}
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warned.__setitem__("called", True))
    )

    window._on_open_project()

    assert warned.get("called") is True
    assert window.current_project is None


def test_new_project_load_failure_shows_message_instead_of_silent_no_op(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()

    class FakeWizard:
        class review_page:
            class name_edit:
                @staticmethod
                def text():
                    return "broken_project"

        @staticmethod
        def exec_():
            from PyQt5.QtWidgets import QDialog

            return QDialog.Accepted

    monkeypatch.setattr("ui.wizard_new_project.NewProjectWizard", lambda settings, parent: FakeWizard())
    monkeypatch.setattr(
        "app.project_creation.local_directory_for",
        lambda settings, name: str(tmp_path / "nonexistent_dir"),
    )
    warned = {}
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: warned.__setitem__("called", True)),
    )

    window._on_new_project()

    assert warned.get("called") is True


def test_project_deleted_signal_resets_to_dashboard_when_current_project(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    project_dir = _make_project_dir(tmp_path, "to_delete")
    window.open_project(Project.load(str(project_dir)), str(project_dir))
    assert window.tabs.count() == 4

    window._on_project_deleted(str(project_dir))

    assert window.current_project is None
    assert window.current_project_dir is None
    assert window.tabs.count() == 1
    assert window.tabs.currentIndex() == 0


def test_project_deleted_signal_for_a_different_project_leaves_open_project_alone(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    dir_a = _make_project_dir(tmp_path, "kept_open")
    dir_b = _make_project_dir(tmp_path, "deleted_elsewhere")
    window.open_project(Project.load(str(dir_a)), str(dir_a))

    window._on_project_deleted(str(dir_b))

    assert window.current_project.name == "kept_open"
    assert window.tabs.count() == 4


def test_project_renamed_signal_reopens_project_when_it_was_current(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    old_dir = _make_project_dir(tmp_path, "old_name")
    project = Project.load(str(old_dir))
    window.open_project(project, str(old_dir))

    new_dir = tmp_path / "new_name"
    new_dir.mkdir()
    renamed_project = Project(name="new_name", directory=str(new_dir))
    renamed_project.save(str(new_dir))

    window._on_project_renamed(str(old_dir), renamed_project, str(new_dir))

    assert window.current_project.name == "new_name"
    assert window.current_project_dir == str(new_dir)
    assert window.tabs.count() == 4


def test_project_renamed_signal_for_a_different_project_just_refreshes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.settings.QSettings", lambda *a, **k: _FakeQSettings())
    window = MainWindow()
    dir_a = _make_project_dir(tmp_path, "kept_open")
    window.open_project(Project.load(str(dir_a)), str(dir_a))

    other_project = Project(name="renamed_elsewhere", directory=str(tmp_path / "elsewhere"))
    window._on_project_renamed(str(tmp_path / "old_elsewhere"), other_project, str(tmp_path / "elsewhere"))

    assert window.current_project.name == "kept_open"


class _FakeQSettings:
    """Avoids touching the real on-disk QSettings store from tests."""

    def __init__(self):
        self._data = {}

    def value(self, key, default=None, type=None):
        val = self._data.get(key, default)
        if type is not None and val is not None:
            try:
                return type(val)
            except (TypeError, ValueError):
                return val
        return val

    def setValue(self, key, value):
        self._data[key] = value

    def sync(self):
        pass
