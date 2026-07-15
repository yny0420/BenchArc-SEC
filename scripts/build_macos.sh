#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$APP_DIR/../.." && pwd)"
APP_VERSION="0.2.2"
DEFAULT_PYTHON="/private/tmp/BenchArc-SEC-venv/bin/python"
PYTHON="${BENCHARC_PYTHON:-$DEFAULT_PYTHON}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing project environment: $PYTHON" >&2
  exit 1
fi

cd "$APP_DIR"
"$PYTHON" -m pip install -e .
"$SCRIPT_DIR/build_macos_icon.sh"

BUILD_ROOT="$(mktemp -d /private/tmp/BenchArc-SEC-build.XXXXXX)"
trap 'rm -rf "$BUILD_ROOT"' EXIT
mkdir -p "$BUILD_ROOT/spec" "$BUILD_ROOT/dmg"
export PYINSTALLER_CONFIG_DIR="$BUILD_ROOT/pyinstaller-cache"

"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "BenchArc SEC" \
  --osx-bundle-identifier "org.bencharc.sec" \
  --icon "$APP_DIR/assets/BenchArc_SEC.icns" \
  --distpath "$BUILD_ROOT/dist" \
  --workpath "$BUILD_ROOT/work" \
  --specpath "$BUILD_ROOT/spec" \
  --paths src \
  launch_bencharc_sec.py

APP_BUNDLE="$BUILD_ROOT/dist/BenchArc SEC.app"
/usr/libexec/PlistBuddy \
  -c "Set :CFBundleShortVersionString $APP_VERSION" \
  -c "Add :CFBundleVersion string $APP_VERSION" \
  "$APP_BUNDLE/Contents/Info.plist"
xattr -cr "$APP_BUNDLE"
codesign --force --deep --sign - "$APP_BUNDLE"
codesign --verify --deep --strict "$APP_BUNDLE"

STAGING_DIR="$BUILD_ROOT/dmg"
cp -R "$APP_BUNDLE" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"
DMG_PATH="$BUILD_ROOT/BenchArc_SEC_${APP_VERSION}.dmg"
hdiutil create \
  -volname "BenchArc SEC" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

mkdir -p "$APP_DIR/dist"
cp "$DMG_PATH" "$APP_DIR/dist/BenchArc_SEC_${APP_VERSION}.dmg"

echo "Built: $APP_DIR/dist/BenchArc_SEC_${APP_VERSION}.dmg"
