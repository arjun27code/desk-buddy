#!/data/data/com.termux/files/usr/bin/bash
set -e

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

if [ -z "${PREFIX:-}" ]; then
  echo "This installer is meant to run inside Termux."
  exit 1
fi

if ! command -v python >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  echo "Python is not installed."
  echo "Installing the Termux python package..."
  pkg install python -y
fi

chmod +x "$PROJECT_DIR/start.sh"

LAUNCHER="$PREFIX/bin/desk-buddy"

cat > "$LAUNCHER" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$PROJECT_DIR"
exec bash "$PROJECT_DIR/start.sh" "\$@"
EOF

chmod +x "$LAUNCHER"

echo
echo "Desk Buddy installed."
echo "Start it anytime with:"
echo
echo "  desk-buddy"
echo
echo "Optional battery integration:"
echo "  1. Install the Termux:API companion app from the same source as Termux."
echo "  2. Run: pkg install termux-api"
echo
echo "Weather works through your browser location permission."
