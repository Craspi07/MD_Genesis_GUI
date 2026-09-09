import os
import time
from pathlib import Path
from typing import List

import pytest
from PyQt5.QtCore import QEventLoop, QTimer

from app.project import Project, ResourceConfig, Engine
from app.settings import Settings
from app.runner import (
    SimulationRunner,
    build_wrapper_script,
    build_oversubscribe_wrapper_script,
)
from app.wsl import WslBridge, CommandResult, TailResult

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")


def _settings() -> Settings:
    s = Settings()
    s.distro = "Ubuntu-24.04"
    s.mpi_extra_args = "--mca btl vader,self --bind-to core --map-by socket:PE={omp_threads}"
    s.total_cores = 16
    return s


def test_build_wrapper_script_records_pgid_before_exec():
    resources = ResourceConfig(engine=Engine.ATDYN, mpi_ranks=4, omp_threads=4)
    script = build_wrapper_script(resources, _settings())
    assert "setsid bash -c" in script
    inner_start = script.index("echo $$")
    exec_start = script.index("exec mpirun")
    assert inner_start < exec_start  # PGID captured before exec replaces the shell
    assert "mpirun -np 4" in script
    assert "atdyn" in script
    assert "run.log" in script


def test_build_oversubscribe_wrapper_script_adds_flag():
    resources = ResourceConfig(engine=Engine.CGDYN, mpi_ranks=8, omp_threads=2)
    script = build_oversubscribe_wrapper_script(resources, _settings())
    assert "--oversubscribe" in script
    assert "cgdyn" in script


# -- polling/tailing against real files via the fake wsl.exe shim -----------
@pytest.fixture
def bridge() -> WslBridge:
    return WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)


def _project(directory: str) -> Project:
    project = Project(name="test", directory=directory)
    project.resources = ResourceConfig(engine=Engine.ATDYN, mpi_ranks=4, omp_threads=4)
    return project


def test_runner_poll_parses_newly_tailed_lines(bridge: WslBridge, tmp_path: Path):
    project = _project(str(tmp_path))
    runner = SimulationRunner(bridge, project, str(tmp_path), poll_interval_ms=100)
    runner.set_settings(_settings())

    log_path = tmp_path / "run.log"
    log_path.write_text("INFO:       STEP       TIME   TOTAL_ENE\n")

    # fake a live process group so poll() doesn't think the run finished
    runner._pgid = os.getpgrp()

    received: List[list] = []
    runner.new_records.connect(received.append)

    runner.poll()  # header only, no records yet
    assert received == []

    with open(log_path, "a") as fh:
        fh.write("INFO:          0     0.0000    -1234.50\n")
    runner.poll()

    assert len(received) == 1
    assert received[0][0].step == 0
    assert received[0][0].values["TOTAL_ENE"] == -1234.50


def test_runner_detects_finished_process(bridge: WslBridge, tmp_path: Path):
    project = _project(str(tmp_path))
    runner = SimulationRunner(bridge, project, str(tmp_path), poll_interval_ms=100)
    runner.set_settings(_settings())
    (tmp_path / "run.log").write_text("")

    # an implausibly large PID that (almost certainly) isn't a live process group
    runner._pgid = 999999

    statuses = []
    runner.status_changed.connect(statuses.append)
    runner.poll()

    assert project.last_run_status == "finished"
    assert "finished" in statuses


def test_runner_stop_sends_sigterm_to_process_group():
    calls = []

    class RecordingBridge:
        def run(self, command, timeout=None):
            calls.append(command)
            return CommandResult(returncode=0, stdout="", stderr="")

        def tail(self, path, offset=0):
            return TailResult(text="", offset=offset)

    project = _project("/fake/project/dir")
    runner = SimulationRunner(RecordingBridge(), project, "/fake/project/dir")
    runner.set_settings(_settings())
    runner._pgid = 4242

    runner.stop(force=True)

    assert any("kill -TERM -- -4242" in c for c in calls)
    assert any("kill -KILL -- -4242" in c for c in calls)
    assert project.last_run_status == "stopped"


def test_runner_stop_without_pgid_just_marks_stopped():
    class RecordingBridge:
        def run(self, command, timeout=None):
            raise AssertionError("should not call bridge.run when no PGID is known")

        def tail(self, path, offset=0):
            return TailResult(text="", offset=offset)

    project = _project("/fake/project/dir")
    runner = SimulationRunner(RecordingBridge(), project, "/fake/project/dir")
    runner.stop()
    assert project.last_run_status == "stopped"


def test_reattach_to_dead_pgid_reports_finished(bridge: WslBridge, tmp_path: Path):
    project = _project(str(tmp_path))
    runner = SimulationRunner(bridge, project, str(tmp_path))
    runner.set_settings(_settings())

    alive = runner.reattach(999999)
    assert not alive
    assert project.last_run_status == "finished"


def test_reattach_to_alive_pgid_resumes_polling(bridge: WslBridge, tmp_path: Path):
    project = _project(str(tmp_path))
    runner = SimulationRunner(bridge, project, str(tmp_path))
    runner.set_settings(_settings())

    statuses = []
    runner.status_changed.connect(statuses.append)
    alive = runner.reattach(os.getpgrp())
    assert alive
    assert statuses == ["running"]
    runner._timer.stop()


def test_summary_computes_ns_per_day(bridge: WslBridge, tmp_path: Path):
    project = _project(str(tmp_path))
    project.parameters.timestep_fs = 10.0
    runner = SimulationRunner(bridge, project, str(tmp_path))
    runner.set_settings(_settings())
    runner._start_time = time.time() - 3600  # pretend it's been running an hour

    runner.parser.feed("INFO:       STEP       TIME   TOTAL_ENE\n")
    runner.parser.feed("INFO:      100000     100.0    -1234.50\n")

    summary = runner.summary()
    assert summary is not None
    assert summary.ns_simulated == pytest.approx(1.0)  # 100000 steps * 10 fs = 1 ns
    assert summary.ns_per_day == pytest.approx(24.0, rel=0.05)  # 1 ns/hour ~= 24 ns/day
