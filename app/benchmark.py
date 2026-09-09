"""Benchmark helper (F4): try a few MPI x OMP splits on a short run and
record which is fastest, so future runs can estimate wall time.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from app.control_file import ControlFileConfig, write_control_file
from app.log_parser import GenesisLogParser
from app.project import Project, ResourceConfig, Engine
from app.runner import build_wrapper_script
from app.settings import Settings
from app.wsl import WslBridge

BENCHMARK_STEPS = 2000
BENCHMARK_TIMEOUT_SECONDS = 300
BENCHMARK_FILE_NAME = "benchmarks.json"


def presets_for(total_cores: int) -> List[tuple]:
    """(mpi_ranks, omp_threads) splits that each multiply to total_cores,
    matching the 4x4 / 8x2 / 16x1 shape called for in the original spec
    for a 16-core machine, generalized to any core count."""
    candidates = [
        (max(total_cores // 4, 1), 4),
        (max(total_cores // 2, 1), 2),
        (total_cores, 1),
    ]
    seen = set()
    presets = []
    for ranks, threads in candidates:
        if ranks * threads != total_cores or (ranks, threads) in seen:
            continue
        seen.add((ranks, threads))
        presets.append((ranks, threads))
    return presets or [(total_cores, 1)]


@dataclass
class BenchmarkResult:
    mpi_ranks: int
    omp_threads: int
    wall_time_seconds: Optional[float]
    steps_per_second: Optional[float]
    success: bool
    error: str = ""


def run_benchmark(
    bridge: WslBridge,
    project: Project,
    local_directory: str,
    settings: Settings,
    n_steps: int = BENCHMARK_STEPS,
) -> List[BenchmarkResult]:
    directory = Path(local_directory)
    top_files = list(directory.glob(f"{project.name}*.top"))
    gro_files = list(directory.glob(f"{project.name}*.gro"))
    if not top_files or not gro_files:
        return [
            BenchmarkResult(0, 0, None, None, False, "Project has no .top/.gro yet — create the project first.")
        ]

    results: List[BenchmarkResult] = []
    for ranks, threads in presets_for(settings.total_cores):
        result = _run_one_preset(bridge, project, directory, settings, ranks, threads, n_steps, top_files[0].name, gro_files[0].name)
        results.append(result)

    _save_results(directory, results)
    return results


def _run_one_preset(
    bridge: WslBridge,
    project: Project,
    directory: Path,
    settings: Settings,
    ranks: int,
    threads: int,
    n_steps: int,
    top_name: str,
    gro_name: str,
) -> BenchmarkResult:
    config = ControlFileConfig(
        top_file=top_name,
        gro_file=gro_name,
        output_prefix="benchmark",
        temperature_k=project.parameters.temperature_k,
        n_steps=n_steps,
        timestep_fs=project.parameters.timestep_fs,
        output_frequency=max(n_steps // 10, 1),
        langevin_friction=project.parameters.langevin_friction,
    )
    write_control_file(config, project.model_type, str(directory), filename="benchmark.inp", force=True)

    resources = ResourceConfig(engine=project.resources.engine, mpi_ranks=ranks, omp_threads=threads)
    log_name = "benchmark.log"
    pgid_name = "benchmark.pgid"
    script = build_wrapper_script(
        resources, settings, control_file="benchmark.inp", log_file=log_name, pgid_file=pgid_name
    )
    # Benchmarks run synchronously and to completion, unlike a real
    # (backgrounded) simulation run, so the caller gets a direct
    # steps/s measurement without needing to poll.
    blocking_command = script.rstrip("&").strip() + "; wait"

    start = time.time()
    outcome = bridge.run(f"cd {project.directory} && {blocking_command}", timeout=BENCHMARK_TIMEOUT_SECONDS)
    wall_time = time.time() - start

    if not outcome.ok:
        return BenchmarkResult(ranks, threads, None, None, False, outcome.stderr.strip()[:300] or "command failed")

    log_result = bridge.run(f"cat {project.directory}/{log_name} 2>/dev/null")
    parser = GenesisLogParser()
    parser.feed(log_result.stdout)
    latest = parser.latest()
    if latest is None or wall_time <= 0:
        return BenchmarkResult(ranks, threads, wall_time, None, False, "no steps completed within the timeout")

    steps_per_second = latest.step / wall_time
    return BenchmarkResult(ranks, threads, wall_time, steps_per_second, True)


def _save_results(directory: Path, results: List[BenchmarkResult]) -> None:
    data = [asdict(r) for r in results]
    (directory / BENCHMARK_FILE_NAME).write_text(json.dumps(data, indent=2))


def load_results(local_directory: str) -> List[BenchmarkResult]:
    path = Path(local_directory) / BENCHMARK_FILE_NAME
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [BenchmarkResult(**item) for item in data]


def fastest_preset(results: List[BenchmarkResult]) -> Optional[BenchmarkResult]:
    successful = [r for r in results if r.success and r.steps_per_second]
    if not successful:
        return None
    return max(successful, key=lambda r: r.steps_per_second)


def apply_fastest_preset(project: Project, results: List[BenchmarkResult]) -> bool:
    best = fastest_preset(results)
    if best is None:
        return False
    project.resources.mpi_ranks = best.mpi_ranks
    project.resources.omp_threads = best.omp_threads
    return True


def estimate_wall_time_seconds(results: List[BenchmarkResult], n_steps: int) -> Optional[float]:
    best = fastest_preset(results)
    if best is None:
        return None
    return n_steps / best.steps_per_second
