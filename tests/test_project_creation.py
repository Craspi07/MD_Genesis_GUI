from pathlib import Path

from app.project import Project, InputMode, ModelType
from app.project_creation import (
    create_project_files,
    build_cg_commands,
    run_cg_tool_pipeline,
    generate_project_control_file,
    local_directory_for,
    local_projects_root_for,
    copy_cg_tool_param,
)
from app.settings import Settings
from app.wsl import CommandResult, WslBridge

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


def test_local_projects_root_for_is_the_parent_of_local_directory_for():
    settings = Settings()
    settings.distro = "Ubuntu-24.04"
    settings.linux_user = "biplab"
    root = local_projects_root_for(settings)
    project_dir = local_directory_for(settings, "myproj")
    assert project_dir == f"{root}\\myproj"


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
    assert "myidr.fasta" in created
    assert (project_dir / "myidr.fasta").exists()
    assert (project_dir / "myidr.fasta").read_text() == ">myidr\nMKTAYIAKQR\n"


def test_build_cg_commands_pdb_mode_uses_aicg2p():
    project = Project(name="p", directory="~/genesis_projects/p", input_mode=InputMode.PDB)
    commands = build_cg_commands(project, "p.pdb")
    assert len(commands) == 1
    assert commands[0].verified


def test_build_cg_commands_sequence_mode_uses_structure_builder():
    project = Project(
        name="p", directory="~/genesis_projects/p", input_mode=InputMode.SEQUENCE, sequence="MKT"
    )
    commands = build_cg_commands(project, "p.fasta")
    assert len(commands) == 1
    assert commands[0].verified
    assert "cg_protein_structure_builder.jl" in commands[0].command
    assert "p.fasta" in commands[0].command


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


def test_run_cg_tool_pipeline_reports_failure_for_sequence_mode_too(tmp_path: Path):
    # Regression check for the 2026-09-14 rewrite: sequence-mode input
    # detection now looks for .fasta (not the old .pdb extended-chain
    # workaround), and must still fail gracefully when genesis_cg_tool
    # isn't actually installed here.
    project_dir = tmp_path / "proj"
    project = Project(
        name="myidr", directory="~/genesis_projects/myidr", input_mode=InputMode.SEQUENCE, sequence="MKT"
    )
    create_project_files(project, str(project_dir))

    result = run_cg_tool_pipeline(_bridge(), project, str(project_dir))

    assert not result.success
    assert (project_dir / "cgtool.log").exists()


def test_run_cg_tool_pipeline_condensate_renames_and_replicates(tmp_path: Path, monkeypatch):
    # Exercises the rename -> duplication_generator.jl -> cleanup sequence
    # directly (app/cgtool.py's build_duplication_command is covered in
    # isolation by tests/test_cgtool.py) by faking every bridge.run() call
    # to succeed, since the real tools aren't installed in this dev
    # environment. Pre-places the .top/.gro that a real
    # cg_protein_structure_builder.jl run would have produced.
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    project = Project(
        name="myidr",
        directory=str(project_dir),
        input_mode=InputMode.SEQUENCE,
        sequence="MKT",
        model_type=ModelType.HPS_CONDENSATE,
    )
    project.parameters.n_copies = 3
    create_project_files(project, str(project_dir))
    (project_dir / "myidr_cg.top").write_text("[ molecules ]\nMOL 1\n")
    (project_dir / "myidr_cg.gro").write_text("title\n0\n0.0 0.0 0.0\n")

    bridge = _bridge()
    monkeypatch.setattr(bridge, "run", lambda *a, **k: CommandResult(0, "", ""))

    result = run_cg_tool_pipeline(bridge, project, str(project_dir))

    assert result.success
    assert "duplication_generator.jl" in result.log
    assert (project_dir / "myidr_cg.top").exists()
    # the temporary rename target must be cleaned up, not left as a second
    # file matching "myidr*.gro" that a later glob could pick up by mistake
    assert not (project_dir / "myidr_single.gro").exists()


def test_copy_cg_tool_param_succeeds_when_source_exists(tmp_path: Path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / "genesis_cg_tool" / "param").mkdir(parents=True)
    (fake_home / "genesis_cg_tool" / "param" / "example.itp").write_text("; fake param\n")
    monkeypatch.setenv("HOME", str(fake_home))

    project_dir = tmp_path / "proj"
    project = Project(name="myproj", directory=str(project_dir))

    result = copy_cg_tool_param(_bridge(), project)

    assert result.ok
    assert (project_dir / "param" / "example.itp").exists()


def test_copy_cg_tool_param_fails_when_source_missing(tmp_path: Path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    project_dir = tmp_path / "proj"
    project = Project(name="myproj", directory=str(project_dir))

    result = copy_cg_tool_param(_bridge(), project)

    assert not result.ok


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
