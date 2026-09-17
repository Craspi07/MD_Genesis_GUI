"""Wizard page: pre-built all-atom (CHARMM) system files.

Only shown when the Input page's "Pre-built all-atom system (CHARMM)"
mode is selected (see ui/wizard_new_project.py's nextId()). GENESIS
User Guide 2.0.0 Sec. 4.1 confirms GENESIS never builds atomistic
systems itself -- topology/parameter/PSF/PDB files must already exist,
prepared by an external tool (CHARMM-GUI, VMD/PSFGEN, or CHARMM). This
page only collects paths to those already-prepared files plus the box
size they were built with (PME needs a periodic box that matches the
real system -- there's no tutorial-derived default to fall back to the
way CG models have one, since guessing here risks silently mismatching
a real prepared system).
"""
from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QDoubleSpinBox,
    QFileDialog,
    QWidget,
)

from app.charmm_gui_import import CharmmGuiExtractResult, extract_charmm_gui_archive


class _FileListWidget(QWidget):
    """A QListWidget plus Add/Remove buttons for picking N files."""

    def __init__(self, dialog_caption: str, file_filter: str, parent=None):
        super().__init__(parent)
        self._dialog_caption = dialog_caption
        self._file_filter = file_filter
        self._start_dir = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(80)
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()
        add_button = QPushButton("Add...")
        add_button.clicked.connect(self._on_add)
        button_row.addWidget(add_button)
        remove_button = QPushButton("Remove selected")
        remove_button.clicked.connect(self._on_remove)
        button_row.addWidget(remove_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

    def set_start_dir(self, start_dir: str) -> None:
        self._start_dir = start_dir

    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, self._dialog_caption, self._start_dir, self._file_filter)
        for path in paths:
            self.list_widget.addItem(path)

    def _on_remove(self) -> None:
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def paths(self) -> List[str]:
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]


class CharmmGuiImportWorker(QObject):
    """Runs extract_charmm_gui_archive() off the GUI thread -- extracting a
    real CHARMM-GUI archive (which bundles its whole toppar/ library,
    tens of MB) shouldn't block the UI for the ~100ms budget CLAUDE.md
    sets. Guards the call the same way every other worker in this codebase
    does (HealthCheckWorker, ProjectCreationWorker): an unhandled
    exception raised on a QThread's slot would otherwise abort the whole
    application instead of surfacing as an error message."""

    finished = pyqtSignal(object)  # CharmmGuiExtractResult

    def __init__(self, archive_path: str):
        super().__init__()
        self.archive_path = archive_path

    def run(self) -> None:
        try:
            result = extract_charmm_gui_archive(self.archive_path)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI instead of crashing
            result = CharmmGuiExtractResult(False, f"Could not import '{self.archive_path}': {exc}")
        self.finished.emit(result)


class AllAtomInputPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("All-Atom System Files")
        self.setSubTitle(
            "Point to the already-prepared CHARMM system (from CHARMM-GUI, VMD/PSFGEN, or CHARMM)."
        )
        self._thread: Optional[QThread] = None
        self._worker: Optional[CharmmGuiImportWorker] = None
        self._browse_start_dir = ""

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "GENESIS never builds atomistic systems itself -- these files must already exist."
        ))

        import_row = QHBoxLayout()
        self.charmm_gui_import_button = QPushButton("Import from CHARMM-GUI archive (.tgz)...")
        self.charmm_gui_import_button.clicked.connect(self._on_import_charmm_gui)
        import_row.addWidget(self.charmm_gui_import_button)
        import_row.addStretch(1)
        layout.addLayout(import_row)
        self.charmm_gui_status_label = QLabel("")
        self.charmm_gui_status_label.setWordWrap(True)
        layout.addWidget(self.charmm_gui_status_label)

        form = QFormLayout()
        layout.addLayout(form)

        self.top_files = _FileListWidget("Select CHARMM topology file(s)", "Topology files (*.rtf *.top);;All files (*)")
        form.addRow("Topology file(s):", self.top_files)

        self.par_files = _FileListWidget("Select CHARMM parameter file(s)", "Parameter files (*.prm *.par);;All files (*)")
        form.addRow("Parameter file(s):", self.par_files)

        self.str_files = _FileListWidget("Select CHARMM stream file(s) (optional)", "Stream files (*.str);;All files (*)")
        form.addRow("Stream file(s) (optional):", self.str_files)

        psf_row = QHBoxLayout()
        self.psf_path_edit = QLineEdit()
        psf_row.addWidget(self.psf_path_edit)
        psf_browse = QPushButton("Browse...")
        psf_browse.clicked.connect(self._on_browse_psf)
        psf_row.addWidget(psf_browse)
        form.addRow("PSF file:", psf_row)

        pdb_row = QHBoxLayout()
        self.pdb_path_edit = QLineEdit()
        pdb_row.addWidget(self.pdb_path_edit)
        pdb_browse = QPushButton("Browse...")
        pdb_browse.clicked.connect(self._on_browse_pdb)
        pdb_row.addWidget(pdb_browse)
        form.addRow("PDB file:", pdb_row)

        self.box_x = QDoubleSpinBox()
        self.box_y = QDoubleSpinBox()
        self.box_z = QDoubleSpinBox()
        box_row = QHBoxLayout()
        for box in (self.box_x, self.box_y, self.box_z):
            box.setRange(0.0, 100000.0)
            box.setSuffix(" A")
            box.setDecimals(3)
            box.valueChanged.connect(self.completeChanged)
            box_row.addWidget(box)
        form.addRow("Box size (x/y/z):", box_row)
        layout.addWidget(QLabel(
            "Box size must match the box your setup tool already built -- there is no "
            "tutorial-derived default for a real prepared system (see DECISIONS.md)."
        ))

        for widget in (self.psf_path_edit, self.pdb_path_edit):
            widget.textChanged.connect(self.completeChanged)
        self.top_files.list_widget.model().rowsInserted.connect(self.completeChanged)
        self.top_files.list_widget.model().rowsRemoved.connect(self.completeChanged)
        self.par_files.list_widget.model().rowsInserted.connect(self.completeChanged)
        self.par_files.list_widget.model().rowsRemoved.connect(self.completeChanged)

    def _on_browse_psf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PSF file", self._browse_start_dir, "PSF files (*.psf);;All files (*)"
        )
        if path:
            self.psf_path_edit.setText(path)

    def _on_browse_pdb(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PDB file", self._browse_start_dir, "PDB files (*.pdb);;All files (*)"
        )
        if path:
            self.pdb_path_edit.setText(path)

    def _on_import_charmm_gui(self) -> None:
        if self._thread is not None:
            return
        archive_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CHARMM-GUI archive",
            "",
            "CHARMM-GUI archive (*.tgz *.tar.gz);;All files (*)",
        )
        if not archive_path:
            return

        self.charmm_gui_import_button.setEnabled(False)
        self.charmm_gui_status_label.setText("Extracting and reading the archive...")
        self._thread = QThread(self)
        self._worker = CharmmGuiImportWorker(archive_path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_import_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_import_thread)
        self._thread.start()

    def _cleanup_import_thread(self) -> None:
        self._thread = None
        self._worker = None
        self.charmm_gui_import_button.setEnabled(True)

    def _on_import_finished(self, result: CharmmGuiExtractResult) -> None:
        self.charmm_gui_status_label.setText(result.message)
        if not result.success:
            return

        # Topology/parameter/stream selection is deliberately left to the
        # user (see app/charmm_gui_import.py) -- but point their Add.../
        # Browse... dialogs straight at the extracted files instead of a
        # blank picker, since digging through the archive by hand was the
        # actual "can't open .tgz on Windows" problem this solves.
        start_dir = result.toppar_dir or result.extracted_dir
        self.top_files.set_start_dir(start_dir)
        self.par_files.set_start_dir(start_dir)
        self.str_files.set_start_dir(start_dir)
        self._browse_start_dir = result.extracted_dir

        if result.psf_path:
            self.psf_path_edit.setText(result.psf_path)
        if result.pdb_path:
            self.pdb_path_edit.setText(result.pdb_path)
        if result.box_x is not None:
            self.box_x.setValue(result.box_x)
        if result.box_y is not None:
            self.box_y.setValue(result.box_y)
        if result.box_z is not None:
            self.box_z.setValue(result.box_z)

    def isComplete(self) -> bool:
        return (
            bool(self.top_files.paths())
            and bool(self.par_files.paths())
            and bool(self.psf_path_edit.text().strip())
            and bool(self.pdb_path_edit.text().strip())
            and self.box_x.value() > 0
            and self.box_y.value() > 0
            and self.box_z.value() > 0
        )
