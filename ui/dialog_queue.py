"""Queue dialog: pick recent projects to run sequentially, or two at once
with each halving its requested cores (F3's queue requirement).
"""
from __future__ import annotations

from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QButtonGroup,
    QPushButton,
    QLabel,
)

from app.project import Project
from app.run_queue import RunQueue
from app.settings import Settings


class QueueDialog(QDialog):
    def __init__(self, settings: Settings, recent_projects: List[str], parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Run Queue")
        self.resize(520, 420)
        self.queue: RunQueue | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select recent projects to queue:"))

        self.list_widget = QListWidget()
        for path in recent_projects:
            item = QListWidgetItem(path)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        mode_row = QHBoxLayout()
        self.sequential_radio = QRadioButton("Run sequentially")
        self.parallel_radio = QRadioButton("Run two at once (half cores each)")
        self.sequential_radio.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.sequential_radio)
        group.addButton(self.parallel_radio)
        mode_row.addWidget(self.sequential_radio)
        mode_row.addWidget(self.parallel_radio)
        layout.addLayout(mode_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        start_button = QPushButton("Start Queue")
        start_button.clicked.connect(self._on_start)
        layout.addWidget(start_button)

    def _checked_paths(self) -> List[str]:
        paths = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                paths.append(item.text())
        return paths

    def _on_start(self) -> None:
        paths = self._checked_paths()
        if not paths:
            self.status_label.setText("Select at least one project.")
            return

        self.queue = RunQueue(self.settings, parallel=self.parallel_radio.isChecked())
        loaded = 0
        for path in paths:
            try:
                project = Project.load(path)
            except (OSError, ValueError):
                continue
            self.queue.add(project, path)
            loaded += 1

        if loaded == 0:
            self.status_label.setText("Could not load any of the selected projects.")
            return

        self.queue.item_started.connect(self._on_item_started)
        self.queue.item_finished.connect(self._on_item_finished)
        self.queue.queue_finished.connect(lambda: self.status_label.setText("Queue finished."))
        self.status_label.setText(f"Starting queue with {loaded} project(s)...")
        self.queue.start()

    def _on_item_started(self, index: int) -> None:
        item = self.queue.items[index]
        self.status_label.setText(f"Started: {item.project.name}")

    def _on_item_finished(self, index: int, status: str) -> None:
        item = self.queue.items[index]
        self.status_label.setText(f"{item.project.name}: {status}")
