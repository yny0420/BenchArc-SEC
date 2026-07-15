#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_DIR="${BENCHARC_ENV_DIR:-/private/tmp/BenchArc-SEC-venv}"
PYTHON_BASE="${BENCHARC_PYTHON_BASE:-/Library/Frameworks/Python.framework/Versions/3.10/bin/python3}"

if [[ ! -x "$PYTHON_BASE" ]]; then
  echo "Missing official Python 3.10: $PYTHON_BASE" >&2
  exit 1
fi

"$PYTHON_BASE" -m venv "$ENV_DIR"
"$ENV_DIR/bin/python" -m pip install --upgrade pip
"$ENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements-dev.txt"

echo "BenchArc SEC development environment: $ENV_DIR"
