#!/usr/bin/env python3
"""Headless integration smoke test for image digitization."""

from __future__ import annotations

import os
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
    window.load_image(source)
    window.show()
    app.processEvents()
    if not window.grab().save(str(output_dir / "image_calibration_window.png"), "PNG"):
        raise SystemExit("Could not save the image-calibration screenshot.")
    window.x_min.setValue(6)
    window.x_max.setValue(18)
    window.y_min.setValue(0)
    window.y_max.setValue(35)
    window.x_major.setValue(2)
    window.x_minor.setValue(0.5)
    window.y_major.setValue(5)
    window.y_minor.setValue(1)
    window.sampled_trace_color = "#858585"
    window.extract_image_curve()
    app.processEvents()

    if window.trace is None or not window.trace.approximate:
        raise SystemExit("Image digitization did not produce an approximate trace.")
    (output_dir / "image_mode_preview.svg").write_text(window.current_svg, encoding="utf-8")
    if not window.grab().save(str(output_dir / "image_mode_window.png"), "PNG"):
        raise SystemExit("Could not save the image-mode application screenshot.")
    print(f"digitized_points={len(window.trace.x)}")
    print(f"plot_rectangle={window.trace.metadata['plot_rectangle']}")


if __name__ == "__main__":
    main()
