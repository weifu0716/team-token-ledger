#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${PYTHON_PATH:-python3}" -m ledger server "$@"
