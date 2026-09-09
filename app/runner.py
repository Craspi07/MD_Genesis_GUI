"""Launches and monitors a GENESIS simulation inside WSL.

Fortran stdout is block-buffered when piped, so a live-updating Run tab
can't just read a QProcess's stdout: every job is launched with its
output redirected to a log file (`run.log`) inside the project directory,
and that file is tailed on a QTimer instead (see CLAUDE.md / app/wsl.py's
`tail()`). The job is started with `setsid` so it owns its own process
group; the wrapper records that group's PID to `run.pgid` before `exec`ing
into `mpirun`, so `stop()` can signal the whole group (and a fresh GUI
process can reattach to a still-running job after being closed/reopened,
by checking whether that PGID is still alive).
"""
from __future__ import annotations

import shlex
import time
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from app.log_parser import GenesisLogParser, detect_slot_error, detect_error_lines
from app.project import Project, ResourceConfig
from app.settings import Settings
from app.wsl import WslBridge

RUN_LOG_NAME = "run.log"
PGID_FILE_NAME = "run.pgid"
CONTROL_FILE_NAME = "run.inp"

STOP_GRACE_PERIOD_MS = 10_000


def build_wrapper_script(
    resources: ResourceConfig,
    settings: Settings,
    control_file: str = CONTROL_FILE_NAME,
    log_file: str = RUN_LOG_NAME,
    pgid_file: str = PGID_FILE_NAME,
    extra_mpirun_args: str = "",
) -> str:
    """The exact command launched inside WSL for a simulation run.

    `setsid` makes this shell its own process group leader; it records its
    PID (== the group's PGID, since it's the leader) before `exec`ing into
    `mpirun` so the group ID survives the exec (gotcha #3: killing mpirun
    alone doesn't reliably kill the MPI ranks — the whole group must be
    signaled).
    """
    mpi_args = settings.mpi_args_for(resources.omp_threads)
    if extra_mpirun_args:
        mpi_args = f"{mpi_args} {extra_mpirun_args}"
    inner = (
        f"echo $$ > {shlex.quote(pgid_file)}; "
        f"export OMP_NUM_THREADS={resources.omp_threads}; "
        f"exec mpirun -np {resources.mpi_ranks} {mpi_args} {resources.engine.value} "
        f"{shlex.quote(control_file)} > {shlex.quote(log_file)} 2>&1"
    )
    return f"setsid bash -c {shlex.quote(inner)} < /dev/null &"


def build_oversubscribe_wrapper_script(
    resources: ResourceConfig, settings: Settings, **kwargs
) -> str:
    """Same as build_wrapper_script but with --oversubscribe added, for the
    automatic retry after an MPI "not enough slots" error (F6)."""
    return build_wrapper_script(resources, settings, extra_mpirun_args="--oversubscribe", **kwargs)


@dataclass
class RunSummary:
    wall_time_seconds: float
    ns_simulated: float
    ns_per_day: float


class SimulationRunner(QObject):
    """Owns the lifecycle of one simulation run: start, poll/tail, stop,
    reattach. One instance per open project's Run tab.
    """

    new_records = pyqtSignal(list)  # List[LogRecord]
    raw_output = pyqtSignal(str)
    status_changed = pyqtSignal(str)  # "running" | "finished" | "stopped" | "failed"
    error_detected = pyqtSignal(str)

    def __init__(
        self,
        bridge: WslBridge,
        project: Project,
        local_directory: str,
        poll_interval_ms: int = 2000,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.bridge = bridge
        self.project = project
        self.local_directory = local_directory
        self.parser = GenesisLogParser()
        self._offset = 0
        self._pgid: Optional[int] = None
        self._start_time: Optional[float] = None
        self._oversubscribe_retried = False

        self._timer = QTimer(self)
        self._timer.setInterval(poll_interval_ms)
        self._timer.timeout.connect(self.poll)

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        script = build_wrapper_script(self.project.resources, self._settings())
        self.bridge.run(f"cd {self.project.directory} && {script}")
        self._offset = 0
        self._start_time = time.time()
        self.project.last_run_status = "running"
        self.status_changed.emit("running")
        self._timer.start()
        # give the wrapper a moment to write the PGID file before the first poll
        QTimer.singleShot(500, self._read_pgid)

    def _settings(self) -> Settings:
        # Runner only needs mpi_extra_args/total_cores; constructed lazily
        # to avoid a hard dependency on a full Settings object in tests.
        if hasattr(self, "_settings_obj"):
            return self._settings_obj
        return Settings().load()

    def set_settings(self, settings: Settings) -> None:
        self._settings_obj = settings

    def _read_pgid(self) -> None:
        result = self.bridge.run(f"cat {self.project.directory}/{PGID_FILE_NAME} 2>/dev/null")
        text = result.stdout.strip()
        if text.isdigit():
            self._pgid = int(text)
            self.project.last_run_pgid = self._pgid

    def poll(self) -> None:
        result = self.bridge.tail(f"{self.project.directory}/{RUN_LOG_NAME}", self._offset)
        self._offset = result.offset
        if result.text:
            self.raw_output.emit(result.text)
            if detect_slot_error(result.text) and not self._oversubscribe_retried:
                self._retry_with_oversubscribe()
                return
            errors = detect_error_lines(result.text)
            for line in errors:
                self.error_detected.emit(line)
            records = self.parser.feed(result.text)
            if records:
                self.new_records.emit(records)

        if self._pgid is not None and not self._process_group_alive():
            self._on_finished()

    def _retry_with_oversubscribe(self) -> None:
        self._oversubscribe_retried = True
        self.stop(force=True)
        script = build_oversubscribe_wrapper_script(self.project.resources, self._settings())
        self.bridge.run(f"cd {self.project.directory} && {script}")
        self._offset = 0
        self.parser = GenesisLogParser()
        QTimer.singleShot(500, self._read_pgid)

    def _process_group_alive(self) -> bool:
        result = self.bridge.run(f"kill -0 -- -{self._pgid} 2>/dev/null && echo ALIVE || echo DEAD")
        return "ALIVE" in result.stdout

    def _on_finished(self) -> None:
        self._timer.stop()
        self.project.last_run_status = "finished"
        self.status_changed.emit("finished")

    def stop(self, force: bool = False) -> None:
        if self._pgid is None:
            self._timer.stop()
            self.project.last_run_status = "stopped"
            self.status_changed.emit("stopped")
            return
        self.bridge.run(f"kill -TERM -- -{self._pgid}")
        if force:
            self.bridge.run(f"kill -KILL -- -{self._pgid} 2>/dev/null")
        else:
            QTimer.singleShot(STOP_GRACE_PERIOD_MS, self._escalate_if_still_alive)
        self._timer.stop()
        self.project.last_run_status = "stopped"
        self.status_changed.emit("stopped")

    def _escalate_if_still_alive(self) -> None:
        if self._pgid is not None and self._process_group_alive():
            self.bridge.run(f"kill -KILL -- -{self._pgid}")

    # -- reattach --------------------------------------------------------------
    def reattach(self, pgid: int) -> bool:
        """Called on app startup if project.json recorded a running PGID.
        Returns True if that process group is still alive and polling has
        resumed."""
        self._pgid = pgid
        if not self._process_group_alive():
            self.project.last_run_status = "finished"
            return False
        self.status_changed.emit("running")
        self._timer.start()
        return True

    # -- summary -----------------------------------------------------------
    def summary(self) -> Optional[RunSummary]:
        if self._start_time is None:
            return None
        wall = max(time.time() - self._start_time, 1e-9)
        latest = self.parser.latest()
        if latest is None:
            return RunSummary(wall_time_seconds=wall, ns_simulated=0.0, ns_per_day=0.0)
        ns_simulated = latest.step * self.project.parameters.timestep_fs / 1_000_000.0
        ns_per_day = ns_simulated / (wall / 86400.0)
        return RunSummary(wall_time_seconds=wall, ns_simulated=ns_simulated, ns_per_day=ns_per_day)
