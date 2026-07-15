"""Parsing, digitization, and SVG rendering for BenchArc SEC."""

from __future__ import annotations

import csv
import html
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class TraceData:
    x: np.ndarray
    y: np.ndarray
    x_name: str
    y_name: str
    source_kind: str
    approximate: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlotSettings:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    x_major: float
    x_minor: float
    y_major: float
    y_minor: float
    x_label: str = "Elution volume (ml)"
    y_label: str = "UV 280 (mAU)"
    trace_color: str = "#858585"
    trace_width: float = 7.0
    axis_width: float = 5.0
    tick_font_size: float = 34.0
    label_font_size: float = 42.0
    width: int = 900
    height: int = 600
    show_tick_labels: bool = True
    show_peak_label: bool = False
    smooth_window: int = 1
    baseline_subtract: bool = False
    normalize: bool = False
    normalization_mode: str = "maximum"
    normalization_peak_x: float = 0.0
    normalization_window: float = 0.5
    show_area: bool = False
    area_start: float = 0.0
    area_end: float = 0.0


@dataclass(frozen=True)
class PeakAreaResult:
    start: float
    end: float
    raw_area: float
    baseline_corrected_area: float
    displayed_area: float
    normalization_x: float | None = None
    normalization_y: float | None = None


def _parse_number(value: str) -> float | None:
    value = value.strip().replace(",", ".")
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _decode_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def _read_table(path: Path) -> tuple[list[str], list[list[str]], dict[str, Any]]:
    lines = _decode_text(path).splitlines()
    header_line = 0
    for idx, line in enumerate(lines[:80]):
        if line.strip() and max(line.count(delimiter) for delimiter in ("\t", ",", ";")):
            header_line = idx
            break
    text = "\n".join(lines[header_line:])
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters="\t,;")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in text[:8192] else csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    if not rows:
        raise ValueError("The input file is empty.")

    metadata: dict[str, Any] = {}
    if len(rows) >= 4 and any(cell.strip().lower() == "uv" for cell in rows[1]):
        channel_row = rows[1]
        unit_row = rows[2]
        headers: list[str] = []
        current_channel = ""
        column_count = max(len(channel_row), len(unit_row))
        for idx in range(column_count):
            channel = channel_row[idx].strip() if idx < len(channel_row) else ""
            if channel:
                current_channel = channel
            unit = unit_row[idx].strip() if idx < len(unit_row) else ""
            headers.append(" ".join(part for part in (current_channel, unit) if part))

        lower_headers = [name.lower() for name in headers]
        try:
            run_x_idx = lower_headers.index("run log ml")
            run_label_idx = lower_headers.index("run log logbook")
        except ValueError:
            pass
        else:
            for row in rows[3:]:
                if max(run_x_idx, run_label_idx) >= len(row):
                    continue
                if row[run_label_idx].strip().strip('"').lower() == "elution":
                    start = _parse_number(row[run_x_idx])
                    if start is not None:
                        metadata["elution_start"] = start
                        break
        metadata["format"] = "UNICORN multi-channel export"
        return headers, rows[3:], metadata
    return rows[0], rows[1:], metadata


def _numeric_columns(headers: list[str], rows: list[list[str]]) -> list[int]:
    candidates: list[int] = []
    required = max(2, min(5, int(math.ceil(len(rows) * 0.2))))
    for idx in range(len(headers)):
        good = sum(
            _parse_number(row[idx]) is not None
            for row in rows
            if idx < len(row)
        )
        if good >= required:
            candidates.append(idx)
    return candidates


def _score_column(name: str, keywords: Iterable[str], preferred_channel: str) -> int:
    lower = name.lower()
    score = sum(2 for keyword in keywords if keyword in lower)
    if lower.startswith(preferred_channel.lower() + " "):
        score += 20
    return score


def _choose_column(
    headers: list[str],
    candidates: list[int],
    keywords: list[str],
    preferred_channel: str,
) -> int:
    if not candidates:
        raise ValueError("No numeric columns were found.")
    return max(
        candidates,
        key=lambda idx: (
            _score_column(headers[idx], keywords, preferred_channel),
            -candidates.index(idx),
        ),
    )


def read_trace(path: str | Path, preferred_channel: str = "UV") -> TraceData:
    path = Path(path)
    headers, rows, metadata = _read_table(path)
    numeric = _numeric_columns(headers, rows)
    if len(numeric) < 2:
        raise ValueError("Could not find at least two numeric columns.")

    x_idx = _choose_column(
        headers,
        numeric,
        ["elution", "volume", " ml", "time", "min", "cv"],
        preferred_channel,
    )
    y_idx = _choose_column(
        headers,
        [idx for idx in numeric if idx != x_idx],
        ["uv", "280", "a280", "mau", "abs", "absorbance"],
        preferred_channel,
    )

    parsed: list[tuple[float, float]] = []
    for row in rows:
        if max(x_idx, y_idx) >= len(row):
            continue
        x_value = _parse_number(row[x_idx])
        y_value = _parse_number(row[y_idx])
        if x_value is not None and y_value is not None:
            parsed.append((x_value, y_value))
    if len(parsed) < 2:
        raise ValueError("No usable numeric x/y rows were found.")

    parsed.sort(key=lambda item: item[0])
    values = np.asarray(parsed, dtype=float)
    metadata = {
        **metadata,
        "source_name": path.name,
        "point_count": len(values),
        "selected_columns": (headers[x_idx], headers[y_idx]),
    }
    return TraceData(
        x=values[:, 0],
        y=values[:, 1],
        x_name=headers[x_idx],
        y_name=headers[y_idx],
        source_kind="raw-data",
        metadata=metadata,
    )


def _nice_number(value: float) -> float:
    if not math.isfinite(value) or value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    scale = 10**exponent
    fraction = value / scale
    choice = min((1.0, 2.0, 2.5, 5.0, 10.0), key=lambda item: abs(item - fraction))
    return choice * scale


def suggest_settings(trace: TraceData) -> PlotSettings:
    x_min = float(np.nanmin(trace.x))
    x_max = float(np.nanmax(trace.x))
    elution_start = trace.metadata.get("elution_start")
    if isinstance(elution_start, (int, float)) and x_min < elution_start < x_max:
        x_min = float(elution_start)
    visible = (trace.x >= x_min) & (trace.x <= x_max)
    visible_y = trace.y[visible]
    y_min = min(0.0, float(np.nanmin(visible_y)))
    y_max_raw = float(np.nanmax(visible_y))
    x_major = _nice_number((x_max - x_min) / 8)
    y_major = _nice_number((y_max_raw - y_min) / 7)
    y_max = math.ceil(y_max_raw / y_major) * y_major
    return PlotSettings(
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        x_major=x_major,
        x_minor=x_major / 4,
        y_major=y_major,
        y_minor=y_major / 5,
    )


def _smooth(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or len(values) < 3:
        return values
    if window % 2 == 0:
        window += 1
    if window >= len(values):
        return values
    kernel = np.ones(window, dtype=float) / window
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _prepare_base_trace(
    trace: TraceData,
    settings: PlotSettings,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    mask = (trace.x >= settings.x_min) & (trace.x <= settings.x_max)
    x = trace.x[mask]
    y = trace.y[mask].copy()
    if len(x) < 2:
        raise ValueError("No data remain inside the selected x-axis range.")
    notes: list[str] = []
    if settings.smooth_window > 1:
        y = _smooth(y, settings.smooth_window)
        notes.append(f"moving-average smoothing: {settings.smooth_window} points")
    if settings.baseline_subtract:
        y -= float(np.nanmin(y))
        notes.append("baseline subtraction: visible minimum")
    return x, y, notes


def _normalization_reference(
    x: np.ndarray,
    y: np.ndarray,
    settings: PlotSettings,
) -> tuple[float, float]:
    if settings.normalization_mode == "peak":
        window = max(settings.normalization_window, np.finfo(float).eps)
        mask = np.abs(x - settings.normalization_peak_x) <= window
        if not np.any(mask):
            raise ValueError("No points were found in the normalization peak window.")
        indices = np.flatnonzero(mask)
        index = int(indices[int(np.nanargmax(y[mask]))])
    else:
        index = int(np.nanargmax(y))
    value = float(y[index])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("The selected normalization peak must have a positive finite height.")
    return float(x[index]), value


def prepare_trace(trace: TraceData, settings: PlotSettings) -> tuple[np.ndarray, np.ndarray, list[str]]:
    x, y, notes = _prepare_base_trace(trace, settings)
    if settings.normalize:
        reference_x, reference_y = _normalization_reference(x, y, settings)
        y /= reference_y
        if settings.normalization_mode == "peak":
            notes.append(
                f"normalized to peak at {reference_x:.4g} ml "
                f"(search center {settings.normalization_peak_x:.4g} ml, "
                f"half-window {settings.normalization_window:.4g} ml)"
            )
        else:
            notes.append(f"normalized to visible maximum at {reference_x:.4g} ml")
    return x, y, notes


def _interval_points(
    x: np.ndarray,
    y: np.ndarray,
    start: float,
    end: float,
) -> tuple[np.ndarray, np.ndarray]:
    if not start < end:
        raise ValueError("Peak-area start must be smaller than its end.")
    if start < float(x[0]) or end > float(x[-1]):
        raise ValueError("Peak-area bounds must remain inside the available data range.")
    inside = (x > start) & (x < end)
    interval_x = np.concatenate(([start], x[inside], [end]))
    interval_y = np.concatenate(
        ([np.interp(start, x, y)], y[inside], [np.interp(end, x, y)])
    )
    return interval_x, interval_y


def integrate_peak(
    trace: TraceData,
    settings: PlotSettings,
    start: float | None = None,
    end: float | None = None,
) -> PeakAreaResult:
    start = settings.area_start if start is None else start
    end = settings.area_end if end is None else end
    raw_x, raw_y = _interval_points(trace.x, trace.y, start, end)
    raw_area = float(np.trapezoid(raw_y, raw_x))
    linear_baseline = np.interp(raw_x, [start, end], [raw_y[0], raw_y[-1]])
    corrected_area = float(np.trapezoid(raw_y - linear_baseline, raw_x))

    display_x, display_y, _ = prepare_trace(trace, settings)
    area_x, area_y = _interval_points(display_x, display_y, start, end)
    displayed_area = float(np.trapezoid(area_y, area_x))

    normalization_x: float | None = None
    normalization_y: float | None = None
    if settings.normalize:
        base_x, base_y, _ = _prepare_base_trace(trace, settings)
        normalization_x, normalization_y = _normalization_reference(base_x, base_y, settings)
    return PeakAreaResult(
        start=start,
        end=end,
        raw_area=raw_area,
        baseline_corrected_area=corrected_area,
        displayed_area=displayed_area,
        normalization_x=normalization_x,
        normalization_y=normalization_y,
    )


def _ticks(start: float, end: float, interval: float) -> list[float]:
    if interval <= 0 or start >= end:
        return []
    first = math.ceil((start - interval * 1e-8) / interval) * interval
    values: list[float] = []
    value = first
    while value <= end + interval * 1e-8:
        values.append(round(value, 12))
        value += interval
    return values


def _minor_ticks(start: float, end: float, major: float, minor: float) -> list[float]:
    majors = {round(value, 8) for value in _ticks(start, end, major)}
    return [value for value in _ticks(start, end, minor) if round(value, 8) not in majors]


def _format_tick(value: float) -> str:
    if abs(value - round(value)) < 1e-8:
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _scaled_points(
    x: np.ndarray,
    y: np.ndarray,
    settings: PlotSettings,
    plot: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    left, top, width, height = plot
    px = left + (x - settings.x_min) / (settings.x_max - settings.x_min) * width
    py = top + height - (y - settings.y_min) / (settings.y_max - settings.y_min) * height
    return list(zip(px, py))


def render_svg(trace: TraceData, settings: PlotSettings) -> str:
    if not (settings.x_min < settings.x_max and settings.y_min < settings.y_max):
        raise ValueError("Axis minimum values must be smaller than maximum values.")
    x, y, notes = prepare_trace(trace, settings)
    width, height = settings.width, settings.height
    left = width * 0.16
    right_margin = width * 0.055
    top = height * 0.065
    bottom_margin = height * 0.205
    plot_width = width - left - right_margin
    plot_height = height - top - bottom_margin
    bottom = top + plot_height
    right = left + plot_width
    plot = (left, top, plot_width, plot_height)

    points = _scaled_points(x, y, settings, plot)
    polyline = " ".join(f"{px:.2f},{py:.2f}" for px, py in points)
    trace_color = html.escape(settings.trace_color)
    metadata = (
        f"source={html.escape(trace.source_kind)} "
        f"approximate={str(trace.approximate).lower()} "
        f"transformations={html.escape('; '.join(notes) or 'none')}"
    )
    area_markup: list[str] = []
    if settings.show_area:
        result = integrate_peak(trace, settings)
        area_x, area_y = _interval_points(x, y, settings.area_start, settings.area_end)
        baseline_y = np.interp(
            area_x,
            [settings.area_start, settings.area_end],
            [area_y[0], area_y[-1]],
        )
        upper = _scaled_points(area_x, area_y, settings, plot)
        lower = _scaled_points(area_x[::-1], baseline_y[::-1], settings, plot)
        polygon = " ".join(f"{px:.2f},{py:.2f}" for px, py in upper + lower)
        area_markup.append(
            f'<polygon points="{polygon}" fill="{trace_color}" fill-opacity="0.20" stroke="none"/>'
        )
        for boundary in (settings.area_start, settings.area_end):
            px = left + (boundary - settings.x_min) / (settings.x_max - settings.x_min) * plot_width
            area_markup.append(
                f'<line x1="{px:.2f}" y1="{top:.2f}" x2="{px:.2f}" y2="{bottom:.2f}" '
                f'stroke="{trace_color}" stroke-width="1.5" stroke-dasharray="6 5" opacity="0.65"/>'
            )
        metadata += (
            f" peak_area_bounds={result.start:.6g},{result.end:.6g}"
            f" raw_area={result.raw_area:.8g}"
            f" linear_baseline_corrected_area={result.baseline_corrected_area:.8g}"
            f" displayed_area={result.displayed_area:.8g}"
        )
    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<!-- {metadata} -->',
        '<rect width="100%" height="100%" fill="white"/>',
        *area_markup,
        f'<polyline points="{polyline}" fill="none" stroke="{trace_color}" stroke-width="{settings.trace_width}" stroke-linecap="round" stroke-linejoin="round"/>',
        f'<line x1="{left:.2f}" y1="{bottom:.2f}" x2="{right:.2f}" y2="{bottom:.2f}" stroke="black" stroke-width="{settings.axis_width}"/>',
        f'<line x1="{left:.2f}" y1="{top:.2f}" x2="{left:.2f}" y2="{bottom:.2f}" stroke="black" stroke-width="{settings.axis_width}"/>',
    ]

    x_major = _ticks(settings.x_min, settings.x_max, settings.x_major)
    y_major = _ticks(settings.y_min, settings.y_max, settings.y_major)
    x_minor = _minor_ticks(settings.x_min, settings.x_max, settings.x_major, settings.x_minor)
    y_minor = _minor_ticks(settings.y_min, settings.y_max, settings.y_major, settings.y_minor)
    major_length = max(11.0, settings.axis_width * 3.0)
    minor_length = major_length * 0.58
    tick_width = max(2.0, settings.axis_width * 0.78)

    for tick in x_minor:
        px = left + (tick - settings.x_min) / (settings.x_max - settings.x_min) * plot_width
        svg.append(f'<line x1="{px:.2f}" y1="{bottom:.2f}" x2="{px:.2f}" y2="{bottom + minor_length:.2f}" stroke="black" stroke-width="{tick_width}"/>')
    for tick in y_minor:
        py = bottom - (tick - settings.y_min) / (settings.y_max - settings.y_min) * plot_height
        svg.append(f'<line x1="{left:.2f}" y1="{py:.2f}" x2="{left - minor_length:.2f}" y2="{py:.2f}" stroke="black" stroke-width="{tick_width}"/>')
    for tick in x_major:
        px = left + (tick - settings.x_min) / (settings.x_max - settings.x_min) * plot_width
        svg.append(f'<line x1="{px:.2f}" y1="{bottom:.2f}" x2="{px:.2f}" y2="{bottom + major_length:.2f}" stroke="black" stroke-width="{settings.axis_width}"/>')
        if settings.show_tick_labels:
            svg.append(f'<text x="{px:.2f}" y="{bottom + major_length + settings.tick_font_size * 1.18:.2f}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="{settings.tick_font_size}">{_format_tick(tick)}</text>')
    for tick in y_major:
        py = bottom - (tick - settings.y_min) / (settings.y_max - settings.y_min) * plot_height
        svg.append(f'<line x1="{left:.2f}" y1="{py:.2f}" x2="{left - major_length:.2f}" y2="{py:.2f}" stroke="black" stroke-width="{settings.axis_width}"/>')
        if settings.show_tick_labels:
            svg.append(f'<text x="{left - major_length - 8:.2f}" y="{py + settings.tick_font_size * 0.34:.2f}" text-anchor="end" font-family="Arial, Helvetica, sans-serif" font-size="{settings.tick_font_size}">{_format_tick(tick)}</text>')

    svg.append(f'<text x="{left + plot_width / 2:.2f}" y="{height - settings.label_font_size * 0.25:.2f}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="{settings.label_font_size}">{html.escape(settings.x_label)}</text>')
    svg.append(f'<text transform="translate({settings.label_font_size * 0.72:.2f} {top + plot_height / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="{settings.label_font_size}">{html.escape(settings.y_label)}</text>')

    if settings.show_peak_label:
        peak_idx = int(np.nanargmax(y))
        peak_x = float(x[peak_idx])
        peak_y = float(y[peak_idx])
        px, py = _scaled_points(np.array([peak_x]), np.array([peak_y]), settings, plot)[0]
        label = f"{peak_x:.2f} ml"
        svg.append(f'<text x="{px:.2f}" y="{max(top + settings.tick_font_size, py - 12):.2f}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="{settings.tick_font_size * 0.72:.1f}">{html.escape(label)}</text>')

    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.strip().lstrip("#")
    if len(color) != 6:
        raise ValueError("Colors must use six-digit hex notation.")
    try:
        return tuple(int(color[idx : idx + 2], 16) for idx in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError("Invalid hex color.") from exc


def sample_image_color(path: str | Path, x: int, y: int) -> str:
    image = Image.open(path).convert("RGB")
    if not (0 <= x < image.width and 0 <= y < image.height):
        raise ValueError("The selected point is outside the image.")
    red, green, blue = image.getpixel((x, y))
    return f"#{red:02X}{green:02X}{blue:02X}"


def _longest_true_run(values: np.ndarray) -> tuple[int, int, int]:
    padded = np.concatenate(([False], values.astype(bool), [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    if len(changes) < 2:
        return 0, 0, 0
    starts = changes[::2]
    ends = changes[1::2]
    lengths = ends - starts
    idx = int(np.argmax(lengths))
    return int(lengths[idx]), int(starts[idx]), int(ends[idx] - 1)


def detect_plot_rectangle(path: str | Path, darkness: int = 70) -> tuple[int, int, int, int]:
    image = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    dark = image.mean(axis=2) < darkness
    horizontal = [_longest_true_run(row) for row in dark]
    bottom, (h_length, h_start, h_end) = max(enumerate(horizontal), key=lambda item: item[1][0])
    if h_length < image.shape[1] * 0.25:
        raise ValueError("Could not reliably detect long x/y axes; calibrate them manually.")

    # The left edge of the longest horizontal run is the expected y-axis.
    # Search locally for the strongest intersecting vertical run so a window
    # border at the outer image edge cannot be mistaken for the plot axis.
    search_width = max(30, int(h_length * 0.15))
    local_columns = range(
        max(0, h_start - 3),
        min(dark.shape[1], h_start + search_width),
    )
    left, (v_length, v_start, v_end) = max(
        ((column, _longest_true_run(dark[:, column])) for column in local_columns),
        key=lambda item: item[1][0],
    )
    if v_length < image.shape[0] * 0.25:
        raise ValueError("Could not reliably detect the y-axis at the x-axis intersection.")
    right = h_end
    top = v_start
    if not (left < right and top < bottom):
        raise ValueError("Detected axes do not form a valid plot rectangle.")
    return int(left), int(top), int(right), int(bottom)


def digitize_image(
    path: str | Path,
    plot_rectangle: tuple[int, int, int, int],
    axis_limits: tuple[float, float, float, float],
    trace_color: str,
    tolerance: float = 45.0,
) -> TraceData:
    left, top, right, bottom = plot_rectangle
    x_min, x_max, y_min, y_max = axis_limits
    if not (left < right and top < bottom):
        raise ValueError("Plot calibration requires top-left and bottom-right bounds.")
    if not (x_min < x_max and y_min < y_max):
        raise ValueError("Axis minimum values must be smaller than maximum values.")

    image = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    if left < 0 or top < 0 or right >= image.shape[1] or bottom >= image.shape[0]:
        raise ValueError("The calibrated plot rectangle extends outside the image.")
    crop = image[top : bottom + 1, left : right + 1]
    target = np.asarray(hex_to_rgb(trace_color), dtype=np.float32)
    distance = np.linalg.norm(crop - target, axis=2)
    mask = distance <= tolerance
    if float(mask.mean()) > 0.35:
        raise ValueError("The color tolerance selects too much of the image; reduce it.")

    pixel_y = np.full(mask.shape[1], np.nan, dtype=float)
    for column in range(mask.shape[1]):
        hits = np.flatnonzero(mask[:, column])
        if len(hits):
            pixel_y[column] = float(np.median(hits))
    valid = np.flatnonzero(np.isfinite(pixel_y))
    if len(valid) < max(10, int(mask.shape[1] * 0.05)):
        raise ValueError("Too little curve was detected; sample the trace color again or increase tolerance.")

    first, last = int(valid[0]), int(valid[-1])
    columns = np.arange(first, last + 1, dtype=float)
    interpolated_y = np.interp(columns, valid, pixel_y[valid])
    x = x_min + columns / max(1, mask.shape[1] - 1) * (x_max - x_min)
    y = y_max - interpolated_y / max(1, mask.shape[0] - 1) * (y_max - y_min)
    return TraceData(
        x=x,
        y=y,
        x_name="Digitized x",
        y_name="Digitized y",
        source_kind="digitized-image",
        approximate=True,
        metadata={
            "source_name": Path(path).name,
            "point_count": len(x),
            "plot_rectangle": plot_rectangle,
            "axis_limits": axis_limits,
            "trace_color": trace_color,
            "tolerance": tolerance,
        },
    )


def with_normalized_axis(settings: PlotSettings) -> PlotSettings:
    if not settings.normalize:
        return settings
    label = (
        "Relative A280"
        if settings.normalization_mode == "peak"
        else "Normalized A280"
    )
    return replace(
        settings,
        y_min=0.0,
        y_max=1.05,
        y_major=0.2,
        y_minor=0.05,
        y_label=label,
    )
