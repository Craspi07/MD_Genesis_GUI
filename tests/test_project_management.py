from pathlib import Path

import pytest

from app.project import Project, InputMode, ModelType
from app.project_creation import copy_all_atom_files
from app.project_management import delete_project, rename_project
from app.settings import Settings
from app.wsl import WslBridge

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")


def _bridge() -> WslBridge:
    return WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)


@pytest.fixture
def settings(tmp_path: Path, monkeypatch) -> Settings:
    s = Settings()
    s.distro = "Ubuntu-24.04"
    s.linux_user = "biplab"
    # The real app's "WSL-side" project root (~/genesis_projects, used by
    # rename_project's `mv`) and its "local-side" mirror (a \\wsl$ UNC path,
    # used for project.json/run.inp) are the same underlying directory
    # content, reached two different ways. This dev container has neither a
    # real WSL mount nor a real home directory to touch, so both are pointed
    # at the same tmp_path root -- consistent with how the fake bridge in
    # tests/fixtures/fake_wsl.py runs commands directly against the local
    # filesystem (see test_run_minimization_success's `project.directory =
    # str(tmp_path)` for the same pattern).
    monkeypatch.setattr(Settings, "projects_root_wsl", lambda self: str(tmp_path))
    monkeypatch.setattr(
        "app.project_management.local_directory_for",
        lambda settings, name: str(tmp_path / name),
    )
    return s


def _all_atom_project(tmp_path: Path, directory: Path) -> Project:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "top_all36_prot.rtf").write_text("* topology\n")
    (source_dir / "par_all36m_prot.prm").write_text("* parameters\n")
    (source_dir / "input.psf").write_text("PSF\n")
    (source_dir / "input.pdb").write_text("ATOM\n")

    project = Project(
        name="myaa",
        directory=str(directory),  # real path so the fake bridge's "mv"/"cd" land here
        model_type=ModelType.ALL_ATOM_CHARMM,
        input_mode=InputMode.ALL_ATOM_PREBUILT,
    )
    project.aa_top_source_paths = [str(source_dir / "top_all36_prot.rtf")]
    project.aa_par_source_paths = [str(source_dir / "par_all36m_prot.prm")]
    project.aa_psf_source_path = str(source_dir / "input.psf")
    project.aa_pdb_source_path = str(source_dir / "input.pdb")
    project.aa_box_x = 68.26
    project.aa_box_y = 80.24
    project.aa_box_z = 66.59

    directory.mkdir(parents=True, exist_ok=True)
    copy_all_atom_files(project, str(directory))
    project.save(str(directory))
    return project


# -- delete_project -----------------------------------------------------------


def test_delete_project_removes_the_directory(tmp_path: Path, settings: Settings):
    project_dir = tmp_path / "myaa"
    project = _all_atom_project(tmp_path, project_dir)
    assert project_dir.exists()

    result = delete_project(_bridge(), project)

    assert result.success
    assert not project_dir.exists()


def test_delete_project_refuses_while_running(tmp_path: Path, settings: Settings):
    project_dir = tmp_path / "myaa"
    project = _all_atom_project(tmp_path, project_dir)
    project.last_run_status = "running"

    result = delete_project(_bridge(), project)

    assert not result.success
    assert "running" in result.message.lower()
    assert project_dir.exists()


# -- rename_project -------------------------------------------------------------


def test_rename_project_rejects_empty_name(tmp_path: Path, settings: Settings):
    project_dir = tmp_path / "myaa"
    project = _all_atom_project(tmp_path, project_dir)

    result = rename_project(_bridge(), settings, project, "   ")

    assert not result.success
    assert "name" in result.message.lower()
    assert project_dir.exists()


def test_rename_project_rejects_same_name(tmp_path: Path, settings: Settings):
    project_dir = tmp_path / "myaa"
    project = _all_atom_project(tmp_path, project_dir)

    result = rename_project(_bridge(), settings, project, "myaa")

    assert not result.success
    assert project_dir.exists()


def test_rename_project_refuses_while_running(tmp_path: Path, settings: Settings):
    project_dir = tmp_path / "myaa"
    project = _all_atom_project(tmp_path, project_dir)
    project.last_run_status = "running"

    result = rename_project(_bridge(), settings, project, "renamed")

    assert not result.success
    assert "running" in result.message.lower()
    assert project_dir.exists()


def test_rename_project_refuses_name_collision(tmp_path: Path, settings: Settings):
    project_dir = tmp_path / "myaa"
    project = _all_atom_project(tmp_path, project_dir)
    # local_directory_for(settings, "taken") resolves to tmp_path / "taken"
    # (see the `settings` fixture) -- create it so the collision check finds it.
    (tmp_path / "taken").mkdir()

    result = rename_project(_bridge(), settings, project, "taken")

    assert not result.success
    assert "already exists" in result.message
    assert project_dir.exists()


def test_rename_project_renames_directory_prefixed_files_and_regenerates_control_file(
    tmp_path: Path, settings: Settings
):
    project_dir = tmp_path / "myaa"
    project = _all_atom_project(tmp_path, project_dir)

    result = rename_project(_bridge(), settings, project, "renamed")

    new_dir = tmp_path / "renamed"
    assert result.success, result.message
    assert result.new_local_directory == str(new_dir)
    assert not project_dir.exists()
    assert new_dir.exists()

    # non-prefixed files (the copied source files) are untouched
    assert (new_dir / "input.psf").exists()
    assert (new_dir / "input.pdb").exists()
    assert (new_dir / "top_all36_prot.rtf").exists()

    # project.json follows the rename (via project.save inside rename_project)
    assert (new_dir / "project.json").exists()
    reloaded = Project.load(str(new_dir))
    assert reloaded.name == "renamed"
    assert reloaded.directory == str(new_dir)

    # run.inp was regenerated for the new name
    assert (new_dir / "run.inp").exists()
    assert "topfile = top_all36_prot.rtf" in (new_dir / "run.inp").read_text()
    assert project.name == "renamed"
    assert project.directory == str(new_dir)
