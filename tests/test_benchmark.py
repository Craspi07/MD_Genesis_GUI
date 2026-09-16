from pathlib import Path

from app.benchmark import (
    presets_for,
    run_benchmark,
    fastest_preset,
    apply_fastest_preset,
    estimate_wall_time_seconds,
    load_results,
    BenchmarkResult,
    _diagnose_empty_log,
    _run_one_preset,
)
from app.project import ModelType, Project
from app.settings import Settings
from app.wsl import WslBridge

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")


def _bridge() -> WslBridge:
    return WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)


def _settings(total_cores=16) -> Settings:
    s = Settings()
    s.distro = "Ubuntu-24.04"
    s.total_cores = total_cores
    return s


def test_presets_for_16_cores_matches_spec():
    assert presets_for(16) == [(4, 4), (8, 2), (16, 1)]


def test_presets_for_8_cores():
    presets = presets_for(8)
    for ranks, threads in presets:
        assert ranks * threads == 8


def test_run_benchmark_without_top_gro_reports_error(tmp_path: Path):
    project = Project(name="myproj", directory=str(tmp_path))
    results = run_benchmark(_bridge(), project, str(tmp_path), _settings())
    assert len(results) == 1
    assert not results[0].success


def test_run_benchmark_reports_failure_when_binaries_missing(tmp_path: Path):
    (tmp_path / "myproj.top").write_text("[ molecules ]\nMOL 1\n")
    (tmp_path / "myproj.gro").write_text("title\n0\n0.0 0.0 0.0\n")
    project = Project(name="myproj", directory=str(tmp_path))

    results = run_benchmark(_bridge(), project, str(tmp_path), _settings())

    assert len(results) == 3
    assert all(not r.success for r in results)  # mpirun/atdyn aren't installed here
    assert (tmp_path / "benchmarks.json").exists()

    loaded = load_results(str(tmp_path))
    assert len(loaded) == 3


def test_fastest_preset_picks_highest_steps_per_second():
    results = [
        BenchmarkResult(4, 4, 10.0, 200.0, True),
        BenchmarkResult(8, 2, 8.0, 250.0, True),
        BenchmarkResult(16, 1, 20.0, 100.0, True),
    ]
    best = fastest_preset(results)
    assert best.mpi_ranks == 8 and best.omp_threads == 2


def test_fastest_preset_ignores_failures():
    results = [
        BenchmarkResult(4, 4, None, None, False, "failed"),
        BenchmarkResult(8, 2, 8.0, 250.0, True),
    ]
    best = fastest_preset(results)
    assert best.mpi_ranks == 8


def test_fastest_preset_none_when_all_failed():
    results = [BenchmarkResult(4, 4, None, None, False, "failed")]
    assert fastest_preset(results) is None


def test_apply_fastest_preset_updates_project_resources(tmp_path: Path):
    project = Project(name="p", directory=str(tmp_path))
    results = [
        BenchmarkResult(4, 4, 10.0, 200.0, True),
        BenchmarkResult(8, 2, 8.0, 250.0, True),
    ]
    applied = apply_fastest_preset(project, results)
    assert applied
    assert project.resources.mpi_ranks == 8
    assert project.resources.omp_threads == 2


def test_estimate_wall_time_seconds():
    results = [BenchmarkResult(8, 2, 8.0, 250.0, True)]
    estimate = estimate_wall_time_seconds(results, n_steps=1_000_000)
    assert estimate == 4000.0


def test_run_one_preset_uses_a_unique_tag_and_cleans_up_first(tmp_path: Path):
    # Real 2026-09-14 failure: every preset shared a fixed "benchmark"
    # output prefix, so the second preset in a sweep hit "Open_file> File
    # benchmark.rst already exists" from the first preset's leftover
    # restart file. Each preset must get its own filenames, and must
    # clear its own (possibly stale, from an earlier benchmark run on the
    # same project) leftovers before running.
    (tmp_path / "myproj.top").write_text("[ molecules ]\nMOL 1\n")
    (tmp_path / "myproj.gro").write_text("title\n0\n0.0 0.0 0.0\n")
    project = Project(name="myproj", directory=str(tmp_path))

    commands = []
    bridge = _bridge()
    real_run = bridge.run

    def recording_run(command, *args, **kwargs):
        commands.append(command)
        return real_run(command, *args, **kwargs)

    bridge.run = recording_run

    _run_one_preset(bridge, project, tmp_path, _settings(), ranks=4, threads=4, n_steps=100)
    _run_one_preset(bridge, project, tmp_path, _settings(), ranks=8, threads=2, n_steps=100)

    assert (tmp_path / "benchmark_4x4.inp").exists()
    assert (tmp_path / "benchmark_8x2.inp").exists()

    cleanup_commands = [c for c in commands if "rm -f" in c]
    assert len(cleanup_commands) == 2
    assert "benchmark_4x4.rst" in cleanup_commands[0]
    assert "benchmark_8x2" not in cleanup_commands[0]
    assert "benchmark_8x2.rst" in cleanup_commands[1]
    assert "benchmark_4x4" not in cleanup_commands[1]


def test_run_benchmark_reports_missing_files_for_all_atom_project(tmp_path: Path):
    project = Project(name="myaa", directory=str(tmp_path), model_type=ModelType.ALL_ATOM_CHARMM)
    results = run_benchmark(_bridge(), project, str(tmp_path), _settings())
    assert len(results) == 1
    assert not results[0].success
    assert ".psf/.pdb" in results[0].error


def test_run_one_preset_builds_all_atom_control_file(tmp_path: Path):
    (tmp_path / "input.psf").write_text("PSF\n")
    (tmp_path / "input.pdb").write_text("ATOM\n")
    (tmp_path / "top_all36_prot.rtf").write_text("* top\n")
    (tmp_path / "par_all36m_prot.prm").write_text("* par\n")
    project = Project(name="myaa", directory=str(tmp_path), model_type=ModelType.ALL_ATOM_CHARMM)
    project.aa_top_source_paths = ["top_all36_prot.rtf"]
    project.aa_par_source_paths = ["par_all36m_prot.prm"]
    project.aa_psf_source_path = "input.psf"
    project.aa_pdb_source_path = "input.pdb"
    project.aa_box_x = 68.26
    project.aa_box_y = 80.24
    project.aa_box_z = 66.59

    _run_one_preset(_bridge(), project, tmp_path, _settings(), ranks=4, threads=4, n_steps=100)

    text = (tmp_path / "benchmark_4x4.inp").read_text()
    assert "forcefield          = CHARMM" in text
    assert "psffile = input.psf" in text


def test_diagnose_empty_log_reports_slot_error():
    log = "mpirun detected that one or more processes exited with...\nnot enough slots available\n"
    assert "not enough slots" in _diagnose_empty_log(log)


def test_diagnose_empty_log_reports_genesis_error():
    log = "INFO: reading input files...\nERROR: could not open control file\n"
    assert "GENESIS reported an error" in _diagnose_empty_log(log)
    assert "could not open control file" in _diagnose_empty_log(log)


def test_diagnose_empty_log_reports_blank_log():
    assert "empty" in _diagnose_empty_log("")


def test_diagnose_empty_log_includes_context_before_openmpi_rank_death():
    # Real 2026-09-14 case: the actual GENESIS crash message contained
    # none of "error"/"segmentation fault"/"mpirun...(fail|abort)", so it
    # fell through to a generic tail dump that never showed it. OpenMPI's
    # own wrapper text ("Exit code: 1", "the job to be terminated") is
    # what actually matched, several lines after the real cause -- the
    # diagnosis must pull in that earlier context, not just the matched
    # line itself.
    log = (
        "INFO: STEP 0 ...\n"
        "Fatal problem in [CONSTRAINTS]: unstable bond length\n"
        "--------------------------------------------------------------------------\n"
        "mpirun noticed that process rank 2 with PID 123 on node X exited on signal 6\n"
        "the job to be terminated. The first process to do so was:\n"
        "  Process name: [[39631,1],2]\n"
        "  Exit code:    1\n"
        "--------------------------------------------------------------------------\n"
    )
    diagnosis = _diagnose_empty_log(log)
    assert "GENESIS reported an error" in diagnosis
    assert "unstable bond length" in diagnosis


def test_diagnose_empty_log_shows_tail_when_unrecognized():
    log = "some unrecognized GENESIS output\nthat log_parser doesn't match\n"
    diagnosis = _diagnose_empty_log(log)
    assert "didn't recognize any step records" in diagnosis
    assert "unrecognized GENESIS output" in diagnosis
