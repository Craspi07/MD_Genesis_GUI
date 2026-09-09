from pathlib import Path

from app.benchmark import (
    presets_for,
    run_benchmark,
    fastest_preset,
    apply_fastest_preset,
    estimate_wall_time_seconds,
    load_results,
    BenchmarkResult,
)
from app.project import Project
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
