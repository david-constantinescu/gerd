#!/usr/bin/env bash
# Restore UI/button snapshot saved before battery icon + nav changes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/data/ui.revert"
DST="$ROOT/src/upright"
cp "$SRC/ui.py" "$DST/modes/ui.py"
cp "$SRC/ui_theme.py" "$DST/modes/ui_theme.py"
cp "$SRC/button.py" "$DST/hal/button.py"
cp "$SRC/manager.py" "$DST/modes/manager.py"
cp "$SRC/menu.py" "$DST/modes/menu.py"
echo "Restored UI snapshot from data/ui.revert/ (saved before battery + button nav update)"
echo "Restart upright on the Pi: sudo systemctl restart upright"
