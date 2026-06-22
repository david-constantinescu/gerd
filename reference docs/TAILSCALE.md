# Tailscale — remote access to UpRight

The Pi normally exposes the web app only on your **local Wi-Fi** at
`http://softhoarders-pi.local` (mDNS). With Tailscale, you can open the same UI
from anywhere on your tailnet (phone/laptop on Tailscale, no port forwarding) —
handy for remote SSH/debugging when the Pi isn't on your LAN.

## One-time install on the Pi

From the repo on the device:

```bash
cd ~/upright
sudo bash scripts/pi-install-tailscale.sh
```

Or during full install:

```bash
UPRIGHT_INSTALL_TAILSCALE=1 curl -fsSL …/install.sh | bash
```

## Link this Pi to your network

### Option A — browser login (easiest)

```bash
sudo tailscale up --hostname=upright-pi
```

Copy the URL it prints, sign in with your Tailscale account, and approve the device.

### Option B — auth key (headless / scripted)

1. Create a reusable or one-off key at  
   https://login.tailscale.com/admin/settings/keys  
2. On the Pi:

```bash
export TAILSCALE_AUTH_KEY="tskey-auth-xxxxxxxx"
export TAILSCALE_HOSTNAME="upright-pi"
sudo -E bash scripts/pi-install-tailscale.sh
```

### Check status

```bash
tailscale status
tailscale ip -4
```

Example: if the IP is `100.64.12.34`, open:

- Dashboard: `http://100.64.12.34/`
- **Control panel** (login): `http://100.64.12.34/control`  
  Username: `softhoarders` · Password: `0031` (change in `firmware/data/config.json` → `web_username` / `web_password`)

## Notes

- Tailscale runs over its own interface (`tailscale0`) and is independent of
  `wlan0`, so it works whether the Pi is a Wi-Fi client or briefly hosting the
  **UpRight-Setup** provisioning AP.
- Commands from the web UI still go through the SQLite **inbox**; the `upright` firmware service must be running (`systemctl status upright`).
- For SSH: `ssh softhoarders@100.64.12.34` (if SSH is enabled on the Pi).

## Change web password

Edit on the Pi:

```bash
nano ~/upright/firmware/data/config.json
```

Set `"web_username"` and `"web_password"`, then:

```bash
sudo systemctl restart upright-web
```
