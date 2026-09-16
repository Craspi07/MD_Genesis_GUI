"""A small embedded-matplotlib line-plot widget shared by the Run and
Analysis tabs (F3/F5). Uses FigureCanvasQTAgg per CLAUDE.md — no
Plotly/WebEngine.

Roadmap Phase 6: supports a secondary y-axis (`axis="secondary"`) so
series with unrelated units/scales (e.g. energy in kcal/mol vs.
temperature in K) don't get silently squashed onto one shared axis --
the Run tab's energy/temperature plot did exactly that before this
change, where temperature's ~300 K line was nearly invisible next to
energy terms in the thousands.
"""
from __future__ import annotations

from typing import Dict, Sequence

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
        self._axes2 = None  # lazily created secondary y-axis
        self._lines: Dict[str, "matplotlib.lines.Line2D"] = {}
        self._lines2: Dict[str, "matplotlib.lines.Line2D"] = {}
        super().__init__(self.figure)
        if parent is not None:
            self.setParent(parent)

    def _secondary_axes(self):
        if self._axes2 is None:
            self._axes2 = self.axes.twinx()
        return self._axes2

    def set_series(self, name: str, x: Sequence[float], y: Sequence[float], axis: str = "primary", ylabel: str = "") -> None:
        """Plot/update one named series. `axis="secondary"` puts it on a
        second y-axis sharing the same x-axis, for a series whose scale
        or units don't belong on the primary axis."""
        target_axes = self._secondary_axes() if axis == "secondary" else self.axes
        lines = self._lines2 if axis == "secondary" else self._lines

        if name not in lines:
            (line,) = target_axes.plot(x, y, label=name, linestyle="--" if axis == "secondary" else "-")
            lines[name] = line
            if ylabel and axis == "secondary":
                target_axes.set_ylabel(ylabel)
            self._update_combined_legend()
        else:
            lines[name].set_data(x, y)

    def _update_combined_legend(self) -> None:
        handles = list(self._lines.values()) + list(self._lines2.values())
        labels = list(self._lines.keys()) + list(self._lines2.keys())
        if handles:
            self.axes.legend(handles, labels, loc="upper right", fontsize="small")

    def rescale_and_draw(self) -> None:
        self.axes.relim()
        self.axes.autoscale_view()
        if self._axes2 is not None:
            self._axes2.relim()
            self._axes2.autoscale_view()
        self.draw_idle()

    def clear(self) -> None:
        self.axes.cla()
        self._lines.clear()
        self.axes.set_xlabel("Step")
        if self._axes2 is not None:
            self.figure.delaxes(self._axes2)
            self._axes2 = None
        self._lines2.clear()
