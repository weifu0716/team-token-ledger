#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON_PATH:-python3}"
"$PYTHON" "$ROOT/scripts/install.py" --macos "$@"
printf '%s\n' '背景回報已註冊。請確認 launchctl print 與 employee-data/status.json，並在老闆看板回讀。'
