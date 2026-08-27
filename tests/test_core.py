from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from bencharc_sec.core import (
    PlotSettings,
    TraceData,
    detect_plot_rectangle,
    digitize_image,
    integrate_peak,
    prepare_trace,
    read_trace,
    render_svg,
)


def test_reads_utf16_unicorn_export(tmp_path: Path) -> None:
    content = (
        "Chrom.1\t\tChrom.1\t\tChrom.1\t\tChrom.1\t\tChrom.1\t\n"
        "UV\t\tCond\t\tConc B\t\tRun Log\t\tFraction\t\n"
        "ml\tmAU\tml\tmS/cm\tml\t%\tml\tLogbook\tml\tFraction\n"
        "0\t1\t0\t30\t0\t0\t0\tSample Application\t7\t2\n"
        "5\t2\t5\t31\t5\t0\t5\tElution\t8\t3\n"
        "10\t8\t10\t32\t10\t0\t\t\t9\t4\n"
    )
    source = tmp_path / "unicorn.txt"
    source.write_text(content, encoding="utf-16")

    trace = read_trace(source)

    assert trace.x_name == "UV ml"
    assert trace.y_name == "UV mAU"
    assert trace.metadata["elution_start"] == 5
    np.testing.assert_allclose(trace.x, [0, 5, 10])
    np.testing.assert_allclose(trace.y, [1, 2, 8])


def test_reference_svg_is_valid_and_records_no_transformations() -> None:
    x = np.linspace(6, 18, 120)
    y = 1 + 25 * np.exp(-0.5 * ((x - 13) / 0.55) ** 2)
    trace = TraceData(x, y, "ml", "mAU", "raw-data")
    settings = PlotSettings(6, 18, 0, 35, 2, 0.5, 5, 1)

    svg = render_svg(trace, settings)

    ET.fromstring(svg)
    assert 'stroke="#858585"' in svg
    assert 'stroke-width="7.0"' in svg
    assert "transformations=none" in svg
    assert "Elution volume (ml)" in svg
    assert "UV 280 (mAU)" in svg


def test_large_trace_is_split_into_illustrator_safe_polylines() -> None:
    x = np.linspace(0, 20, 4_500)
    trace = TraceData(x, np.sin(x) + 2, "ml", "mAU", "raw-data")
    settings = PlotSettings(0, 20, 0, 4, 2, 0.5, 1, 0.2)

    root = ET.fromstring(render_svg(trace, settings))
    polylines = root.findall("{http://www.w3.org/2000/svg}polyline")
    point_groups = [polyline.attrib["points"].split() for polyline in polylines]

    assert len(polylines) == 3
    assert max(map(len, point_groups)) <= 2_000
    assert all(left[-1] == right[0] for left, right in zip(point_groups, point_groups[1:]))


def test_detects_axes_and_digitizes_colored_trace(tmp_path: Path) -> None:
    path = tmp_path / "chromatogram.png"
    image = Image.new("RGB", (500, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.line((4, 0, 4, 319), fill="black", width=3)  # screenshot/window border
    draw.line((70, 30, 70, 270), fill="black", width=5)
    draw.line((30, 270, 460, 270), fill="black", width=5)  # outward zero tick + x-axis
    points = []
    for pixel_x in range(80, 451):
        data_x = (pixel_x - 70) / (460 - 70) * 12 + 6
        data_y = 1 + 25 * np.exp(-0.5 * ((data_x - 13) / 0.6) ** 2)
        pixel_y = 270 - data_y / 35 * (270 - 30)
        points.append((pixel_x, round(pixel_y)))
    draw.line(points, fill="#858585", width=7)
    image.save(path)

    rectangle = detect_plot_rectangle(path)
    trace = digitize_image(path, rectangle, (6, 18, 0, 35), "#858585", tolerance=12)

    assert trace.approximate is True
    assert abs(rectangle[0] - 70) < 5
    assert len(trace.x) > 300
    peak = int(np.argmax(trace.y))
    assert abs(trace.x[peak] - 13) < 0.2
    assert abs(trace.y[peak] - 26) < 1.0


def test_normalizes_to_selected_peak_and_integrates_area() -> None:
    trace = TraceData(
        x=np.asarray([0, 1, 2, 3, 4], dtype=float),
        y=np.asarray([2, 2, 4, 2, 2], dtype=float),
        x_name="ml",
        y_name="mAU",
        source_kind="raw-data",
    )
    settings = PlotSettings(
        0,
        4,
        0,
        1.05,
        1,
        0.5,
        0.2,
        0.05,
        normalize=True,
        normalization_mode="peak",
        normalization_peak_x=2.0,
        normalization_window=0.2,
        show_area=True,
        area_start=1.0,
        area_end=3.0,
    )

    x, y, notes = prepare_trace(trace, settings)
    result = integrate_peak(trace, settings)
    svg = render_svg(trace, settings)

    np.testing.assert_allclose(x, trace.x)
    np.testing.assert_allclose(y, [0.5, 0.5, 1.0, 0.5, 0.5])
    assert "normalized to peak at 2 ml" in notes[0]
    assert result.raw_area == 6.0
    assert result.baseline_corrected_area == 2.0
    assert result.displayed_area == 1.5
    assert result.normalization_x == 2.0
    assert result.normalization_y == 4.0
    assert "<polygon" in svg
    assert "linear_baseline_corrected_area=2" in svg


def test_selected_peak_normalization_uses_local_maximum() -> None:
    x = np.linspace(0, 10, 101)
    y = 2 + 8 * np.exp(-0.5 * ((x - 3) / 0.3) ** 2) + 4 * np.exp(-0.5 * ((x - 7) / 0.3) ** 2)
    trace = TraceData(x, y, "ml", "mAU", "raw-data")
    settings = PlotSettings(
        0,
        10,
        0,
        1.05,
        2,
        0.5,
        0.2,
        0.05,
        normalize=True,
        normalization_mode="peak",
        normalization_peak_x=7.0,
        normalization_window=0.4,
    )

    normalized_x, normalized_y, _ = prepare_trace(trace, settings)
    local = np.abs(normalized_x - 7.0) <= 0.4

    assert np.isclose(normalized_y[local].max(), 1.0)
    assert normalized_y.max() > 1.5
