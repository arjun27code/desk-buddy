#!/data/data/com.termux/files/usr/bin/bash
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Python is missing. Run: pkg install python"
  exit 1
fi

if [ "${1:-}" = "--terminal" ]; then
  shift
  exec "$PYTHON_BIN" "$SCRIPT_DIR/desk_buddy.py" "$@"
fi

if [ "${1:-}" = "--vision-test" ]; then
  shift
  exec "$PYTHON_BIN" "$SCRIPT_DIR/vision_test.py" "$@"
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/gui_buddy.py" "$@"
