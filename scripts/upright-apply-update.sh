#!/bin/bash
# One-shot SD sync: unpack upright-code-sync.tar.gz onto the rootfs, then reboot.
# Invoked once via cmdline.txt → systemd.run= (removed automatically on success).
set -euo pipefail

if [[ -f /boot/firmware/cmdline.txt ]]; then
  BOOT=/boot/firmware
elif [[ -d /boot/firmware ]]; then
  BOOT=/boot/firmware
elif [[ -f /boot/cmdline.txt ]]; then
  BOOT=/boot
else
  BOOT=/boot
fi

LOG="$BOOT/upright-apply.log"
TAR="$BOOT/upright-code-sync.tar.gz"
STAMP="$BOOT/.upright-sync-stamp"
DEST=/home/softhoarders/upright
USER=softhoarders

log() { echo "$(date -Is) $*" | tee -a "$LOG"; }

log "=== UpRight SD code sync starting ==="

[[ -f $TAR ]] || { log "no tarball at $TAR — nothing to do"; exit 0; }

TAR_ID=$(md5sum "$TAR" | awk '{print $1}')
if [[ -f $STAMP ]] && [[ "$(cat "$STAMP")" == "$TAR_ID" ]]; then
  log "already applied $TAR_ID — skipping"
  exit 0
fi

install -d -o "$USER" -g "$USER" "$DEST"
BACKUP=$(mktemp -d)
trap 'rm -rf "$BACKUP"' EXIT

preserve() {
  local rel="$1"
  if [[ -e $DEST/$rel ]]; then
    install -d -m 0755 "$BACKUP/$(dirname "$rel")"
    cp -a "$DEST/$rel" "$BACKUP/$rel"
    log "preserved $rel"
  fi
}

preserve .venv
preserve firmware/data/upright.db
preserve firmware/data/upright.db-wal
preserve firmware/data/upright.db-shm
preserve firmware/data/web_secret.txt
preserve firmware/data/display.json

log "extracting $TAR → $DEST"
tar xzf "$TAR" -C "$DEST" \
  --exclude='./firmware/data/upright.db' \
  --exclude='./firmware/data/upright.db-wal' \
  --exclude='./firmware/data/upright.db-shm' \
  --exclude='./firmware/data/web_secret.txt' \
  --exclude='./firmware/data/display.json' \
  --exclude='./firmware/.venv' \
  --exclude='./.venv'

restore() {
  local rel="$1"
  if [[ -e $BACKUP/$rel ]]; then
    rm -rf "$DEST/$rel"
    install -d -m 0755 "$DEST/$(dirname "$rel")"
    cp -a "$BACKUP/$rel" "$DEST/$rel"
    log "restored $rel"
  fi
}

restore .venv
restore firmware/data/upright.db
restore firmware/data/upright.db-wal
restore firmware/data/upright.db-shm
restore firmware/data/web_secret.txt
restore firmware/data/display.json

chown -R "$USER:$USER" "$DEST"
rm -f "$DEST/firmware/src/upright/hal/hrv.py" "$DEST/firmware/scripts/hrv_dump.py" 2>/dev/null || true

log "installing systemd units"
cat > /etc/systemd/system/upright.service <<EOF
[Unit]
Description=UpRight firmware loop
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$DEST
Environment=PYTHONPATH=$DEST/firmware/src
ExecStart=$DEST/.venv/bin/python -m upright.main
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/upright-web.service <<EOF
[Unit]
Description=UpRight Flask PWA
After=network.target upright.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$DEST
Environment=PYTHONPATH=$DEST/firmware/src
AmbientCapabilities=CAP_NET_BIND_SERVICE
ExecStart=$DEST/.venv/bin/gunicorn -b 0.0.0.0:80 -w 1 --timeout 120 --chdir $DEST/firmware/src upright.web.app:app
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable upright.service upright-web.service 2>/dev/null || true

log "configuring setup-AP captive portal (dnsmasq DNS redirect)"
install -d -m 0755 /etc/NetworkManager/dnsmasq-shared.d
cat > /etc/NetworkManager/dnsmasq-shared.d/upright-captive.conf <<'EOF'
# UpRight setup AP captive portal — resolve all names to the gateway.
address=/#/10.42.0.1
EOF
systemctl restart NetworkManager 2>/dev/null || true

if [[ -f $BOOT/config.txt ]] && ! grep -q '^country=' "$BOOT/config.txt"; then
  printf '\ncountry=RO\n' >> "$BOOT/config.txt"
  log "appended country=RO to config.txt"
fi

echo "$TAR_ID" > "$STAMP"

if [[ -f $BOOT/cmdline.txt ]]; then
  sed -i \
    -e 's/systemd\.run=[^ ]* *//g' \
    -e 's/systemd\.run_success_action=[^ ]* *//g' \
    -e 's/systemd\.run_failure_action=[^ ]* *//g' \
    "$BOOT/cmdline.txt"
  log "removed systemd.run from cmdline.txt"
fi

log "=== sync complete — rebooting ==="
systemctl restart upright.service upright-web.service 2>/dev/null || true
exit 0
