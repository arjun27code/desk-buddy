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

WAKE_LOCKED=0

cleanup() {
  if [ "$WAKE_LOCKED" -eq 1 ] && command -v termux-wake-unlock >/dev/null 2>&1; then
    termux-wake-unlock >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock >/dev/null 2>&1 || true
  WAKE_LOCKED=1
fi

"$PYTHON_BIN" "$SCRIPT_DIR/desk_buddy.py" "$@"
