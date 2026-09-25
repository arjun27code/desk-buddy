#!/data/data/com.termux/files/usr/bin/bash
set -e

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

if [ -z "${PREFIX:-}" ]; then
  echo "This installer is meant to run inside Termux."
  exit 1
fi

if ! command -v python >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  echo "Installing Python..."
  pkg install python -y
fi

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  PYTHON_BIN="python3"
fi

echo "Checking Desk Buddy..."
"$PYTHON_BIN" -m py_compile "$PROJECT_DIR/desk_buddy.py"

LAUNCHER="$PREFIX/bin/desk-buddy"

cat > "$LAUNCHER" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$PROJECT_DIR"
exec bash "$PROJECT_DIR/start.sh" "\$@"
EOF

chmod +x "$LAUNCHER"

echo
echo "Desk Buddy installed."
echo "Direct Termux display. No browser and no localhost."
echo
echo "Start:"
echo "  desk-buddy"
echo
echo "Optional weather fallback city:"
echo "  desk-buddy --set-city \"Your City\""
echo
echo "Optional phone battery/location reactions need the Termux:API companion app"
echo "and this Termux package:"
echo "  pkg install termux-api"
