"""Wizard page 1: drag-drop PDB/CIF, or a pasted sequence (F2.1)."""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QButtonGroup,
    QPushButton,
    QFileDialog,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QStackedWidget,
    QWidget,
)

from app.validators import parse_pdb, PdbParseError, validate_sequence, PdbInfo


class DropArea(QFrame):
    """A simple drag-drop target for a single PDB/CIF file."""

    def __init__(self, on_file_dropped, parent=None):
        super().__init__(parent)
        self._on_file_dropped = on_file_dropped
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(100)
        layout = QVBoxLayout(self)
        self.label = QLabel("Drag a .pdb or .cif file here, or click Browse below")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self._on_file_dropped(urls[0].toLocalFile())


class InputPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Input")
        self.setSubTitle("Provide a structure file or paste a sequence.")

        self.pdb_info: Optional[PdbInfo] = None
        self.pdb_path: str = ""
        self.sequence_text: str = ""

        layout = QVBoxLayout(self)

        mode_row = QHBoxLayout()
        self.pdb_radio = QRadioButton("Structure file (PDB / CIF)")
        self.seq_radio = QRadioButton("Sequence (for disordered proteins)")
        self.pdb_radio.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.pdb_radio)
        group.addButton(self.seq_radio)
        mode_row.addWidget(self.pdb_radio)
        mode_row.addWidget(self.seq_radio)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.pdb_radio.toggled.connect(self._on_mode_changed)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # -- PDB mode widget --
        pdb_widget = QWidget()
        pdb_layout = QVBoxLayout(pdb_widget)
        self.drop_area = DropArea(self._load_pdb)
        pdb_layout.addWidget(self.drop_area)

        browse_row = QHBoxLayout()
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_pdb)
        browse_row.addWidget(browse_button)
        self.path_label = QLabel("No file selected")
        browse_row.addWidget(self.path_label, stretch=1)
        pdb_layout.addLayout(browse_row)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        pdb_layout.addWidget(self.summary_label)

        self.chain_table = QTableWidget(0, 3)
        self.chain_table.setHorizontalHeaderLabels(["Chain", "Residues", "Notes"])
        self.chain_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.chain_table.verticalHeader().setVisible(False)
        pdb_layout.addWidget(self.chain_table)

        self.stack.addWidget(pdb_widget)

        # -- sequence mode widget --
        seq_widget = QWidget()
        seq_layout = QVBoxLayout(seq_widget)
        seq_layout.addWidget(QLabel(
            "Paste an amino-acid sequence (one-letter codes; a FASTA header "
            "line starting with '>' is fine and will be ignored)."
        ))
        self.sequence_edit = QTextEdit()
        self.sequence_edit.setPlaceholderText("MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEK...")
        self.sequence_edit.textChanged.connect(self._on_sequence_changed)
        seq_layout.addWidget(self.sequence_edit)
        self.sequence_status_label = QLabel("")
        seq_layout.addWidget(self.sequence_status_label)
        self.stack.addWidget(seq_widget)

    # -- mode switching --------------------------------------------------
    def _on_mode_changed(self, pdb_checked: bool) -> None:
        self.stack.setCurrentIndex(0 if pdb_checked else 1)
        self.completeChanged.emit()

    # -- PDB handling ------------------------------------------------------
    def _browse_pdb(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select structure file", "", "Structure files (*.pdb *.cif *.ent);;All files (*)"
        )
        if path:
            self._load_pdb(path)

    def _load_pdb(self, path: str) -> None:
        self.path_label.setText(path)
        try:
            info = parse_pdb(path)
        except PdbParseError as exc:
            self.pdb_info = None
            self.pdb_path = ""
            self.summary_label.setText(f"Could not read file: {exc}")
            self.chain_table.setRowCount(0)
            self.completeChanged.emit()
            return

        self.pdb_info = info
        self.pdb_path = path
        n_chains = len(info.chains)
        summary = f"{n_chains} chain(s), {info.total_residues} residue(s) total."
        if info.hetatm_groups:
            summary += f" HETATM groups: {', '.join(info.hetatm_groups)}."
        if info.warnings:
            summary += "\n" + "\n".join(f"⚠ {w}" for w in info.warnings)
        self.summary_label.setText(summary)

        self.chain_table.setRowCount(n_chains)
        for row, chain in enumerate(info.chains):
            self.chain_table.setItem(row, 0, QTableWidgetItem(chain.chain_id))
            self.chain_table.setItem(row, 1, QTableWidgetItem(str(chain.residue_count)))
            notes = []
            if chain.nonstandard_residues:
                notes.append(f"{len(chain.nonstandard_residues)} non-standard residue(s)")
            if chain.residue_gaps:
                notes.append(f"gaps: {', '.join(chain.residue_gaps)}")
            self.chain_table.setItem(row, 2, QTableWidgetItem("; ".join(notes)))

        self.completeChanged.emit()

    # -- sequence handling ---------------------------------------------------
    def _on_sequence_changed(self) -> None:
        raw = self.sequence_edit.toPlainText()
        result = validate_sequence(raw)
        self.sequence_text = result.cleaned
        if not raw.strip():
            self.sequence_status_label.setText("")
        elif result.valid:
            self.sequence_status_label.setText(f"{result.length} residues — looks good.")
        else:
            self.sequence_status_label.setText("⚠ " + " ".join(result.errors))
        self.completeChanged.emit()

    # -- QWizardPage overrides ------------------------------------------------
    def isComplete(self) -> bool:
        if self.pdb_radio.isChecked():
            return self.pdb_info is not None
        result = validate_sequence(self.sequence_edit.toPlainText())
        return result.valid

    def is_sequence_mode(self) -> bool:
        return self.seq_radio.isChecked()
