# UpRight — Raspberry Pi Simulator

A **virtual Raspberry Pi bench** that runs the *real* firmware from
[`../firmware`](../firmware) with a simulated hardware layer, surfaced through a
browser UI and an HTTP control API.

You click buttons, drag posture/battery sliders, and stream your webcam — and
the actual `upright` firmware (boot sequence, finite-state machine, menu system,
posture detection, alert/haptics, the *exact* `ui.render` frames it pushes to
the OLED/TFT) reacts as if it were on the device. The screen you see is the
genuine 160×128 ST7735R panel output, rendered by the firmware itself.

> **Why not QEMU?** A full-system emulator boots the ARM CPU and Linux, but it
> does **not** emulate the GPIO buttons, I²C IMU, SPI TFT, or USB camera — the
> peripherals that *are* this firmware. Under QEMU the code falls back to the
> same empty stubs it uses on a Mac. This simulator instead runs the real
> Python firmware natively (Python behaves identically to the Pi) and provides
> interactive, faithful simulation of the peripherals — which is *more* accurate
> for this project, not less.

## What is real vs. simulated

| Layer | In the simulator |
|-------|------------------|
| Boot sequence, FSM, menus, services, posture/sleep/meds logic | **Real firmware code, unmodified** |
| `ui.render` → display frames (160×128 RGB) | **Real** — captured and streamed to the browser |
| Web-app inbox commands (meal, symptom, calibrate, …) | **Real** — same SQLite inbox path as the PWA |
| Buttons A/B, encoder | Simulated → real `BUTTON_PRESS` / `ENCODER_*` events |
| IMU (pitch/roll) | Simulated from sliders → real `POSTURE_SAMPLE` events (incl. EMA smoothing) |
| Battery, heart-rate | Simulated → real `POWER_SAMPLE` / `HRV_SAMPLE` events |
| Camera (USB UVC) | Your **webcam** (or an uploaded image) → real `camera.capture()` |
| Motor (haptics), audio | Captured and shown as indicators in the UI |

The firmware's HAL has a clean seam (lazy hardware imports + `--dry-run`), so the
simulator swaps only the lowest layer via monkeypatching — **the firmware source
is never touched.** See [`sim/hal_sim.py`](sim/hal_sim.py).

## Run it

```bash
cd simulator
# use the firmware venv (already has flask + pillow + numpy):
../firmware/.venv/bin/python run.py
# → open http://localhost:8000
```

Flags:

| Flag | Effect |
|------|--------|
| `--port 9000` | listen on a different port (default 8000) |
| `--fresh` | reset the `.simdata` sandbox before starting |
| `--demo` | enable `demo_mode` (synthetic week data; disables live posture control) |
| `--open` | open the bench in your default browser |

Firmware data is sandboxed in `simulator/.simdata/` (seeded once from
`firmware/data/`), so running the simulator **never clobbers the real device DB.**

## HTTP / JSON control API (AI-controllable)

Any agent can drive the device with plain HTTP. The screen is readable as a PNG
(for vision models) and the full state as JSON.

| Method & path | Body | Purpose |
|---------------|------|---------|
| `GET /api/state` | — | FSM state, menu, sensors, motor/audio, log tail |
| `GET /screen.png?scale=N` | — | current panel frame as PNG (native 160×128 × N) |
| `GET /stream.mjpeg` | — | live MJPEG screen stream |
| `POST /api/button` | `{"button":"a\|b","pattern":"single\|double\|triple"}` | press a button |
| `POST /api/encoder` | `{"action":"cw\|ccw\|click"}` | rotate/click encoder |
| `POST /api/posture` | `{"pitch":<deg>,"roll":<deg>}` | set IMU posture |
| `POST /api/battery` | `{"pct":0-100,"low":bool}` | set battery |
| `POST /api/hrv` | `{"bpm":<n>,"rmssd":<ms>}` | inject a heart-rate sample |
| `POST /api/camera/frame` | raw `image/*` bytes, or `{"image":"<dataURL\|base64>"}` | feed a camera frame |
| `POST /api/command` | `{"command":"<name>","payload":{…}}` | queue a web-app inbox command |

`/api/command` names mirror the real PWA: `meal`, `symptom`, `water`,
`calibrate`, `open_menu`, `sleep`, `haptic`, `idle`, `demo_enter`, `demo_exit`,
`med_ack`, `config_reload` (raw inbox kinds like `cmd_open_menu` also accepted).

### Example: an agent drives the device

```bash
B=http://localhost:8000
curl -s $B/api/command -d '{"command":"open_menu"}' -H 'Content-Type: application/json'
curl -s $B/api/button  -d '{"button":"a"}'          -H 'Content-Type: application/json'   # navigate
curl -s $B/api/button  -d '{"button":"b"}'          -H 'Content-Type: application/json'   # select
curl -s $B/api/posture -d '{"pitch":35,"roll":2}'   -H 'Content-Type: application/json'   # slouch
curl -s $B/screen.png?scale=4 -o screen.png                                                # read the screen
curl -s $B/api/state | python -m json.tool                                                 # read the state
```

## Layout

```
simulator/
├── run.py            # entrypoint: boots firmware + serves the bench
├── sim/
│   ├── runner.py     # path/data sandbox, imports firmware, runs main() in a thread
│   ├── hal_sim.py    # simulated HAL backends + monkeypatch installer (no firmware edits)
│   ├── server.py     # Flask: bench UI + control API + screen stream
│   └── state.py      # SimDevice: thread-safe bridge (inputs ⇄ outputs ⇄ frames)
└── web/              # the browser bench (index.html, bench.css, bench.js)
```

## Notes & limits

- The encoder is *not fitted* on the real hardware (shares GPIO with the motor),
  so the firmware mostly ignores encoder events — the controls are provided for
  completeness.
- Food-photo classification runs for real in the sim: the bundled AIY Food model
  ships in `firmware/models/`, and `pip install ai-edge-litert` (in
  `requirements.txt`) provides the runtime on macOS. Enable the webcam or upload a
  food image, capture, and you get a real dish name + GERD risk. Without the
  runtime it degrades to "Not recognized".
- Posture alerts/haptics fire under the firmware's real timing/threshold rules
  (sustained slouch, post-meal strictness, etc.) — set a slouch and wait.
