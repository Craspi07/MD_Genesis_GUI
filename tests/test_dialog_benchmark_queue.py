from pathlib import Path

from PyQt5.QtCore import Qt

from app.benchmark import BenchmarkResult
from app.project import Project
from app.settings import Settings
from ui.dialog_benchmark import BenchmarkDialog
from ui.dialog_queue import QueueDialog


def _settings() -> Settings:
    s = Settings()
    s.distro = "Ubuntu-24.04"
    s.total_cores = 16
    return s


def test_benchmark_dialog_populates_table_and_enables_apply(tmp_path: Path):
    project = Project(name="p", directory=str(tmp_path))
    dialog = BenchmarkDialog(project, str(tmp_path), _settings())

    results = [
        BenchmarkResult(4, 4, 10.0, 200.0, True),
        BenchmarkResult(8, 2, 8.0, 250.0, True),
        BenchmarkResult(16, 1, None, None, False, "not found"),
    ]
    dialog._on_finished(results)

    assert dialog.table.rowCount() == 3
    assert dialog.apply_button.isEnabled()
    assert "8 x 2" in dialog.status_label.text()

    dialog._on_apply()
    assert project.resources.mpi_ranks == 8
    assert project.resources.omp_threads == 2


def test_benchmark_dialog_disables_apply_when_all_failed(tmp_path: Path):
    project = Project(name="p", directory=str(tmp_path))
    dialog = BenchmarkDialog(project, str(tmp_path), _settings())
    dialog._on_finished([BenchmarkResult(4, 4, None, None, False, "err")])
    assert not dialog.apply_button.isEnabled()


def test_queue_dialog_checked_paths(tmp_path: Path):
    dialog = QueueDialog(_settings(), ["/a", "/b", "/c"])
    dialog.list_widget.item(0).setCheckState(Qt.Checked)
    dialog.list_widget.item(2).setCheckState(Qt.Checked)
    assert dialog._checked_paths() == ["/a", "/c"]


def test_queue_dialog_no_selection_shows_message(tmp_path: Path):
    dialog = QueueDialog(_settings(), ["/a"])
    dialog._on_start()
    assert "Select at least one project" in dialog.status_label.text()
