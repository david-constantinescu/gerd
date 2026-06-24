#!/usr/bin/env bash
# Prepare an SD card boot partition for one-shot Pi boot sync (no Mac sudo).
# Writes tarball + hook script to /Volumes/bootfs and patches cmdline.txt.
#
# Usage (SD inserted, bootfs mounted):
#   ./scripts/sd-boot-sync.sh
#   diskutil eject /dev/disk8

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BOOT="${BOOT_VOL:-/Volumes/bootfs}"

[[ -d $BOOT ]] || { echo "boot partition not mounted at $BOOT"; exit 1; }
[[ -f $BOOT/cmdline.txt ]] || { echo "not a Raspberry Pi boot partition"; exit 1; }

echo "[sd-boot-sync] packing latest code…"
tar czf "$BOOT/upright-code-sync.tar.gz" \
  -C "$REPO_ROOT" \
  --exclude './.git' \
  --exclude './firmware/.venv' \
  --exclude './simulator' \
  --exclude './reference docs' \
  --exclude '*/__pycache__' \
  --exclude './firmware/.pytest_cache' \
  .

echo "[sd-boot-sync] installing boot hook script…"
install -m 0755 "$REPO_ROOT/scripts/upright-apply-update.sh" "$BOOT/upright-apply-update.sh"

# Allow re-run when tarball changes.
rm -f "$BOOT/.upright-sync-stamp"

CMDLINE="$BOOT/cmdline.txt"
if ! grep -q 'systemd.run=/boot/firmware/upright-apply-update.sh' "$CMDLINE" 2>/dev/null; then
  # Bookworm mounts boot at /boot/firmware on the Pi.
  printf '%s systemd.run=/boot/firmware/upright-apply-update.sh systemd.run_success_action=reboot' \
    "$(tr -d '\n' < "$CMDLINE")" > "$CMDLINE"
  echo "" >> "$CMDLINE"
  echo "[sd-boot-sync] patched cmdline.txt for one-shot boot sync"
else
  echo "[sd-boot-sync] cmdline.txt already has systemd.run hook"
fi

cp "$REPO_ROOT/scripts/DEPLOY-INSTRUCTIONS.boot.txt" "$BOOT/DEPLOY-INSTRUCTIONS.txt" 2>/dev/null || true

CONFIG="$BOOT/config.txt"
if [[ -f $CONFIG ]] && ! grep -q '^country=' "$CONFIG"; then
  printf '\ncountry=RO\n' >> "$CONFIG"
  echo "[sd-boot-sync] appended country=RO to config.txt"
fi

ls -lh "$BOOT/upright-code-sync.tar.gz"
echo "[sd-boot-sync] done — eject SD and boot the Pi"
