# BenchArc SEC

BenchArc SEC is a local macOS application for turning raw SEC chromatogram
exports or calibrated chromatogram images into publication-ready figures.

- [中文用户使用指南](USER_GUIDE.md)
- [Copyright information](COPYRIGHT.md)
- [Download the latest macOS DMG](https://github.com/yny0420/BenchArc-SEC/releases/latest)

## Installation

Download the latest DMG, open it, and drag **BenchArc SEC** to Applications.
The application is self-contained; users do not need to install Python or any
scientific packages. The current build targets Apple Silicon and is not
notarized. On first launch, macOS may require Control-clicking the application
and choosing **Open**.

## Version 0.2 scope

- Use the white BenchArc chromatography-arc icon in Finder, Applications, and
  the macOS Dock.
- Read UTF-16 UNICORN multi-channel TXT exports without manual cleanup.
- Read ordinary CSV, TSV, and TXT tables.
- Digitize PNG, JPEG, and TIFF chromatogram images after axis calibration and
  trace-color sampling. Image-derived curves are explicitly marked approximate.
- Preview edits immediately in a native PySide6 interface.
- Add multiple SEC data files or images to a batch, switch between them, apply
  the current settings to all items, and export every ready trace together.
- Scale the Y axis either to the visible maximum or to a user-selected peak
  near a specified elution volume. Scaling affects display values only and
  does not overwrite the imported measurements.
- Calculate peak area over user-defined bounds. The app reports the raw
  integral, the linear-baseline-corrected area, and the current displayed-scale
  integral; the selected area can be shaded in the figure.
- Customize axis limits, major/minor ticks, labels, trace color, line width,
  font size, peak labels, smoothing, baseline subtraction, and normalization.
- Use the default bold-gray publication preset: gray trace, heavy black left and
  bottom axes, dense outward ticks, white background, no grid, no fill.
- Export editable SVG and 600-dpi PNG. Batch export also creates an Excel-ready
  `BenchArc_SEC_peak_areas.csv` when area calculation is enabled.

Data transformations and peak-area shading are disabled by default. Applied
transformations, integration bounds, and area values are recorded in SVG
metadata. Image items must be calibrated and extracted individually before
they can participate in batch export; unextracted images are reported as
skipped.

## Development run

```bash
apps/sec/scripts/setup_dev_env.sh
/private/tmp/BenchArc-SEC-venv/bin/python -m pip install -e apps/sec
/private/tmp/BenchArc-SEC-venv/bin/python -m bencharc_sec
```

## Tests

```bash
/private/tmp/BenchArc-SEC-venv/bin/python -m pytest apps/sec/tests
```

## macOS build

```bash
apps/sec/scripts/build_macos.sh
```

The development DMG is unsigned. Public distribution without a Gatekeeper
warning requires an Apple Developer ID certificate and notarization.

The build environment is intentionally outside Desktop and Documents because
macOS protected-folder access can prevent Qt from enumerating development
plugins there. The installed `.app` is self-contained and does not use this
temporary environment at runtime.

## Copyright

Copyright © 2026 Yang Yu. All rights reserved. See [COPYRIGHT.md](COPYRIGHT.md).
