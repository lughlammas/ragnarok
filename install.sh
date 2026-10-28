#!/usr/bin/env bash
# Instalador Linux/macOS (usado para testar na box). Cria .venv, instala pacotes e baixa os modelos.
set -euo pipefail
cd "$(dirname "$0")"
PY="${RAGNAROK_PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.12 python3.11 python3.13 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)'; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "ERRO: precisa de Python 3.11, 3.12 ou 3.13."; exit 1; }
echo "Usando $($PY --version) ($PY)"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m ragnarok models
.venv/bin/python -m ragnarok doctor
echo
echo "Pronto. Use:  ./run.sh            (interface web)"
echo "              ./run.sh say \"texto\" --voice alex-pt --out saida.mp3"
