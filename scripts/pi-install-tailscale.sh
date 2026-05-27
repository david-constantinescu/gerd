#!/usr/bin/env bash
# Install Tailscale on Raspberry Pi OS and join your tailnet.
#
# Usage (on the Pi):
#   sudo bash scripts/pi-install-tailscale.sh
#
# Optional env:
#   TAILSCALE_AUTH_KEY=tskey-auth-...   # non-interactive join (from https://login.tailscale.com/admin/settings/keys)
#   TAILSCALE_HOSTNAME=upright-pi       # name shown in the admin console
#
# After install, reach the web UI at http://<tailscale-ip>/ (same Flask app on port 80).

set -euo pipefail

log() { printf '\033[1;34m[tailscale]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[tailscale]\033[0m %s\n' "$*" >&2; }

if [[ $EUID -ne 0 ]]; then
  exec sudo TAILSCALE_AUTH_KEY="${TAILSCALE_AUTH_KEY:-}" \
    TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-upright-pi}" \
    bash "$0" "$@"
fi

if ! command -v tailscale >/dev/null 2>&1; then
  log "installing Tailscale…"
  curl -fsSL https://tailscale.com/install.sh | sh
else
  log "tailscale already installed"
fi

systemctl enable --now tailscaled

HOSTNAME="${TAILSCALE_HOSTNAME:-upright-pi}"
if tailscale status 2>/dev/null | grep -q "Logged in"; then
  log "already logged in:"
  tailscale status | head -5
  exit 0
fi

if [[ -n "${TAILSCALE_AUTH_KEY:-}" ]]; then
  log "joining tailnet with auth key (hostname=$HOSTNAME)…"
  tailscale up --auth-key="$TAILSCALE_AUTH_KEY" --hostname="$HOSTNAME" --accept-routes
else
  log "starting interactive login — open the URL below in a browser:"
  echo ""
  tailscale up --hostname="$HOSTNAME" --accept-routes
  echo ""
fi

log "Tailscale IP(s):"
tailscale ip -4 || true
log "Web dashboard: http://$(tailscale ip -4 2>/dev/null | head -1)/control"
