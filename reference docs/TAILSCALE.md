# Tailscale — remote access to UpRight

The Pi normally only exposes the web app on its **hotspot** (`http://192.168.1.1`). With Tailscale, you can open the same UI from anywhere on your tailnet (phone/laptop on Tailscale, no port forwarding).

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

- Tailscale and the **UpRight-AP** hotspot can both be enabled; the Pi may use `wlan0` for AP. Tailscale uses its own interface (`tailscale0`).
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
