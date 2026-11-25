#!/usr/bin/env bash
set -euo pipefail
D="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)";[[ -x "$D/.venv/bin/python" ]]||"$D/instalar.sh";cd "$D";exec "$D/.venv/bin/python" -m flight_watch.ui "$@"
