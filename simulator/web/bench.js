"use strict";

const $ = (sel) => document.querySelector(sel);

async function post(url, body) {
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return await r.json();
  } catch (e) {
    console.error("post failed", url, e);
  }
}

/* ---- screen: MJPEG with PNG-polling fallback -------------------------- */
const screen = $("#screen");
let pollTimer = null;
function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    screen.src = "/screen.png?scale=3&t=" + Date.now();
  }, 250);
}
screen.addEventListener("error", () => { startPoll(); });
screen.src = "/stream.mjpeg";

/* ---- hardware buttons ------------------------------------------------- */
document.querySelectorAll(".hw-btn, .mini[data-btn]").forEach((el) => {
  el.addEventListener("click", () =>
    post("/api/button", { button: el.dataset.btn, pattern: el.dataset.pat || "single" }));
});
document.querySelectorAll(".mini[data-enc]").forEach((el) => {
  el.addEventListener("click", () => post("/api/encoder", { action: el.dataset.enc }));
});

/* ---- posture --------------------------------------------------------- */
const pitch = $("#pitch"), roll = $("#roll");
const pitchVal = $("#pitch-val"), rollVal = $("#roll-val");
let postureTimer = null;
function sendPosture() {
  pitchVal.textContent = pitch.value + "°";
  rollVal.textContent = roll.value + "°";
  clearTimeout(postureTimer);
  postureTimer = setTimeout(() =>
    post("/api/posture", { pitch: +pitch.value, roll: +roll.value }), 40);
}
pitch.addEventListener("input", sendPosture);
roll.addEventListener("input", sendPosture);
document.querySelectorAll(".presets .mini").forEach((el) => {
  el.addEventListener("click", () => {
    pitch.value = el.dataset.pitch;
    roll.value = el.dataset.roll;
    sendPosture();
  });
});

/* ---- battery --------------------------------------------------------- */
const batt = $("#batt"), battVal = $("#batt-val"), battLow = $("#batt-low");
let battTimer = null;
function sendBattery() {
  battVal.textContent = batt.value + "%";
  clearTimeout(battTimer);
  battTimer = setTimeout(() =>
    post("/api/battery", { pct: +batt.value, low: battLow.checked }), 40);
}
batt.addEventListener("input", sendBattery);
battLow.addEventListener("change", sendBattery);

/* ---- commands -------------------------------------------------------- */
document.querySelectorAll(".cmd").forEach((el) => {
  el.addEventListener("click", () => post("/api/command", { command: el.dataset.cmd }));
});

/* ---- camera ---------------------------------------------------------- */
const video = $("#cam-preview"), camStatus = $("#cam-status");
let camStream = null, camLoop = null;
const canvas = document.createElement("canvas");

$("#cam-on").addEventListener("click", async () => {
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 } });
    video.srcObject = camStream;
    camStatus.textContent = "Webcam streaming to the device camera HAL.";
    camLoop = setInterval(pushFrame, 350);
  } catch (e) {
    camStatus.textContent = "Could not access webcam: " + e.message;
  }
});
$("#cam-off").addEventListener("click", () => {
  if (camLoop) clearInterval(camLoop), (camLoop = null);
  if (camStream) camStream.getTracks().forEach((t) => t.stop()), (camStream = null);
  video.srcObject = null;
  camStatus.textContent = "Webcam stopped.";
});
async function pushFrame() {
  if (!video.videoWidth) return;
  canvas.width = 320; canvas.height = 240;
  canvas.getContext("2d").drawImage(video, 0, 0, 320, 240);
  canvas.toBlob(async (blob) => {
    if (blob) await fetch("/api/camera/frame", { method: "POST",
      headers: { "Content-Type": "image/jpeg" }, body: blob });
  }, "image/jpeg", 0.8);
}
$("#cam-file").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const fd = fetch("/api/camera/frame", { method: "POST",
    headers: { "Content-Type": f.type || "image/jpeg" }, body: f });
  fd.then(() => (camStatus.textContent = "Uploaded still image to camera HAL."));
});

/* ---- state polling --------------------------------------------------- */
let lastMotorTs = 0, lastAudioTs = 0;
const device = $("#device");
async function pollState() {
  try {
    const r = await fetch("/api/state");
    const s = await r.json();

    $("#pill-boot").textContent = s.booted ? "● running" : "booting…";
    $("#pill-boot").classList.toggle("live", s.booted);
    $("#pill-state").textContent = "state: " + (s.fsm.state || "—") +
      (s.fsm.menu_open ? " · " + s.fsm.menu_screen : "");
    $("#pill-frames").textContent = "frames: " + s.frame_count;
    $("#pill-uptime").textContent = Math.round(s.uptime_s) + "s";

    // motor / audio indicators
    const motorEl = $("#act-motor"), audioEl = $("#act-audio");
    if (s.motor.length) {
      const m = s.motor[0];
      motorEl.querySelector("span").textContent = "buzz: " + m.pattern;
      if (m.ts > lastMotorTs) {
        lastMotorTs = m.ts;
        device.classList.remove("buzz"); void device.offsetWidth;
        device.classList.add("buzz");
        motorEl.classList.add("fire");
        setTimeout(() => motorEl.classList.remove("fire"), 600);
      }
    }
    if (s.audio.length) {
      const a = s.audio[0];
      audioEl.querySelector("span").textContent = a.name;
      if (a.ts > lastAudioTs) {
        lastAudioTs = a.ts;
        audioEl.classList.add("fire");
        setTimeout(() => audioEl.classList.remove("fire"), 600);
      }
    }

    $("#log").textContent = (s.log || []).join("\n");
  } catch (e) { /* server may be busy serving the stream */ }
}
setInterval(pollState, 700);
pollState();
