#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="${BENCHARC_PYTHON:-/private/tmp/BenchArc-SEC-venv/bin/python}"
SOURCE="$APP_DIR/assets/BenchArc_SEC_icon_white_transparent.png"
OUTPUT="$APP_DIR/assets/BenchArc_SEC.icns"
WORK_DIR="$(mktemp -d /private/tmp/BenchArc-SEC-icon.XXXXXX)"
ICONSET="$WORK_DIR/BenchArc_SEC.iconset"
mkdir -p "$ICONSET"
trap 'rm -rf "$WORK_DIR"' EXIT

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing project environment: $PYTHON" >&2
  exit 1
fi

"$PYTHON" "$SCRIPT_DIR/prepare_macos_icon.py"

make_size() {
  local pixels="$1"
  local name="$2"
  sips -z "$pixels" "$pixels" "$SOURCE" --out "$ICONSET/$name" >/dev/null
}

make_size 16 icon_16x16.png
make_size 32 icon_16x16@2x.png
make_size 32 icon_32x32.png
make_size 64 icon_32x32@2x.png
make_size 128 icon_128x128.png
make_size 256 icon_128x128@2x.png
make_size 256 icon_256x256.png
make_size 512 icon_256x256@2x.png
make_size 512 icon_512x512.png
make_size 1024 icon_512x512@2x.png

iconutil -c icns "$ICONSET" -o "$OUTPUT"
echo "Built: $OUTPUT"
