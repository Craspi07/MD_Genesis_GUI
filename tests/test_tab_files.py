from pathlib import Path

from PyQt5.QtWidgets import QMessageBox

from app.project import Project
from app.control_file import ControlFileConfig, write_control_file
from app.wsl import WslBridge
from ui.tab_files import FilesTab, ValidateWorker

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")


def _make_project_dir(tmp_path: Path) -> Path:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    project = Project(name="myproj", directory="~/genesis_projects/myproj")
    project.save(str(project_dir))

    config = ControlFileConfig(
        top_file="myproj.top",
        gro_file="myproj.gro",
        output_prefix="myproj",
        temperature_k=300.0,
        n_steps=1000,
        timestep_fs=10.0,
        output_frequency=100,
        langevin_friction=0.01,
        box_x=180.0,
        box_y=180.0,
        box_z=180.0,
    )
    write_control_file(config, project.model_type, str(project_dir))
    (project_dir / "myproj.top").write_text("[ molecules ]\nMOL 1\n")
    return project_dir


def test_files_tab_lists_files_excluding_project_json(tmp_path: Path):
    project_dir = _make_project_dir(tmp_path)
    project = Project.load(str(project_dir))
    tab = FilesTab(project, str(project_dir))

    names = [tab.file_list.item(i).text() for i in range(tab.file_list.count())]
    assert "run.inp" in names
    assert "myproj.top" in names
    assert "project.json" not in names


def test_files_tab_run_inp_is_editable_others_readonly(tmp_path: Path):
    project_dir = _make_project_dir(tmp_path)
    project = Project.load(str(project_dir))
    tab = FilesTab(project, str(project_dir))

    items = {tab.file_list.item(i).text(): tab.file_list.item(i) for i in range(tab.file_list.count())}
    tab.file_list.setCurrentItem(items["run.inp"])
    assert not tab.editor.isReadOnly()

    tab.file_list.setCurrentItem(items["myproj.top"])
    assert tab.editor.isReadOnly()


def test_files_tab_validate_button_only_enabled_for_run_inp(tmp_path: Path):
    project_dir = _make_project_dir(tmp_path)
    project = Project.load(str(project_dir))
    tab = FilesTab(project, str(project_dir))

    items = {tab.file_list.item(i).text(): tab.file_list.item(i) for i in range(tab.file_list.count())}
    tab.file_list.setCurrentItem(items["run.inp"])
    assert tab.validate_button.isEnabled()

    tab.file_list.setCurrentItem(items["myproj.top"])
    assert not tab.validate_button.isEnabled()


def test_validate_worker_emits_warnings():
    bridge = WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)
    worker = ValidateWorker(bridge, "not-a-real-engine", "[DYNAMICS]\nintegrator = VVER\n")
    results = {}
    worker.finished.connect(lambda warnings: results.__setitem__("warnings", warnings))
    worker.run()
    assert "warnings" in results
    assert len(results["warnings"]) == 1
    assert "could not run" in results["warnings"][0]


def test_files_tab_save_marks_manual_edit_and_regenerate_clears_it(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    project_dir = _make_project_dir(tmp_path)
    project = Project.load(str(project_dir))
    tab = FilesTab(project, str(project_dir))

    items = {tab.file_list.item(i).text(): tab.file_list.item(i) for i in range(tab.file_list.count())}
    tab.file_list.setCurrentItem(items["run.inp"])
    tab.editor.setPlainText("; hand edited\n")
    tab._on_save()

    assert "run.inp" in tab.project.files_with_manual_edits
    assert (project_dir / "run.inp").read_text() == "; hand edited\n"

    reloaded = Project.load(str(project_dir))
    assert "run.inp" in reloaded.files_with_manual_edits

    tab._on_regenerate()
    assert "run.inp" not in tab.project.files_with_manual_edits
    assert (project_dir / "run.inp").read_text() != "; hand edited\n"
