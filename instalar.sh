#!/usr/bin/env bash
set -euo pipefail
D="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)";V="$D/.venv";cd "$D"
command -v python3 >/dev/null||{ echo "Python 3.11+ requerido";exit 1; }
python3 - <<'PY'
import sys
if sys.version_info<(3,11):raise SystemExit('Python 3.11+ requerido')
PY
[[ -d "$V" ]]||python3 -m venv "$V";source "$V/bin/activate";python -m pip install --upgrade pip setuptools wheel;python -m pip install -e "$D[test]";python -m playwright install chromium;[[ -f "$D/.env" ]]||cp "$D/.env.example" "$D/.env";mkdir -p "$D/data/browser" "$D/data/diagnostics" "$D/data/cache";echo "Flight Watch Agent 0.7.2 instalado en $D"
