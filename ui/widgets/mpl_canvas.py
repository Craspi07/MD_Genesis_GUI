"""A small embedded-matplotlib line-plot widget shared by the Run and
Analysis tabs (F3/F5). Uses FigureCanvasQTAgg per CLAUDE.md — no
Plotly/WebEngine.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

import matplotlib

matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, title: str = "", ylabel: str = "", width=5, height=3, dpi=100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_title(title)
        self.axes.set_xlabel("Step")
        self.axes.set_ylabel(ylabel)
        self._lines: Dict[str, "matplotlib.lines.Line2D"] = {}
        super().__init__(self.figure)
        if parent is not None:
            self.setParent(parent)

    def set_series(self, name: str, x: Sequence[float], y: Sequence[float]) -> None:
        if name not in self._lines:
            (line,) = self.axes.plot(x, y, label=name)
            self._lines[name] = line
            self.axes.legend(loc="upper right", fontsize="small")
        else:
            self._lines[name].set_data(x, y)

    def rescale_and_draw(self) -> None:
        self.axes.relim()
        self.axes.autoscale_view()
        self.draw_idle()

    def clear(self) -> None:
        self.axes.cla()
        self._lines.clear()
        self.axes.set_xlabel("Step")
