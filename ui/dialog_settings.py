"""First-run setup + health check dialog (F1)."""
from __future__ import annotations

from pathlib import Path
from typing import List

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialogButtonBox,
    QGroupBox,
    QFileDialog,
)
from PyQt5.QtGui import QColor

from app.settings import Settings
from app.wsl import WslBridge, HealthCheckItem


class HealthCheckWorker(QObject):
    """Runs WslBridge.health_check() off the GUI thread (it makes several
    blocking subprocess calls and can take up to ~90s on first run while
    Julia precompiles — see CLAUDE.md / gotcha #5)."""

    finished = pyqtSignal(list)
    errored = pyqtSignal(str)

    def __init__(self, bridge: WslBridge):
        super().__init__()
        self.bridge = bridge

    def run(self) -> None:
        try:
            items = self.bridge.health_check()
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            self.errored.emit(str(exc))
            return
        self.finished.emit(items)


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Setup & Health Check")
        self.resize(720, 560)

        self._thread: QThread | None = None
        self._worker: HealthCheckWorker | None = None

        self._build_ui()
        self._populate_from_settings()

    # -- construction ------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        setup_group = QGroupBox("WSL setup")
        form = QFormLayout(setup_group)

        self.distro_combo = QComboBox()
        self.distro_combo.setEditable(True)
        self.distro_combo.addItem(self.settings.distro)
        form.addRow("WSL distro:", self.distro_combo)

        detect_row = QHBoxLayout()
        self.detect_button = QPushButton("Detect installed distros")
        self.detect_button.clicked.connect(self._on_detect_distros)
        detect_row.addWidget(self.detect_button)
        detect_row.addStretch(1)
        form.addRow("", detect_row)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Linux username inside WSL")
        form.addRow("Linux user:", self.user_edit)

        self.mpi_args_edit = QLineEdit()
        form.addRow("mpirun extra args:", self.mpi_args_edit)

        vmd_row = QHBoxLayout()
        self.vmd_path_edit = QLineEdit()
        self.vmd_path_edit.setPlaceholderText(r"C:\Program Files\...\vmd.exe")
        vmd_row.addWidget(self.vmd_path_edit)
        self.vmd_browse_button = QPushButton("Browse...")
        self.vmd_browse_button.clicked.connect(self._on_browse_vmd)
        vmd_row.addWidget(self.vmd_browse_button)
        form.addRow("VMD path:", vmd_row)

        layout.addWidget(setup_group)

        check_group = QGroupBox("Health check")
        check_layout = QVBoxLayout(check_group)

        self.run_button = QPushButton("Run health check")
        self.run_button.clicked.connect(self._on_run_health_check)
        check_layout.addWidget(self.run_button)

        self.status_label = QLabel("Not run yet.")
        check_layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Check", "Status", "Detail / Fix"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        check_layout.addWidget(self.table)

        layout.addWidget(check_group, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_from_settings(self) -> None:
        self.distro_combo.setCurrentText(self.settings.distro)
        self.user_edit.setText(self.settings.linux_user)
        self.mpi_args_edit.setText(self.settings.mpi_extra_args)
        self.vmd_path_edit.setText(self.settings.vmd_path)

    # -- actions -------------------------------------------------------------
    def _current_bridge(self) -> WslBridge:
        return WslBridge(distro=self.distro_combo.currentText().strip() or "Ubuntu-24.04")

    def _on_detect_distros(self) -> None:
        bridge = self._current_bridge()
        distros = bridge.list_distros()
        current = self.distro_combo.currentText()
        self.distro_combo.clear()
        if distros:
            self.distro_combo.addItems(distros)
        if current and current not in distros:
            self.distro_combo.addItem(current)
        self.distro_combo.setCurrentText(current or (distros[0] if distros else ""))
        if not distros:
            self.status_label.setText(
                "No WSL distros detected. Is WSL installed and wsl.exe on PATH?"
            )

    def _on_run_health_check(self) -> None:
        if self._thread is not None:
            return  # already running
        self.run_button.setEnabled(False)
        self.status_label.setText("Running health check (first run can take ~90s while Julia precompiles)...")
        self.table.setRowCount(0)

        bridge = self._current_bridge()
        self._thread = QThread(self)
        self._worker = HealthCheckWorker(bridge)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_health_check_finished)
        self._worker.errored.connect(self._on_health_check_errored)
        self._worker.finished.connect(self._thread.quit)
        self._worker.errored.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cleanup_thread(self) -> None:
        self.run_button.setEnabled(True)
        self._thread = None
        self._worker = None

    def _on_health_check_errored(self, message: str) -> None:
        self.status_label.setText(f"Health check failed to run: {message}")

    def _on_health_check_finished(self, items: List[HealthCheckItem]) -> None:
        self.table.setRowCount(len(items))
        all_ok = True
        for row, item in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(item.name))
            status_item = QTableWidgetItem("OK" if item.ok else "FAIL")
            status_item.setForeground(QColor("#4CAF50") if item.ok else QColor("#E53935"))
            self.table.setItem(row, 1, status_item)
            detail = item.detail
            if not item.ok and item.fix_hint:
                detail = f"{detail}\nFix: {item.fix_hint}"
            self.table.setItem(row, 2, QTableWidgetItem(detail))
            all_ok = all_ok and item.ok

        self.status_label.setText("All checks passed." if all_ok else "Some checks failed — see table.")
        self.settings.setup_complete = all_ok

    def _on_browse_vmd(self) -> None:
        start_dir = str(Path(self.vmd_path_edit.text()).parent) if self.vmd_path_edit.text() else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Locate vmd.exe", start_dir, "VMD executable (vmd.exe);;All files (*)"
        )
        if path:
            self.vmd_path_edit.setText(path)

    def _on_save(self) -> None:
        self.settings.distro = self.distro_combo.currentText().strip() or "Ubuntu-24.04"
        self.settings.linux_user = self.user_edit.text().strip()
        self.settings.mpi_extra_args = self.mpi_args_edit.text().strip() or self.settings.mpi_extra_args
        self.settings.vmd_path = self.vmd_path_edit.text().strip() or self.settings.vmd_path
        self.settings.save()
        self.accept()
