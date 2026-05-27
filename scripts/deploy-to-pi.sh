#!/usr/bin/env bash
# Sync local repo to the Pi over SSH (prompts for password if no key is set up).
#
# Usage:
#   ./scripts/deploy-to-pi.sh
#   PI_HOST=softhoarders-pi.local PI_USER=softhoarders ./scripts/deploy-to-pi.sh
#
# One-time key setup (no password on future runs):
#   ssh-copy-id softhoarders@softhoarders-pi.local

set -euo pipefail

PI_USER="${PI_USER:-softhoarders}"
PI_HOST="${PI_HOST:-softhoarders-pi.local}"
PI_DIR="${PI_DIR:-/home/$PI_USER/upright}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Syncing $REPO_ROOT → $PI_USER@$PI_HOST:$PI_DIR"

ssh "$PI_USER@$PI_HOST" "mkdir -p '$PI_DIR'"

rsync -avz --progress \
  --exclude '.git/' \
  --exclude 'firmware/.venv/' \
  --exclude '**/__pycache__/' \
  --exclude '**/.pytest_cache/' \
  --exclude 'firmware/data/*.db' \
  --exclude 'firmware/data/*.db-wal' \
  --exclude 'firmware/data/*.db-shm' \
  --exclude 'reference docs/' \
  "$REPO_ROOT/" "$PI_USER@$PI_HOST:$PI_DIR/"

echo ""
echo "Done. On the Pi, install or restart with:"
echo "  ssh $PI_USER@$PI_HOST"
echo "  cd ~/upright && bash install.sh    # first time"
echo "  # or after updates:"
echo "  cd ~/upright/firmware && source ../.venv/bin/activate && pip install -e '.[pi]'"
echo "  sudo systemctl restart upright upright-web"
