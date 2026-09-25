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

echo "Checking Desk Buddy Python files..."
"$PYTHON_BIN" -m py_compile "$PROJECT_DIR/gui_buddy.py"
"$PYTHON_BIN" -m py_compile "$PROJECT_DIR/buddy_advanced.py"
"$PYTHON_BIN" -m py_compile "$PROJECT_DIR/gibber_voice.py"
"$PYTHON_BIN" -m py_compile "$PROJECT_DIR/game_hub.py"
"$PYTHON_BIN" -m py_compile "$PROJECT_DIR/doodle_show.py"
"$PYTHON_BIN" -m py_compile "$PROJECT_DIR/oled_asset_show.py"
"$PYTHON_BIN" -m py_compile "$PROJECT_DIR/desk_buddy.py"

echo "Installing Termux:GUI Python binding..."
"$PYTHON_BIN" -m pip install --upgrade termuxgui

if ! command -v termux-sensor >/dev/null 2>&1; then
  echo "Installing Termux:API command package for motion sensors and audio..."
  pkg install termux-api -y
fi

LAUNCHER="$PREFIX/bin/desk-buddy"

cat > "$LAUNCHER" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$PROJECT_DIR"
exec bash "$PROJECT_DIR/start.sh" "\$@"
EOF

chmod +x "$LAUNCHER"

echo
echo "Desk Buddy installed."
echo
echo "Native pixel mode:"
echo "  desk-buddy"
echo
echo "Old terminal fallback:"
echo "  desk-buddy --terminal"
echo
echo "Direct OLED playback diagnostic:"
echo "  desk-buddy --test-oled"
echo
echo "IMPORTANT:"
echo "Native graphics require the Termux:GUI Android plugin app."
echo "Shake + tilt + gibber audio require the Termux:API Android plugin app."
echo "Install both plugins from the SAME source as your Termux app."
echo "Games:"
echo "  Double-tap or long-press the face to open Game Hub."
echo "  Includes Tic-Tac-Toe vs Buddy, Pong vs Buddy, Snake, and OLED Show."
echo
echo "Optional OLED show asset:"
echo "  Keep animation_frames.h or animation_frames(1).h in this project"
echo "  OR in your phone Downloads folder."
echo "  The player reads your local frame file directly."
