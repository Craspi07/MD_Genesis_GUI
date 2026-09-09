from pathlib import Path

from app.project import Project, InputMode
from app.project_creation import (
    create_project_files,
    build_cg_commands,
    run_cg_tool_pipeline,
    generate_project_control_file,
    local_directory_for,
)
from app.settings import Settings
from app.wsl import WslBridge

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")


def _bridge() -> WslBridge:
    return WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)


def test_local_directory_for():
    settings = Settings()
    settings.distro = "Ubuntu-24.04"
    settings.linux_user = "biplab"
    path = local_directory_for(settings, "myproj")
    assert "Ubuntu-24.04" in path
    assert "biplab" in path
    assert "myproj" in path


def test_create_project_files_pdb_mode(tmp_path: Path):
    source_pdb = tmp_path / "source.pdb"
    source_pdb.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00\n")
    project_dir = tmp_path / "proj"

    project = Project(name="myproj", directory="~/genesis_projects/myproj", input_mode=InputMode.PDB)
    created = create_project_files(project, str(project_dir), source_pdb_path=str(source_pdb))

    assert "project.json" in created
    assert (project_dir / "project.json").exists()
    assert (project_dir / "source.pdb").exists()


def test_create_project_files_sequence_mode(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project = Project(
        name="myidr",
        directory="~/genesis_projects/myidr",
        input_mode=InputMode.SEQUENCE,
        sequence="MKTAYIAKQR",
    )
    created = create_project_files(project, str(project_dir))
    assert "myidr_extended.pdb" in created
    assert (project_dir / "myidr_extended.pdb").exists()


def test_build_cg_commands_pdb_mode_uses_aicg2p():
    project = Project(name="p", directory="~/genesis_projects/p", input_mode=InputMode.PDB)
    commands = build_cg_commands(project, "p.pdb")
    assert len(commands) == 1
    assert commands[0].verified


def test_build_cg_commands_sequence_mode_uses_hps_pipeline():
    project = Project(
        name="p", directory="~/genesis_projects/p", input_mode=InputMode.SEQUENCE, sequence="MKT"
    )
    commands = build_cg_commands(project, "p_extended.pdb")
    assert len(commands) == 3
    assert all(not c.verified for c in commands)


def test_run_cg_tool_pipeline_reports_failure_when_julia_missing(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project = Project(name="myproj", directory="~/genesis_projects/myproj", input_mode=InputMode.PDB)
    source_pdb = tmp_path / "source.pdb"
    source_pdb.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00\n")
    create_project_files(project, str(project_dir), source_pdb_path=str(source_pdb))

    result = run_cg_tool_pipeline(_bridge(), project, str(project_dir))

    # julia isn't installed in this dev environment, so the real command
    # fails — the pipeline must report that failure rather than silently
    # succeeding, and must still leave a readable log behind.
    assert not result.success
    assert (project_dir / "cgtool.log").exists()
    assert "julia" in result.log or "not found" in result.log.lower()


def test_generate_project_control_file(tmp_path: Path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "myproj.top").write_text("[ molecules ]\nMOL  1\n")
    (project_dir / "myproj.gro").write_text("title\n0\n0.0 0.0 0.0\n")

    project = Project(name="myproj", directory="~/genesis_projects/myproj", input_mode=InputMode.PDB)
    path = generate_project_control_file(project, str(project_dir))

    assert path.exists()
    text = path.read_text()
    assert "myproj.top" in text
    assert "myproj.gro" in text
