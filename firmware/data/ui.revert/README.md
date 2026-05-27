# UI revert snapshot

Saved **before** battery icon + two-button navigation update (A tap=up, A hold=back, B tap=down, B hold=select).

Restore on Mac or Pi:

```bash
bash firmware/scripts/ui_revert.sh
sudo systemctl restart upright   # on Pi
```

Files: `ui.py`, `ui_theme.py`, `button.py`, `manager.py`, `menu.py`
