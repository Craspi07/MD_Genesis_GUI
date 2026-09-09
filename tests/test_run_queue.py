from pathlib import Path
from typing import List

from PyQt5.QtCore import QObject, pyqtSignal

from app.project import Project
from app.run_queue import RunQueue
from app.settings import Settings


class StubRunner(QObject):
    status_changed = pyqtSignal(str)

    def __init__(self, project: Project, local_directory: str):
        super().__init__()
        self.project = project
        self.local_directory = local_directory
        self.started = False

    def start(self) -> None:
        self.started = True

    def finish(self, status: str = "finished") -> None:
        self.status_changed.emit(status)


def _settings() -> Settings:
    s = Settings()
    s.distro = "Ubuntu-24.04"
    s.total_cores = 16
    return s


def _make_queue(parallel: bool, stubs: List[StubRunner]) -> RunQueue:
    def factory(project, local_directory):
        stub = StubRunner(project, local_directory)
        stubs.append(stub)
        return stub

    return RunQueue(_settings(), parallel=parallel, runner_factory=factory)


def _project(tmp_path: Path, name: str, ranks: int = 8) -> Project:
    p = Project(name=name, directory=str(tmp_path / name))
    p.resources.mpi_ranks = ranks
    p.resources.omp_threads = 2
    return p


def test_sequential_queue_runs_one_at_a_time(tmp_path: Path):
    stubs: List[StubRunner] = []
    queue = _make_queue(parallel=False, stubs=stubs)
    queue.add(_project(tmp_path, "a"), str(tmp_path / "a"))
    queue.add(_project(tmp_path, "b"), str(tmp_path / "b"))

    queue.start()
    assert len(stubs) == 1
    assert stubs[0].started
    assert queue.items[0].status == "running"
    assert queue.items[1].status == "pending"

    stubs[0].finish("finished")
    assert queue.items[0].status == "finished"
    assert len(stubs) == 2
    assert stubs[1].started
    assert queue.items[1].status == "running"


def test_parallel_queue_runs_two_at_once_and_halves_cores(tmp_path: Path):
    stubs: List[StubRunner] = []
    queue = _make_queue(parallel=True, stubs=stubs)
    proj_a = _project(tmp_path, "a", ranks=8)
    proj_b = _project(tmp_path, "b", ranks=8)
    proj_c = _project(tmp_path, "c", ranks=8)
    queue.add(proj_a, str(tmp_path / "a"))
    queue.add(proj_b, str(tmp_path / "b"))
    queue.add(proj_c, str(tmp_path / "c"))

    queue.start()

    assert len(stubs) == 2
    assert proj_a.resources.mpi_ranks == 4
    assert proj_b.resources.mpi_ranks == 4
    assert queue.items[2].status == "pending"

    stubs[0].finish("finished")

    assert len(stubs) == 3
    assert proj_c.resources.mpi_ranks == 4
    assert queue.items[2].status == "running"


def test_queue_finished_emitted_once_all_items_done(tmp_path: Path):
    stubs: List[StubRunner] = []
    queue = _make_queue(parallel=False, stubs=stubs)
    queue.add(_project(tmp_path, "a"), str(tmp_path / "a"))
    queue.add(_project(tmp_path, "b"), str(tmp_path / "b"))

    finished_calls = []
    queue.queue_finished.connect(lambda: finished_calls.append(True))

    queue.start()
    stubs[0].finish()
    assert finished_calls == []
    stubs[1].finish()
    assert finished_calls == [True]


def test_stopped_status_also_advances_queue(tmp_path: Path):
    stubs: List[StubRunner] = []
    queue = _make_queue(parallel=False, stubs=stubs)
    queue.add(_project(tmp_path, "a"), str(tmp_path / "a"))
    queue.add(_project(tmp_path, "b"), str(tmp_path / "b"))

    queue.start()
    stubs[0].finish("stopped")
    assert queue.items[0].status == "stopped"
    assert queue.items[1].status == "running"
