"""New Project wizard (F2): Input -> Model -> Parameters -> Resources -> Review."""
from __future__ import annotations

from PyQt5.QtWidgets import QWizard

from app.settings import Settings
from ui.page_input import InputPage
from ui.page_model import ModelPage, InputState


class NewProjectWizard(QWizard):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("New Project")
        self.setWizardStyle(QWizard.ModernStyle)
        self.resize(760, 640)

        self.input_page = InputPage()
        self.model_page = ModelPage(self._input_state)

        self.addPage(self.input_page)
        self.addPage(self.model_page)

    def _input_state(self) -> InputState:
        is_sequence = self.input_page.is_sequence_mode()
        has_dna_hint = False
        if not is_sequence and self.input_page.pdb_info is not None:
            # crude DNA hint: any chain whose sequence is mostly A/C/G/T
            for chain in self.input_page.pdb_info.chains:
                seq = chain.sequence
                if seq and sum(c in "ACGT" for c in seq) / len(seq) > 0.9:
                    has_dna_hint = True
                    break
        return InputState(is_sequence_mode=is_sequence, has_dna_hint=has_dna_hint)
