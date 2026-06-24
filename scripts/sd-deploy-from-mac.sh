#!/usr/bin/env bash
# Deploy UpRight repo → Raspberry Pi SD card rootfs from macOS (ext4 via e2tools).
#
# Usage:
#   SD_DISK=disk8 ./scripts/sd-deploy-from-mac.sh
#
# Requires: brew install e2tools e2fsprogs
# The boot partition (FAT) mounts at /Volumes/bootfs automatically.

set -euo pipefail

export PATH="/usr/local/opt/e2fsprogs/sbin:/usr/local/opt/e2fsprogs/bin:${PATH:-/usr/bin:/bin}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SD_DISK="${SD_DISK:-disk8}"
SD_DEV="/dev/${SD_DISK}s2"
DEST="/home/softhoarders/upright"
UID_NUM=1000
GID_NUM=1000

log() { printf '\033[1;34m[sd-deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[sd-deploy]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run with sudo: sudo SD_DISK=$SD_DISK $0"

[[ -b $SD_DEV ]] || die "ext4 partition not found: $SD_DEV (check diskutil list)"
diskutil info "$SD_DEV" | grep -qi linux || die "$SD_DEV does not look like a Linux partition"

log "filesystem check (pre-write) on $SD_DEV"
e2fsck -fn "$SD_DEV" 2>&1 | tail -3 || true

copy_file() {
  local rel="$1"
  local src="$REPO_ROOT/$rel"
  local dst="$SD_DEV:$DEST/$rel"
  [[ -f $src ]] || die "missing source: $src"
  e2cp -a -O "$UID_NUM" -G "$GID_NUM" -p "$src" "$dst"
  COPIED=$((COPIED + 1))
  if (( COPIED % 25 == 0 )); then
    log "  … $COPIED files"
  fi
}

COPIED=0
log "syncing source tree → $DEST"
cd "$REPO_ROOT"
while IFS= read -r -d '' rel; do
  copy_file "$rel"
done < <(
  find . -type f \
    ! -path './.git/*' \
    ! -path './firmware/.venv/*' \
    ! -path './simulator/*' \
    ! -path './reference docs/*' \
    ! -path '*/__pycache__/*' \
    ! -path './firmware/.pytest_cache/*' \
    ! -path './firmware/data/upright.db' \
    ! -path './firmware/data/upright.db-*' \
    ! -path './firmware/data/*.db' \
    ! -path './firmware/data/web_secret.txt' \
    ! -path './firmware/data/display.json' \
    -print0
)
log "copied $COPIED files total"

log "removing obsolete modules (HRV removed from firmware)"
for obsolete in \
  firmware/src/upright/hal/hrv.py \
  firmware/scripts/hrv_dump.py; do
  e2rm "$SD_DEV:$DEST/$obsolete" 2>/dev/null || true
done

log "updating systemd units"
e2cp -O 0 -G 0 -P 0644 \
  "$REPO_ROOT/firmware/systemd/upright.service" \
  "$SD_DEV:/etc/systemd/system/upright.service"
e2cp -O 0 -G 0 -P 0644 \
  "$REPO_ROOT/firmware/systemd/upright-web.service" \
  "$SD_DEV:/etc/systemd/system/upright-web.service"

# Apply @USER@ / @DIR@ placeholders (overwritten below with final units).

cat > /tmp/upright.service <<'EOF'
[Unit]
Description=UpRight firmware loop
After=network.target

[Service]
Type=simple
User=softhoarders
WorkingDirectory=/home/softhoarders/upright
Environment=PYTHONPATH=/home/softhoarders/upright/firmware/src
ExecStart=/home/softhoarders/upright/.venv/bin/python -m upright.main
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > /tmp/upright-web.service <<'EOF'
[Unit]
Description=UpRight Flask PWA
After=network.target upright.service

[Service]
Type=simple
User=softhoarders
WorkingDirectory=/home/softhoarders/upright
Environment=PYTHONPATH=/home/softhoarders/upright/firmware/src
AmbientCapabilities=CAP_NET_BIND_SERVICE
ExecStart=/home/softhoarders/upright/.venv/bin/gunicorn -b 0.0.0.0:80 -w 1 --timeout 120 --chdir /home/softhoarders/upright/firmware/src upright.web.app:app
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

e2cp -O 0 -G 0 -P 0644 /tmp/upright.service "$SD_DEV:/etc/systemd/system/upright.service"
e2cp -O 0 -G 0 -P 0644 /tmp/upright-web.service "$SD_DEV:/etc/systemd/system/upright-web.service"

log "verifying key files (md5)"
TMPV=$(mktemp -d)
trap 'rm -rf "$TMPV"' EXIT
for rel in \
  firmware/src/upright/modes/manager.py \
  firmware/src/upright/services/i18n.py \
  firmware/data/locales/en.json \
  firmware/data/config.json; do
  local_md5=$(md5 -q "$REPO_ROOT/$rel")
  e2cp "$SD_DEV:$DEST/$rel" "$TMPV/remote"
  remote_md5=$(md5 -q "$TMPV/remote")
  if [[ "$local_md5" == "$remote_md5" ]]; then
    log "  OK  $rel"
  else
    die "checksum mismatch: $rel (local=$local_md5 remote=$remote_md5)"
  fi
done

log "filesystem check (post-write)"
e2fsck -fn "$SD_DEV" | tail -3
sync

log "done — safe to eject:"
log "  diskutil eject /dev/$SD_DISK"
log "Insert SD into Pi Zero 2 W and power on."
log "SSH: ssh softhoarders@softhoarders-pi.local"
log "Web: http://softhoarders-pi.local/"
