#!/usr/bin/env python3
"""Redraw AKTA/UNICORN chromatograms as lightweight publication-style SVG figures."""

from __future__ import annotations

import argparse
import csv
import html
import math
from pathlib import Path
from typing import Iterable

try:
    import numpy as np
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: numpy. Install numpy or run with a scientific Python environment.") from exc


def read_delimited(path: Path) -> tuple[list[str], list[list[str]]]:
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    sample = raw.decode(encoding, errors="replace").splitlines()
    header_line = 0
    for i, line in enumerate(sample[:80]):
        if not line.strip():
            continue
        delimiters = [",", "\t", ";"]
        if max(line.count(d) for d in delimiters) >= 1:
            header_line = i
            break

    text = "\n".join(sample[header_line:])
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
    rows = list(csv.reader(text.splitlines(), dialect))
    if not rows:
        raise SystemExit("Input file is empty.")

    # UNICORN exports use three header rows: chromatogram, channel, and units.
    # Flatten paired channel columns into unique names such as "UV ml" and
    # "UV mAU" so users can plot the raw export without cleaning it first.
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
        return headers, rows[3:]
    return rows[0], rows[1:]


def parse_number(value: str) -> float | None:
    value = value.strip().replace(",", ".")
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def numeric_column_indices(headers: list[str], rows: list[list[str]]) -> list[int]:
    indices: list[int] = []
    for idx in range(len(headers)):
        values = [parse_number(row[idx]) for row in rows if idx < len(row)]
        good = sum(v is not None for v in values)
        if good >= max(5, int(len(rows) * 0.2)):
            indices.append(idx)
    return indices


def score_column(name: str, keywords: Iterable[str]) -> int:
    lower = name.lower()
    return sum(1 for keyword in keywords if keyword in lower)


def find_column(headers: list[str], requested: str | None, candidates: list[int], keywords: list[str]) -> int:
    if requested:
        requested_lower = requested.lower()
        for idx, name in enumerate(headers):
            if name == requested or name.lower() == requested_lower or requested_lower in name.lower():
                return idx
        raise SystemExit(f"Column '{requested}' not found. Available columns: {', '.join(headers)}")
    return max(candidates, key=lambda idx: (score_column(headers[idx], keywords), -candidates.index(idx)))


def smooth(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    if window % 2 == 0:
        window += 1
    if window >= len(values):
        return values
    kernel = np.ones(window) / window
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def ticks(start: float, end: float, interval: float | None, count: int = 6) -> list[float]:
    if interval and interval > 0:
        first = math.ceil(start / interval) * interval
        values = []
        value = first
        while value <= end + interval * 0.001:
            values.append(round(value, 10))
            value += interval
        return values
    if start == end:
        return [start]
    raw = (end - start) / max(1, count - 1)
    power = 10 ** math.floor(math.log10(abs(raw)))
    step = min([1, 2, 5, 10], key=lambda m: abs(raw - m * power)) * power
    first = math.ceil(start / step) * step
    values = []
    value = first
    while value <= end + step * 0.001:
        values.append(round(value, 10))
        value += step
    return values


def minor_ticks(start: float, end: float, major_values: list[float], explicit_interval: float | None, subdivisions: int) -> list[float]:
    if explicit_interval and explicit_interval > 0:
        values = ticks(start, end, explicit_interval)
    elif len(major_values) >= 2 and subdivisions > 1:
        major_step = major_values[1] - major_values[0]
        minor_step = major_step / subdivisions
        values = ticks(start, end, minor_step)
    else:
        return []

    major_set = {round(v, 8) for v in major_values}
    return [v for v in values if round(v, 8) not in major_set and start <= v <= end]


def fmt_tick(value: float) -> str:
    if abs(value - round(value)) < 1e-8:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def scale_points(x: np.ndarray, y: np.ndarray, xlim: tuple[float, float], ylim: tuple[float, float], plot: tuple[int, int, int, int]) -> list[tuple[float, float]]:
    left, top, width, height = plot
    xmin, xmax = xlim
    ymin, ymax = ylim
    px = left + (x - xmin) / (xmax - xmin) * width
    py = top + height - (y - ymin) / (ymax - ymin) * height
    return list(zip(px, py))


def render_svg(args: argparse.Namespace, x: np.ndarray, y: np.ndarray, xlim: tuple[float, float], ylim: tuple[float, float], peak: tuple[float, float] | None) -> str:
    width, height = int(args.width), int(args.height)
    plot = (88, 32, width - 120, height - 92)
    left, top, plot_w, plot_h = plot
    bottom = top + plot_h
    right = left + plot_w
    points = scale_points(x, y, xlim, ylim, plot)
    polyline = " ".join(f"{px:.2f},{py:.2f}" for px, py in points)

    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<polyline points="{polyline}" fill="none" stroke="{html.escape(args.line_color)}" stroke-width="{args.line_width}" stroke-linecap="round" stroke-linejoin="round"/>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="black" stroke-width="1.4"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="black" stroke-width="1.4"/>',
    ]

    x_major = ticks(xlim[0], xlim[1], args.major_x)
    y_major = ticks(ylim[0], ylim[1], args.major_y)
    x_minor = minor_ticks(xlim[0], xlim[1], x_major, args.minor_x, args.minor_subdivisions)
    y_minor = minor_ticks(ylim[0], ylim[1], y_major, args.minor_y, args.minor_subdivisions)

    for tick in x_minor:
        tx = left + (tick - xlim[0]) / (xlim[1] - xlim[0]) * plot_w
        svg.append(f'<line x1="{tx:.2f}" y1="{bottom}" x2="{tx:.2f}" y2="{bottom + 5}" stroke="black" stroke-width="0.9"/>')
    for tick in y_minor:
        ty = bottom - (tick - ylim[0]) / (ylim[1] - ylim[0]) * plot_h
        svg.append(f'<line x1="{left}" y1="{ty:.2f}" x2="{left - 5}" y2="{ty:.2f}" stroke="black" stroke-width="0.9"/>')

    for tick in x_major:
        tx = left + (tick - xlim[0]) / (xlim[1] - xlim[0]) * plot_w
        svg.append(f'<line x1="{tx:.2f}" y1="{bottom}" x2="{tx:.2f}" y2="{bottom + 10}" stroke="black" stroke-width="1.4"/>')
        if not args.no_tick_labels:
            svg.append(f'<text x="{tx:.2f}" y="{bottom + 30}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="{args.font_size}">{fmt_tick(tick)}</text>')
    for tick in y_major:
        ty = bottom - (tick - ylim[0]) / (ylim[1] - ylim[0]) * plot_h
        svg.append(f'<line x1="{left}" y1="{ty:.2f}" x2="{left - 10}" y2="{ty:.2f}" stroke="black" stroke-width="1.4"/>')
        if not args.no_tick_labels:
            svg.append(f'<text x="{left - 16}" y="{ty + args.font_size * 0.35:.2f}" text-anchor="end" font-family="Arial, Helvetica, sans-serif" font-size="{args.font_size}">{fmt_tick(tick)}</text>')

    svg.append(f'<text x="{left + plot_w / 2:.2f}" y="{height - 16}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="{args.label_size}">{html.escape(args.xlabel)}</text>')
    svg.append(f'<text transform="translate(24 {top + plot_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="{args.label_size}">{html.escape(args.ylabel)}</text>')
    if args.title:
        svg.append(f'<text x="{left}" y="18" font-family="Arial, Helvetica, sans-serif" font-size="{args.font_size}" font-weight="bold">{html.escape(args.title)}</text>')
    if peak:
        peak_x, peak_y = peak
        px, py = scale_points(np.array([peak_x]), np.array([peak_y]), xlim, ylim, plot)[0]
        label = args.peak_label or f"{peak_x:.2f} ml"
        svg.append(f'<text x="{px:.2f}" y="{py - 10:.2f}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="{args.font_size * 0.9:.1f}">{html.escape(label)}</text>')

    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def render_png(args: argparse.Namespace, x: np.ndarray, y: np.ndarray, xlim: tuple[float, float], ylim: tuple[float, float], peak: tuple[float, float] | None, path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ModuleNotFoundError as exc:
        raise SystemExit("PNG export requires Pillow. SVG output was still generated.") from exc

    scale = args.png_scale
    width, height = int(args.width * scale), int(args.height * scale)
    plot = tuple(int(v * scale) for v in (88, 32, args.width - 120, args.height - 92))
    left, top, plot_w, plot_h = plot
    bottom = top + plot_h
    right = left + plot_w
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    points = [(int(px * scale), int(py * scale)) for px, py in scale_points(x, y, xlim, ylim, (88, 32, args.width - 120, args.height - 92))]
    draw.line(points, fill=args.line_color, width=max(1, int(args.line_width * scale)), joint="curve")
    draw.line([(left, bottom), (right, bottom)], fill="black", width=max(1, int(1.4 * scale)))
    draw.line([(left, top), (left, bottom)], fill="black", width=max(1, int(1.4 * scale)))
    font_path = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    if font_path.exists():
        font = ImageFont.truetype(str(font_path), max(1, int(args.font_size * scale)))
        label_font = ImageFont.truetype(str(font_path), max(1, int(args.label_size * scale)))
    else:
        font = ImageFont.load_default()
        label_font = font
    x_major = ticks(xlim[0], xlim[1], args.major_x)
    y_major = ticks(ylim[0], ylim[1], args.major_y)
    x_minor = minor_ticks(xlim[0], xlim[1], x_major, args.minor_x, args.minor_subdivisions)
    y_minor = minor_ticks(ylim[0], ylim[1], y_major, args.minor_y, args.minor_subdivisions)
    for tick in x_minor:
        tx = left + (tick - xlim[0]) / (xlim[1] - xlim[0]) * plot_w
        draw.line([(tx, bottom), (tx, bottom + 5 * scale)], fill="black", width=max(1, int(0.9 * scale)))
    for tick in y_minor:
        ty = bottom - (tick - ylim[0]) / (ylim[1] - ylim[0]) * plot_h
        draw.line([(left, ty), (left - 5 * scale, ty)], fill="black", width=max(1, int(0.9 * scale)))
    for tick in x_major:
        tx = left + (tick - xlim[0]) / (xlim[1] - xlim[0]) * plot_w
        draw.line([(tx, bottom), (tx, bottom + 10 * scale)], fill="black", width=max(1, int(1.4 * scale)))
        if not args.no_tick_labels:
            draw.text((tx, bottom + 12 * scale), fmt_tick(tick), fill="black", anchor="ma", font=font)
    for tick in y_major:
        ty = bottom - (tick - ylim[0]) / (ylim[1] - ylim[0]) * plot_h
        draw.line([(left, ty), (left - 10 * scale, ty)], fill="black", width=max(1, int(1.4 * scale)))
        if not args.no_tick_labels:
            draw.text((left - 12 * scale, ty), fmt_tick(tick), fill="black", anchor="rm", font=font)
    draw.text((left + plot_w / 2, height - 15 * scale), args.xlabel, fill="black", anchor="ms", font=label_font)

    ylabel_box = draw.textbbox((0, 0), args.ylabel, font=label_font)
    ylabel_size = (ylabel_box[2] - ylabel_box[0] + 8 * scale, ylabel_box[3] - ylabel_box[1] + 8 * scale)
    ylabel_image = Image.new("RGBA", ylabel_size, (255, 255, 255, 0))
    ylabel_draw = ImageDraw.Draw(ylabel_image)
    ylabel_draw.text((4 * scale, 4 * scale), args.ylabel, fill="black", font=label_font)
    ylabel_image = ylabel_image.rotate(90, expand=True)
    image.paste(ylabel_image, (int(8 * scale), int(top + (plot_h - ylabel_image.height) / 2)), ylabel_image)

    if args.title:
        draw.text((left, 5 * scale), args.title, fill="black", font=font)
    if peak:
        peak_x, peak_y = peak
        px, py = scale_points(np.array([peak_x]), np.array([peak_y]), xlim, ylim, (88, 32, args.width - 120, args.height - 92))[0]
        label = args.peak_label or f"{peak_x:.2f} ml"
        draw.text((px * scale, (py - 8) * scale), label, fill="black", anchor="ms", font=font)
    image.save(path, dpi=(600, 600))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot AKTA/UNICORN chromatogram exports.")
    parser.add_argument("input", type=Path, help="CSV, TSV, or TXT file exported from AKTA/UNICORN.")
    parser.add_argument("--output", type=Path, default=Path("akta_chromatogram.svg"), help="Output SVG path.")
    parser.add_argument("--png", action="store_true", help="Also save a high-resolution PNG next to the SVG.")
    parser.add_argument("--png-scale", type=int, default=4, help="PNG scale factor relative to SVG canvas.")
    parser.add_argument("--x-col", default=None, help="Column containing elution volume, time, or CV.")
    parser.add_argument("--y-col", default=None, help="Column containing UV/A280/mAU values.")
    parser.add_argument("--xlim", nargs=2, type=float, metavar=("MIN", "MAX"), help="X-axis limits.")
    parser.add_argument("--ylim", nargs=2, type=float, metavar=("MIN", "MAX"), help="Y-axis limits.")
    parser.add_argument("--xlabel", default="Elution volume (ml)", help="X-axis label.")
    parser.add_argument("--ylabel", default="UV 280 (mAU)", help="Y-axis label.")
    parser.add_argument("--title", default=None, help="Optional panel title. Usually omit for manuscripts.")
    parser.add_argument("--line-color", default="#7f7f7f", help="Trace color.")
    parser.add_argument("--line-width", type=float, default=3.0, help="Trace line width in SVG units.")
    parser.add_argument("--width", type=float, default=520, help="SVG width in pixels.")
    parser.add_argument("--height", type=float, default=360, help="SVG height in pixels.")
    parser.add_argument("--font-size", type=float, default=18.0, help="Tick and annotation font size.")
    parser.add_argument("--label-size", type=float, default=24.0, help="Axis label font size.")
    parser.add_argument("--smooth-window", type=int, default=1, help="Moving-average smoothing window in points.")
    parser.add_argument("--baseline-subtract", action="store_true", help="Subtract the minimum y value after cropping.")
    parser.add_argument("--normalize", action="store_true", help="Scale y to 0-1 after optional baseline subtraction.")
    parser.add_argument("--annotate-peak", action="store_true", help="Label the maximum visible peak with its x value.")
    parser.add_argument("--peak-label", default=None, help="Custom peak label. Default: peak x value.")
    parser.add_argument("--major-x", type=float, default=None, help="Major x tick interval.")
    parser.add_argument("--major-y", type=float, default=None, help="Major y tick interval.")
    parser.add_argument("--minor-x", type=float, default=None, help="Minor x tick interval. Default: divide major tick intervals.")
    parser.add_argument("--minor-y", type=float, default=None, help="Minor y tick interval. Default: divide major tick intervals.")
    parser.add_argument("--minor-subdivisions", type=int, default=4, help="Number of minor intervals per major interval when --minor-x/--minor-y are omitted.")
    parser.add_argument("--no-tick-labels", action="store_true", help="Hide numeric tick labels while keeping major and minor tick marks.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    headers, rows = read_delimited(args.input)
    numeric = numeric_column_indices(headers, rows)
    if len(numeric) < 2:
        raise SystemExit("Could not find at least two numeric columns. Pass cleaner CSV/TSV data.")

    x_idx = find_column(headers, args.x_col, numeric, ["elution", "volume", "ml", "time", "min", "cv"])
    y_candidates = [idx for idx in numeric if idx != x_idx]
    y_idx = find_column(headers, args.y_col, y_candidates, ["uv", "280", "a280", "mau", "abs", "absorbance"])

    parsed = []
    for row in rows:
        if max(x_idx, y_idx) >= len(row):
            continue
        x_val = parse_number(row[x_idx])
        y_val = parse_number(row[y_idx])
        if x_val is not None and y_val is not None:
            parsed.append((x_val, y_val))
    if not parsed:
        raise SystemExit("No numeric x/y rows found.")

    parsed.sort()
    data = np.array(parsed, dtype=float)
    x = data[:, 0]
    y = data[:, 1]
    if args.xlim:
        mask = (x >= args.xlim[0]) & (x <= args.xlim[1])
        x = x[mask]
        y = y[mask]
    if len(x) < 2:
        raise SystemExit("No data remain after cleaning/cropping.")

    y = smooth(y, args.smooth_window)
    if args.baseline_subtract:
        y = y - np.nanmin(y)
    if args.normalize:
        ymax = np.nanmax(y)
        if ymax:
            y = y / ymax
        args.ylabel = "Normalized A280"

    xlim = tuple(args.xlim) if args.xlim else (float(np.nanmin(x)), float(np.nanmax(x)))
    ylim = tuple(args.ylim) if args.ylim else (min(0.0, float(np.nanmin(y))), float(np.nanmax(y) * 1.08))
    peak = None
    if args.annotate_peak:
        peak_idx = int(np.nanargmax(y))
        peak = (float(x[peak_idx]), float(y[peak_idx]))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(args, x, y, xlim, ylim, peak))
    if args.png:
        render_png(args, x, y, xlim, ylim, peak, args.output.with_suffix(".png"))
    print(f"Plotted {len(x)} points from columns '{headers[x_idx]}' and '{headers[y_idx]}' -> {args.output}")


if __name__ == "__main__":
    main()
