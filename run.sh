#!/usr/bin/env bash
cd "$(dirname "$0")"
export PYTHONUTF8=1
[ -x .venv/bin/python ] || { echo "Rode ./install.sh primeiro."; exit 1; }
if [ $# -eq 0 ]; then set -- web; fi
exec .venv/bin/python -m ragnarok "$@"
