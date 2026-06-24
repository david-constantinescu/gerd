#!/usr/bin/env bash
# upright-netdiag — dump Wi-Fi / NetworkManager state to the FAT boot partition
# on every boot, so it can be read from another computer (e.g. a Mac) by just
# reading the SD card's boot partition — no SSH or ext4 tooling needed.
#
# Installed by install.sh as a systemd oneshot (upright-netdiag.service) that
# runs ~20 s after NetworkManager comes up. Output: <boot>/upright-netdiag.txt
set -u

# Find the FAT boot partition mountpoint (newer images use /boot/firmware).
BOOT=/boot/firmware
[[ -d "$BOOT" ]] || BOOT=/boot
OUT="$BOOT/upright-netdiag.txt"

run() { echo "### $* ###"; "$@" 2>&1 || echo "(failed: $?)"; echo; }

{
  echo "UpRight network diagnostic — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo "hostname: $(hostname)"
  echo "========================================================================"
  run nmcli -t -f RUNNING,STATE general
  run nmcli device status
  run nmcli -f GENERAL.STATE,GENERAL.CONNECTION,WIFI-PROPERTIES device show wlan0
  run nmcli -t -f NAME,TYPE,AUTOCONNECT,ACTIVE connection show
  run nmcli -f IP4.ADDRESS device show wlan0
  run nmcli -f WIFI radio
  run rfkill list
  run iw reg get
  run iw dev
  run cat /etc/network/interfaces
  echo "### grep ifupdown managed ###"; grep -RsE 'managed' /etc/NetworkManager/ 2>&1; echo
  run systemctl is-active NetworkManager wpa_supplicant upright upright-web
  echo "### dmesg wifi ###"; dmesg 2>/dev/null | grep -iE 'brcmfmac|cfg80211|wlan' | tail -25; echo
} > "$OUT" 2>&1
sync
