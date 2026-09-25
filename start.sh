#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR" || exit 1

HOST="${DESK_BUDDY_HOST:-127.0.0.1}"
PORT="${DESK_BUDDY_PORT:-8765}"
OPEN_BROWSER=1

if [ "${1:-}" = "--no-open" ]; then
  OPEN_BROWSER=0
fi

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Python is missing. Run: pkg install python"
  exit 1
fi

URL="http://${HOST}:${PORT}"

"$PYTHON_BIN" server.py --host "$HOST" --port "$PORT" &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1
  fi
}

trap cleanup INT TERM EXIT

sleep 1

if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
  echo "Desk Buddy failed to start. Port ${PORT} may already be in use."
  wait "$SERVER_PID"
  exit $?
fi

if [ "$OPEN_BROWSER" -eq 1 ]; then
  if command -v termux-open-url >/dev/null 2>&1; then
    termux-open-url "$URL" >/dev/null 2>&1 || true
  else
    echo "Open this URL in your browser: $URL"
  fi
fi

echo "Desk Buddy is running at $URL"
echo "Press Ctrl+C in Termux to stop it."

wait "$SERVER_PID"
