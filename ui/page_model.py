"""Wizard page 2: plain-language model chooser (F2.2)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QRadioButton,
    QButtonGroup,
    QLabel,
    QGroupBox,
)

from app.project import ModelType


@dataclass
class ModelCard:
    model_type: ModelType
    title: str
    description: str
    advanced: bool = False
    requires_pdb: bool = False
    requires_dna: bool = False


MODEL_CARDS: List[ModelCard] = [
    ModelCard(
        ModelType.AICG2P,
        "Folded protein (AICG2+)",
        "Keeps your protein near its PDB structure using a native-contact "
        "Go-like potential. Use this for domains and complexes whose "
        "structure is already known.",
        requires_pdb=True,
    ),
    ModelCard(
        ModelType.HPS_SINGLE,
        "Disordered protein / IDR (HPS)",
        "A hydropathy-scale model for intrinsically disordered regions and "
        "low-complexity sequences. Needs only the amino-acid sequence.",
    ),
    ModelCard(
        ModelType.HPS_CONDENSATE,
        "Condensate / phase separation (HPS, many copies, slab)",
        "Puts N copies of a chain into an elongated (slab) box to study "
        "droplet / condensate formation. Builds on the HPS model.",
    ),
    ModelCard(
        ModelType.PROTEIN_DNA,
        "Protein-DNA (AICG2+ + 3SPN.2C)",
        "Combines the AICG2+ protein model with the 3SPN.2C DNA model for "
        "protein-DNA complexes. Advanced — requires a DNA chain or sequence.",
        advanced=True,
        requires_pdb=True,
        requires_dna=True,
    ),
]


class ModelPage(QWizardPage):
    def __init__(self, get_input_state: Callable[[], "InputState"], parent=None):
        super().__init__(parent)
        self.setTitle("Model")
        self.setSubTitle("Choose the coarse-grained model that matches your system.")
        self._get_input_state = get_input_state

        self.buttons: List[QRadioButton] = []
        self.group = QButtonGroup(self)
        self._card_by_button = {}

        layout = QVBoxLayout(self)
        for card in MODEL_CARDS:
            box = QGroupBox()
            box_layout = QVBoxLayout(box)
            radio = QRadioButton(card.title + (" [advanced]" if card.advanced else ""))
            desc = QLabel(card.description)
            desc.setWordWrap(True)
            desc.setStyleSheet("color: gray;")
            box_layout.addWidget(radio)
            box_layout.addWidget(desc)
            layout.addWidget(box)
            self.group.addButton(radio)
            self.buttons.append(radio)
            self._card_by_button[radio] = card
            radio.toggled.connect(self.completeChanged)

        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.warning_label)

    def initializePage(self) -> None:
        state = self._get_input_state()
        self.warning_label.setText("")
        for radio in self.buttons:
            card = self._card_by_button[radio]
            enabled = True
            reason = ""
            if card.requires_pdb and state.is_sequence_mode:
                enabled = False
                reason = "requires a structure file, not a pasted sequence"
            if card.requires_dna and not state.has_dna_hint:
                enabled = False
                reason = "requires a DNA chain or sequence (not detected in your input)"
            radio.setEnabled(enabled)
            radio.setToolTip(reason)
            if not enabled and radio.isChecked():
                radio.setChecked(False)

        # default-select the first enabled card if nothing is chosen yet
        if not any(b.isChecked() for b in self.buttons):
            for radio in self.buttons:
                if radio.isEnabled():
                    radio.setChecked(True)
                    break

    def isComplete(self) -> bool:
        return any(b.isChecked() for b in self.buttons)

    def selected_model(self) -> Optional[ModelType]:
        for radio in self.buttons:
            if radio.isChecked():
                return self._card_by_button[radio].model_type
        return None


@dataclass
class InputState:
    """Small view of the Input page's state that the Model page needs,
    without importing PyQt widget internals across pages."""

    is_sequence_mode: bool
    has_dna_hint: bool = False
