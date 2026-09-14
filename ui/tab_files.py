"""Files tab: view/edit every generated file in a project directory, with
a "keep my edits" vs "regenerate" choice (F project-files requirement).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from app.text_io import write_user_text

from PyQt5.QtCore import QObject, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QLabel,
    QSplitter,
    QMessageBox,
)
from PyQt5.QtCore import Qt

from app.project import Project
from app.settings import Settings
from app.wsl import WslBridge

# Files the wizard/runner generates and knows how to regenerate. Anything
# else in the project directory (logs, .dcd, etc.) is view-only here.
REGENERATABLE_FILES = {"run.inp"}


class ValidateWorker(QObject):
    """Runs app.ctrl_reference.validate_against_installed_genesis off the
    GUI thread (it shells out to WSL) -- see DECISIONS.md, 2026-09-14."""

    finished = pyqtSignal(list)  # List[str] warnings

    def __init__(self, bridge: WslBridge, engine: str, control_text: str):
        super().__init__()
        self.bridge = bridge
        self.engine = engine
        self.control_text = control_text

    def run(self) -> None:
        from app.ctrl_reference import validate_against_installed_genesis

        warnings = validate_against_installed_genesis(self.bridge, self.engine, self.control_text)
        self.finished.emit(warnings)


class FilesTab(QWidget):
    def __init__(self, project: Project, local_directory: str, settings: Optional[Settings] = None, parent=None):
        super().__init__(parent)
        self.project = project
        self.local_directory = local_directory
        self.settings = settings or Settings()
        self._current_file: Optional[Path] = None
        self._loaded_text = ""
        self._validate_thread: Optional[QThread] = None
        self._validate_worker: Optional[ValidateWorker] = None

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        open_folder_button = QPushButton("Open folder")
        open_folder_button.clicked.connect(self._open_folder)
        top_row.addWidget(open_folder_button)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        top_row.addWidget(refresh_button)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        splitter = QSplitter(Qt.Horizontal)
        self.file_list = QListWidget()
        self.file_list.currentItemChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.file_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        right_layout.addWidget(self.editor)

        button_row = QHBoxLayout()
        self.save_button = QPushButton("Save edits")
        self.save_button.clicked.connect(self._on_save)
        self.save_button.setEnabled(False)
        button_row.addWidget(self.save_button)

        self.regenerate_button = QPushButton("Regenerate (discard edits)")
        self.regenerate_button.clicked.connect(self._on_regenerate)
        self.regenerate_button.setEnabled(False)
        button_row.addWidget(self.regenerate_button)

        self.validate_button = QPushButton("Validate against GENESIS")
        self.validate_button.clicked.connect(self._on_validate)
        self.validate_button.setEnabled(False)
        self.validate_button.setToolTip(
            "Cross-checks this file against the installed GENESIS's own "
            "`<engine> -h ctrl_all` template output -- see DECISIONS.md."
        )
        button_row.addWidget(self.validate_button)
        button_row.addStretch(1)
        right_layout.addLayout(button_row)

        self.edited_label = QLabel("")
        right_layout.addWidget(self.edited_label)

        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        self.refresh()

    # -- file list -----------------------------------------------------------
    def refresh(self) -> None:
        self.file_list.clear()
        directory = Path(self.local_directory)
        if not directory.exists():
            return
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.name != "project.json":
                item = QListWidgetItem(path.name)
                self.file_list.addItem(item)

    def _on_selection_changed(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            self._current_file = None
            self.editor.setPlainText("")
            self.editor.setReadOnly(True)
            self.save_button.setEnabled(False)
            self.regenerate_button.setEnabled(False)
            self.validate_button.setEnabled(False)
            return

        filename = current.text()
        path = Path(self.local_directory) / filename
        self._current_file = path
        try:
            self._loaded_text = path.read_text(errors="replace")
        except OSError as exc:
            self._loaded_text = f"Could not read file: {exc}"
        self.editor.setPlainText(self._loaded_text)

        editable = filename in REGENERATABLE_FILES
        self.editor.setReadOnly(not editable)
        self.save_button.setEnabled(editable)
        self.regenerate_button.setEnabled(editable)
        self.validate_button.setEnabled(filename == "run.inp")

        if filename in self.project.files_with_manual_edits:
            self.edited_label.setText("⚠ This file has manual edits and will not be auto-regenerated.")
        else:
            self.edited_label.setText("")

    # -- editing ---------------------------------------------------------------
    def _on_save(self) -> None:
        if self._current_file is None:
            return
        text = self.editor.toPlainText()
        write_user_text(self._current_file, text)
        filename = self._current_file.name
        if filename not in self.project.files_with_manual_edits:
            self.project.files_with_manual_edits.append(filename)
        self.project.save(self.local_directory)
        self.edited_label.setText("⚠ This file has manual edits and will not be auto-regenerated.")

    def _on_regenerate(self) -> None:
        if self._current_file is None:
            return
        filename = self._current_file.name
        if filename in self.project.files_with_manual_edits:
            reply = QMessageBox.question(
                self,
                "Discard manual edits?",
                f"{filename} has manual edits. Regenerating will overwrite them. Continue?",
            )
            if reply != QMessageBox.Yes:
                return

        if filename == "run.inp":
            from app.project_creation import generate_project_control_file

            generate_project_control_file(self.project, self.local_directory, force=True)

        if filename in self.project.files_with_manual_edits:
            self.project.files_with_manual_edits.remove(filename)
        self.project.save(self.local_directory)

        self._loaded_text = self._current_file.read_text(errors="replace")
        self.editor.setPlainText(self._loaded_text)
        self.edited_label.setText("")

    # -- validation against the real installed GENESIS --------------------------
    def _on_validate(self) -> None:
        if self._validate_thread is not None or self._current_file is None:
            return
        self.validate_button.setEnabled(False)
        self.edited_label.setText("Checking against the installed GENESIS's -h ctrl_all output...")

        bridge = WslBridge(distro=self.settings.distro)
        engine = self.project.resources.engine.value
        control_text = self.editor.toPlainText()

        self._validate_thread = QThread(self)
        self._validate_worker = ValidateWorker(bridge, engine, control_text)
        self._validate_worker.moveToThread(self._validate_thread)
        self._validate_thread.started.connect(self._validate_worker.run)
        self._validate_worker.finished.connect(self._on_validate_finished)
        self._validate_worker.finished.connect(self._validate_thread.quit)
        self._validate_thread.finished.connect(self._cleanup_validate_thread)
        self._validate_thread.start()

    def _cleanup_validate_thread(self) -> None:
        self.validate_button.setEnabled(self._current_file is not None and self._current_file.name == "run.inp")
        self._validate_thread = None
        self._validate_worker = None

    def _on_validate_finished(self, warnings: List[str]) -> None:
        if self._current_file and self._current_file.name in self.project.files_with_manual_edits:
            self.edited_label.setText("⚠ This file has manual edits and will not be auto-regenerated.")
        else:
            self.edited_label.setText("")
        if not warnings:
            QMessageBox.information(
                self, "Validation", "No mismatches found against the installed GENESIS's -h ctrl_all output."
            )
        else:
            QMessageBox.warning(self, "Validation", "\n".join(f"- {w}" for w in warnings))

    # -- misc --------------------------------------------------------------
    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.local_directory))
