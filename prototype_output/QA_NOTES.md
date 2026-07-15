# BenchArc SEC prototype QA

- Backend: Python only
- Source format: UTF-16LE, tab-delimited UNICORN multi-channel export
- Selected channel: UV (`ml`, `mAU`)
- Raw UV points: 28,400
- Displayed points: 20,576
- Display range: 5-21 ml, 0-180 mAU
- Main peak: 17.862581 ml, 170.561371 mAU
- Smoothing: none
- Baseline subtraction: none
- Normalization: none
- Trace color: `#2F6FAF`
- Output: editable SVG and 600-dpi PNG preview

The default crop begins at the UNICORN `Elution` event near 5.00 ml and ends
before the terminal program transition after 21 ml. BenchArc SEC will expose
both limits to the user instead of applying this crop silently.
