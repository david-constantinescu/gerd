#!/usr/bin/env bash
# Restore last known-good display profile (portrait, slower SPI).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cp "$ROOT/data/display.revert.json" "$ROOT/data/display.json"
echo "Restored display.json from display.revert.json"
cat "$ROOT/data/display.json"
