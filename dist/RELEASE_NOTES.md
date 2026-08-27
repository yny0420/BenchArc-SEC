# BenchArc SEC 0.2.4

## Fixed in 0.2.4

- Fixed long SEC traces disappearing when exported SVG files were opened in
  Adobe Illustrator. Large traces are now written as continuous, overlapping
  polyline segments while retaining every original data point.

## New in 0.2.3

- Added an in-app **Help → User Guide** quick-start guide.
- Added an **About BenchArc SEC** dialog with copyright information.
- Added a detailed Chinese user guide covering installation, raw-data import,
  publication styling, normalization, peak-area analysis, batch processing,
  export, image-input limitations, and troubleshooting.
- Added explicit copyright and local-data ownership information.

## Included

- Native macOS desktop application packaged as a DMG.
- New white macOS application icon built from the BenchArc chromatography peak
  and arc motif, embedded as a multi-resolution ICNS for Finder and Dock use.
- Fixed the icon's outer canvas: the area outside the white squircle is now
  genuinely transparent, so Launchpad no longer shows a white square around
  the rounded application icon.
- Multi-file queue for raw SEC data and chromatogram images.
- Per-item editing plus **Apply settings to all** and batch SVG/600-dpi PNG
  export. Images that have not been calibrated and extracted are skipped with
  an explicit count.
- Y-axis scaling to the visible maximum or to a selected local peak near a
  user-specified elution volume. The selected peak is displayed as 1 without
  overwriting the original signal.
- Peak-area integration over editable start/end bounds, with raw integral,
  linear-baseline-corrected area, displayed-scale integral, optional figure
  shading, SVG metadata, and an Excel-ready batch CSV report.
- Raw data input: UTF-16 UNICORN TXT plus ordinary TXT, CSV, and TSV.
- Image input: PNG, JPEG, and TIFF with plot calibration, trace-color sampling,
  tolerance control, and approximate digitization.
- Default bold-gray publication preset based on the supplied reference:
  white background, gray heavy trace, black left/bottom axes, dense outward
  major/minor ticks, no grid, no fill, no top/right spines.
- Custom axis ranges, tick spacing, labels, trace color, line width, axis width,
  font sizes, and optional peak annotation.
- Smoothing, baseline subtraction, normalization, and area shading are disabled
  by default.
- Editable SVG and 3600 x 2400, 600-dpi PNG export.

## Verification

- Core tests: 5 passed.
- Real UNICORN sample: 28,400 UV points loaded.
- Two-file batch smoke test exported two SVG files, two 600-dpi PNG files, and
  one peak-area CSV. With 16–20 ml bounds, the sample produced raw area
  `493.4061 mAU·ml`, linear-baseline-corrected area `260.6355 mAU·ml`, and a
  normalization reference at `17.862581 ml` (`170.561371 mAU`).
- Reference-image digitization: plot rectangle `(281, 90, 1656, 905)`;
  extracted peak approximately 13.0 ml and 26.56 mAU.
- Frozen application launched successfully from the mounted DMG.
- Application bundle passed deep strict code-signature verification.
- DMG checksum verified by `hdiutil`.
- SHA-256: `f5eb0ea2eae0db51008a233c3b89510747f37055a0ed006b1d279ca53e4bad61`

## Distribution note

This is an Apple Silicon development build with an ad-hoc signature. It is not
Apple-notarized. On another Mac, Gatekeeper may require Control-clicking the app
and choosing **Open**. Public distribution without this warning requires an
Apple Developer ID certificate and notarization.

Image-derived curves are approximate and should be checked against the source
image. Raw TXT/CSV/TSV data remain the preferred source for publication figures.
