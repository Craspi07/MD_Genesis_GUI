"""Simulation run queue: queue several projects and run them either
sequentially or two at once with half the cores each (F3's queue
requirement).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from app.project import Project
from app.runner import SimulationRunner
from app.settings import Settings
from app.wsl import WslBridge


@dataclass
class QueueItem:
    project: Project
    local_directory: str
    status: str = "pending"  # pending | running | finished | stopped | failed


RunnerFactory = Callable[[Project, str], SimulationRunner]


def _default_runner_factory(settings: Settings, distro: str) -> RunnerFactory:
    def factory(project: Project, local_directory: str) -> SimulationRunner:
        runner = SimulationRunner(WslBridge(distro=distro), project, local_directory)
        runner.set_settings(settings)
        return runner

    return factory


class RunQueue(QObject):
    """Owns a list of queued (project, local_directory) items and starts
    them either one at a time or two at once (each halving its requested
    core count so both fit on the machine)."""

    item_started = pyqtSignal(int)
    item_finished = pyqtSignal(int, str)
    queue_finished = pyqtSignal()

    def __init__(
        self,
        settings: Settings,
        parallel: bool = False,
        runner_factory: Optional[RunnerFactory] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.parallel = parallel
        self._runner_factory = runner_factory or _default_runner_factory(settings, settings.distro)
        self.items: List[QueueItem] = []
        self._runners: Dict[int, SimulationRunner] = {}
        self._active_indices: List[int] = []
        self._started = False

    def add(self, project: Project, local_directory: str) -> int:
        self.items.append(QueueItem(project=project, local_directory=local_directory))
        return len(self.items) - 1

    def start(self) -> None:
        self._started = True
        self._advance()

    def max_concurrent(self) -> int:
        return 2 if self.parallel else 1

    def _next_pending_index(self) -> Optional[int]:
        for i, item in enumerate(self.items):
            if item.status == "pending":
                return i
        return None

    def _advance(self) -> None:
        while len(self._active_indices) < self.max_concurrent():
            index = self._next_pending_index()
            if index is None:
                break
            self._start_item(index)
        if not self._active_indices and self._next_pending_index() is None and self._started:
            self.queue_finished.emit()

    def _start_item(self, index: int) -> None:
        item = self.items[index]
        if self.parallel:
            item.project.resources.mpi_ranks = max(item.project.resources.mpi_ranks // 2, 1)

        runner = self._runner_factory(item.project, item.local_directory)
        runner.status_changed.connect(lambda status, i=index: self._on_status(i, status))
        self._runners[index] = runner
        item.status = "running"
        self._active_indices.append(index)
        runner.start()
        self.item_started.emit(index)

    def _on_status(self, index: int, status: str) -> None:
        if status not in ("finished", "stopped", "failed"):
            return
        self.items[index].status = status
        if index in self._active_indices:
            self._active_indices.remove(index)
        self.item_finished.emit(index, status)
        self._advance()

    def runner_for(self, index: int) -> Optional[SimulationRunner]:
        return self._runners.get(index)
