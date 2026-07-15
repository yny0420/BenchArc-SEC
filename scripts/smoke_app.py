#!/usr/bin/env python3
"""Headless integration smoke test for the BenchArc SEC window."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from bencharc_sec.app import BenchArcSECWindow


def main() -> None:
    source = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    window = BenchArcSECWindow()
    batch_inputs = output_dir / "batch_inputs"
    batch_inputs.mkdir(exist_ok=True)
    first = batch_inputs / "run_A.txt"
    second = batch_inputs / "run_B.txt"
    shutil.copyfile(source, first)
    shutil.copyfile(source, second)
    window.add_paths([first, second])
    window.source_list.setCurrentRow(1)
    app.processEvents()
    if window.source_path != second:
        raise SystemExit("Batch selection did not switch to the second chromatogram.")
    window.x_max.setValue(21)
    window.y_max.setValue(180)
    window.x_major.setValue(2)
    window.x_minor.setValue(0.5)
    window.y_major.setValue(20)
    window.y_minor.setValue(5)
    window.apply_reference_preset()
    window.normalization_peak_x.setValue(17.86)
    window.normalization_window.setValue(0.5)
    window.normalization_mode.setCurrentIndex(window.normalization_mode.findData("peak"))
    window.area_start.setValue(16.0)
    window.area_end.setValue(20.0)
    window.show_area.setChecked(True)
    window.apply_current_settings_to_all()
    window.update_preview()
    window.show()
    app.processEvents()

    if not window.current_svg:
        raise SystemExit("No SVG preview was generated.")
    window.save_svg(output_dir / "app_preview.svg")
    if not window.save_png(output_dir / "publication_600dpi.png"):
        raise SystemExit("Could not save the publication PNG.")
    if not window.grab().save(str(output_dir / "app_window.png"), "PNG"):
        raise SystemExit("Could not save the application screenshot.")
    window.controls_scroll.verticalScrollBar().setValue(
        window.controls_scroll.verticalScrollBar().maximum()
    )
    app.processEvents()
    if not window.grab().save(str(output_dir / "normalization_area_window.png"), "PNG"):
        raise SystemExit("Could not save the normalization/area screenshot.")
    exported, skipped, report = window.batch_export(output_dir / "batch_export")
    if exported != 2 or skipped != 0 or report is None:
        raise SystemExit("Batch export did not produce two figures and a peak-area report.")
    print(f"source_points={len(window.trace.x) if window.trace else 0}")
    print(f"svg_bytes={len(window.current_svg.encode('utf-8'))}")
    print(f"window_size={window.size().width()}x{window.size().height()}")
    print(f"batch_exported={exported}; area_report={report.name}")


if __name__ == "__main__":
    main()
