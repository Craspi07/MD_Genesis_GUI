from pathlib import Path

from app.project import Project, InputMode, ModelType
from app.project_creation import (
    copy_all_atom_files,
    create_project_files,
    build_cg_commands,
    run_cg_tool_pipeline,
    run_minimization,
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


# -- Roadmap Phase 5 wizard integration: all-atom CHARMM --------------------
def _all_atom_source_files(tmp_path: Path) -> Path:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "top_all36_prot.rtf").write_text("* topology\n")
    (source_dir / "par_all36m_prot.prm").write_text("* parameters\n")
    (source_dir / "input.psf").write_text("PSF\n")
    (source_dir / "input.pdb").write_text("ATOM\n")
    return source_dir


def _all_atom_project(tmp_path: Path) -> Project:
    source_dir = _all_atom_source_files(tmp_path)
    project = Project(
        name="myaa",
        directory="~/genesis_projects/myaa",
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
    return project


def test_copy_all_atom_files_copies_every_source_file(tmp_path: Path):
    project = _all_atom_project(tmp_path)
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    copied = copy_all_atom_files(project, str(project_dir))

    assert set(copied) == {"top_all36_prot.rtf", "par_all36m_prot.prm", "input.psf", "input.pdb"}
    for name in copied:
        assert (project_dir / name).exists()


def test_create_project_files_all_atom_prebuilt_mode_copies_files(tmp_path: Path):
    project = _all_atom_project(tmp_path)
    project_dir = tmp_path / "proj"

    created = create_project_files(project, str(project_dir))

    assert "project.json" in created
    assert "input.psf" in created
    assert "input.pdb" in created
    assert (project_dir / "input.psf").exists()


def test_generate_project_control_file_all_atom_charmm(tmp_path: Path):
    project = _all_atom_project(tmp_path)
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    copy_all_atom_files(project, str(project_dir))

    path = generate_project_control_file(project, str(project_dir))

    text = path.read_text()
    assert "topfile = top_all36_prot.rtf" in text
    assert "psffile = input.psf" in text
    assert "pdbfile = input.pdb" in text
    assert "forcefield          = CHARMM" in text
    assert "box_size_x = 68.26" in text


def test_generate_project_control_file_all_atom_charmm_with_restart_file(tmp_path: Path):
    project = _all_atom_project(tmp_path)
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    copy_all_atom_files(project, str(project_dir))

    path = generate_project_control_file(project, str(project_dir), restart_file="myaa_min.rst")

    text = path.read_text()
    assert "rstfile = myaa_min.rst" in text


def _settings() -> Settings:
    s = Settings()
    s.distro = "Ubuntu-24.04"
    s.mpi_extra_args = "--mca btl vader,self"
    s.total_cores = 4
    return s


def _install_fake_binary(bin_dir: Path, name: str, script_body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/bash\nset -e\n{script_body}\n")
    path.chmod(0o755)


def _install_fake_mpirun(bin_dir: Path) -> None:
    # This dev container has no real mpirun; run_minimization goes through
    # app.runner.build_wrapper_script (the same real launch shape used
    # everywhere else in this app), which always wraps the engine binary in
    # "mpirun -np N <mpi_args...> <engine> <control_file>". A thin
    # passthrough that execs from the engine binary's name onward is enough
    # to exercise the real code path end-to-end without a real MPI install.
    _install_fake_binary(
        bin_dir,
        "mpirun",
        'args=("$@"); for i in "${!args[@]}"; do '
        'if [[ "${args[$i]}" == "atdyn" || "${args[$i]}" == "cgdyn" ]]; then '
        'exec "${args[@]:$i}"; fi; done; '
        'echo "fake mpirun: no engine binary found in: $@" >&2; exit 1',
    )


def test_run_minimization_success(tmp_path: Path, monkeypatch):
    import os

    project = _all_atom_project(tmp_path)
    project.directory = str(tmp_path)  # so "cd {project.directory}" lands here for the fake bridge
    project_dir = tmp_path
    copy_all_atom_files(project, str(project_dir))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_mpirun(bin_dir)
    _install_fake_binary(
        bin_dir,
        "atdyn",
        'echo "fake minimize run"; touch myaa_min.rst myaa_min.dcd',
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    result = run_minimization(_bridge(), project, str(project_dir), _settings())

    assert result.success, result.log
    assert (project_dir / "minimize.inp").exists()
    assert (project_dir / "myaa_min.rst").exists()


def test_run_minimization_reports_failure_when_no_restart_produced(tmp_path: Path, monkeypatch):
    import os

    project = _all_atom_project(tmp_path)
    project.directory = str(tmp_path)
    project_dir = tmp_path
    copy_all_atom_files(project, str(project_dir))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_mpirun(bin_dir)
    # fake atdyn that "succeeds" but writes nothing -- simulates a silent failure
    _install_fake_binary(bin_dir, "atdyn", 'echo "did nothing"')
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    result = run_minimization(_bridge(), project, str(project_dir), _settings())

    assert not result.success
    assert "restart file" in result.message
