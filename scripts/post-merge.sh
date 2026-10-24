#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_VERSION="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PYTHON_SITE="$ROOT_DIR/.pythonlibs/lib/python${PYTHON_VERSION}/site-packages"

# Keep both runtimes ready after a task merge. These commands use the project
# manifests/lockfile and can run unattended with stdin closed.
python -m pip install --upgrade --no-warn-script-location \
  --target "$PYTHON_SITE" \
  -r "$ROOT_DIR/requirements.txt"
npm --prefix "$ROOT_DIR/hackaton" ci --no-audit --no-fund
