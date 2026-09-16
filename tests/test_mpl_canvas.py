from ui.widgets.mpl_canvas import MplCanvas


def test_primary_series_plotted_on_main_axes():
    canvas = MplCanvas(title="t", ylabel="Energy")
    canvas.set_series("TOTAL_ENE", [0, 1, 2], [1.0, 2.0, 3.0])
    assert "TOTAL_ENE" in canvas._lines
    assert canvas._axes2 is None


def test_secondary_series_creates_twin_axis():
    canvas = MplCanvas(title="t", ylabel="Energy")
    canvas.set_series("TOTAL_ENE", [0, 1], [1.0, 2.0])
    canvas.set_series("TEMPERATURE", [0, 1], [300.0, 301.0], axis="secondary", ylabel="Temperature (K)")

    assert canvas._axes2 is not None
    assert "TEMPERATURE" in canvas._lines2
    assert "TOTAL_ENE" not in canvas._lines2
    assert canvas._axes2.get_ylabel() == "Temperature (K)"


def test_updating_existing_series_does_not_duplicate_line():
    canvas = MplCanvas()
    canvas.set_series("X", [0, 1], [1.0, 2.0])
    canvas.set_series("X", [0, 1, 2], [1.0, 2.0, 3.0])
    assert len(canvas._lines) == 1
    assert list(canvas._lines["X"].get_ydata()) == [1.0, 2.0, 3.0]


def test_clear_removes_secondary_axis():
    canvas = MplCanvas()
    canvas.set_series("A", [0], [1.0])
    canvas.set_series("B", [0], [2.0], axis="secondary")
    assert canvas._axes2 is not None

    canvas.clear()
    assert canvas._axes2 is None
    assert canvas._lines == {}
    assert canvas._lines2 == {}


def test_rescale_and_draw_handles_secondary_axis_without_error():
    canvas = MplCanvas()
    canvas.set_series("A", [0, 1], [1.0, 2.0])
    canvas.set_series("B", [0, 1], [300.0, 305.0], axis="secondary")
    canvas.rescale_and_draw()  # must not raise
