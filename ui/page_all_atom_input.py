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

from typing import List

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


class _FileListWidget(QWidget):
    """A QListWidget plus Add/Remove buttons for picking N files."""

    def __init__(self, dialog_caption: str, file_filter: str, parent=None):
        super().__init__(parent)
        self._dialog_caption = dialog_caption
        self._file_filter = file_filter

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

    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, self._dialog_caption, "", self._file_filter)
        for path in paths:
            self.list_widget.addItem(path)

    def _on_remove(self) -> None:
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def paths(self) -> List[str]:
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]


class AllAtomInputPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("All-Atom System Files")
        self.setSubTitle(
            "Point to the already-prepared CHARMM system (from CHARMM-GUI, VMD/PSFGEN, or CHARMM)."
        )

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "GENESIS never builds atomistic systems itself -- these files must already exist."
        ))

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
        path, _ = QFileDialog.getOpenFileName(self, "Select PSF file", "", "PSF files (*.psf);;All files (*)")
        if path:
            self.psf_path_edit.setText(path)

    def _on_browse_pdb(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select PDB file", "", "PDB files (*.pdb);;All files (*)")
        if path:
            self.pdb_path_edit.setText(path)

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
