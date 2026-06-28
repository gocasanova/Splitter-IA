#!/bin/zsh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python"

cd "$PROJECT_DIR"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "No se encontro el entorno virtual en: $PYTHON_BIN"
  echo "Ejecuta: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  read "?Presiona Enter para cerrar..."
  exit 1
fi

"$PYTHON_BIN" "$PROJECT_DIR/main.py"
