// UpRight — single tiny frontend script. Plain fetch polling, no build step.

const APP_VER = "5";

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

async function j(url, opts) {
  const r = await fetch(url, { credentials: "same-origin", ...opts });
  let data = {};
  try {
    data = await r.json();
  } catch (_) {
    /* non-json body */
  }
  if (!r.ok) {
    throw new Error(data.error || data.message || `HTTP ${r.status}`);
  }
  return data;
}

function showToast(msg, isErr = false) {
  const t = $("#toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.toggle("err", isErr);
  t.style.display = "block";
  t.style.pointerEvents = "none";
  clearTimeout(showToast._tm);
  showToast._tm = setTimeout(() => {
    t.style.display = "none";
  }, 2800);
}

async function refreshLive() {
  if (!$("#posture-pct") && !$("#timeline")) return;
  try {
    const d = await j("/api/live");
    if (d.posture && $("#posture-pct")) {
      const pct = Math.max(0, 100 - Math.abs(d.posture.pitch) * 3);
      $("#posture-pct").textContent = Math.round(pct) + "%";
      $("#posture-bar").style.width = pct + "%";
      $("#pitch").textContent = d.posture.pitch.toFixed(1);
      $("#state").textContent = d.posture.state;
    }
    if ($("#timeline")) {
      $("#timeline").innerHTML = d.events.slice(0, 20).map((e) => {
        const when = new Date(e.ts * 1000).toLocaleTimeString();
        const payload = e.payload || {};
        return `<li><b>${when}</b> — ${e.kind} ${badgeFor(payload)}</li>`;
      }).join("");
    }
    if (d.last_meal && $("#last-meal")) {
      const at = new Date(d.last_meal.ts * 1000);
      const mins = Math.floor((Date.now() - at) / 60000);
      $("#last-meal").innerHTML =
        `<b>${mins}m ago</b> <div class="muted">${d.last_meal.notes || ""}</div>`;
    }
  } catch (e) {
    console.warn("refreshLive", e);
  }
}

function badgeFor(p) {
  if (!p || !p.risk) return "";
  const c = { LOW: "low", MEDIUM: "med", HIGH: "high" }[p.risk] || "";
  return `<span class="badge ${c}">${p.risk}</span>`;
}

async function logMeal() {
  const notes = prompt("Meal notes (optional)");
  if (notes === null) return;
  try {
    await j("/api/log/meal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: notes || "" }),
    });
    showToast("Meal logged — post-meal timer on device");
    refreshLive();
  } catch (e) {
    showToast(e.message || String(e), true);
  }
}

async function logSymptom() {
  const sev = prompt("Severity 1-3", "2");
  if (sev === null || sev === "") return;
  const type = prompt(
    "Type (Heartburn / Regurgitation / Bloating / Chest pain / Other)",
    "Heartburn"
  );
  if (type === null || type === "") return;
  try {
    await j("/api/log/symptom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ severity: parseInt(sev, 10), type }),
    });
    showToast("Symptom logged");
    refreshLive();
  } catch (e) {
    showToast(e.message || String(e), true);
  }
}

async function logWater() {
  try {
    await j("/api/log/water", { method: "POST" });
    showToast("Water logged");
    refreshLive();
  } catch (e) {
    showToast(e.message || String(e), true);
  }
}

async function handleDeviceCommand(cmd, payload = {}) {
  if (cmd === "meal") {
    const notes = prompt("Meal notes (optional)");
    if (notes === null) return;
    await j("/api/log/meal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: notes || "" }),
    });
    showToast("Meal logged");
    return;
  }
  const res = await fetch("/api/device/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ command: cmd, payload }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  showToast(`Sent ${data.command}`);
}

/** One delegated click handler — survives stale caches and dynamic HTML. */
function bindClickDelegation() {
  document.addEventListener("click", async (ev) => {
    const actionBtn = ev.target.closest("[data-action]");
    if (actionBtn) {
      ev.preventDefault();
      const action = actionBtn.getAttribute("data-action");
      try {
        if (action === "log-meal") await logMeal();
        else if (action === "log-symptom") await logSymptom();
        else if (action === "log-water") await logWater();
      } catch (e) {
        showToast(e.message || String(e), true);
      }
      return;
    }

    const cmdBtn = ev.target.closest("button[data-cmd]");
    if (cmdBtn) {
      ev.preventDefault();
      try {
        let payload = {};
        if (cmdBtn.dataset.payload) payload = JSON.parse(cmdBtn.dataset.payload);
        await handleDeviceCommand(cmdBtn.dataset.cmd, payload);
      } catch (e) {
        showToast(e.message || String(e), true);
      }
      return;
    }

    if (ev.target.closest("#sym-send")) {
      ev.preventDefault();
      try {
        await fetch("/api/device/command", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            command: "symptom",
            payload: {
              severity: parseInt($("#sym-sev").value, 10),
              type: $("#sym-type").value,
            },
          }),
        }).then(async (r) => {
          if (!r.ok) {
            const d = await r.json().catch(() => ({}));
            throw new Error(d.error || `HTTP ${r.status}`);
          }
        });
        showToast("Symptom queued");
      } catch (e) {
        showToast(e.message || String(e), true);
      }
      return;
    }

    const delMedBtn = ev.target.closest("[data-action='del-med']");
    if (delMedBtn) {
      ev.preventDefault();
      delMed(delMedBtn.dataset.id).then(loadMeds).catch((e) => showToast(String(e), true));
      return;
    }

    if (ev.target.closest("#cmd-send")) {
      ev.preventDefault();
      try {
        const cmd = $("#cmd-select").value;
        const raw = ($("#cmd-payload").value || "").trim();
        const payload = raw ? JSON.parse(raw) : {};
        await handleDeviceCommand(cmd, payload);
      } catch (e) {
        showToast(e.message || String(e), true);
      }
    }
  });
}

async function loadFoods() {
  if (!$("#foods-table")) return;
  const data = await j("/api/foods");
  const tbody = $("#foods-table tbody");
  tbody.innerHTML = Object.values(data).map((f) =>
    `<tr><td>${f.name}</td><td>${f.risk}</td><td>${f.upright_hours}</td><td></td></tr>`
  ).join("");
  const ev = await j("/api/events?limit=100");
  const meals = ev.filter((e) => e.kind === "food_photo" || e.kind === "meal");
  $("#food-list").innerHTML =
    meals
      .map((e) => {
        const when = new Date(e.ts * 1000).toLocaleString();
        const p = e.payload || {};
        return `<li><b>${when}</b> — ${p.name || "meal"} ${badgeFor(p)}</li>`;
      })
      .join("") || "<li>no entries yet</li>";
}

async function addFood() {
  await j("/api/foods", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: $("#new-food").value,
      risk: $("#new-risk").value,
      upright_hours: parseFloat($("#new-hours").value),
    }),
  });
  loadFoods();
}

async function loadSleep() {
  if (!$("#sleep-summary")) return;
  const [rows, stats] = await Promise.all([
    j("/api/sleep"),
    j("/api/analytics?days=7"),
  ]);
  if (!rows.length) {
    $("#sleep-summary").textContent =
      "No sleep data yet. Try Settings → Demo mode on the device.";
    return;
  }
  const last = rows[0];
  const avg =
    stats.avg_sleep_score != null
      ? ` · 7d avg <b>${stats.avg_sleep_score}</b>`
      : "";
  $("#sleep-summary").innerHTML =
    `<b>${last.night_of}</b> — ${Math.round(last.duration_s / 3600)}h, score ${last.score}/100, nudges ${last.nudges}${avg}`;
  const bar = $("#sleep-bar");
  bar.innerHTML = "";
  for (const [k, cls] of [
    ["left_pct", "left"],
    ["right_pct", "right"],
    ["back_pct", "back"],
    ["front_pct", "front"],
  ]) {
    const s = document.createElement("span");
    s.className = `sw ${cls}`;
    s.style.width = (last[k] || 0) + "%";
    s.style.display = "inline-block";
    bar.appendChild(s);
  }
  $("#sleep-history").innerHTML = rows
    .map(
      (r) =>
        `<li><b>${r.night_of}</b> — score ${r.score}, left ${Math.round(r.left_pct)}%, back ${Math.round(r.back_pct)}%, nudges ${r.nudges}</li>`
    )
    .join("");
  if ($("#sleep-analytics")) {
    $("#sleep-analytics").innerHTML =
      `<p>Best night: <b>${stats.best_sleep_night || "—"}</b> (${stats.best_sleep_score ?? "—"}/100)</p>` +
      `<p class="muted">Meals ${stats.meals} · symptoms ${stats.symptoms} · avg reflux ${stats.avg_reflux_score ?? "—"}</p>`;
  }
}

async function loadReports() {
  if (!$("#morning-report")) return;
  const stats = await j("/api/analytics?days=7");
  $("#morning-report").innerHTML =
    `7-day meals: <b>${stats.meals}</b><br>` +
    `Symptoms: <b>${stats.symptoms}</b><br>` +
    `Food photos: <b>${stats.food_photos}</b><br>` +
    `Avg sleep score: <b>${stats.avg_sleep_score ?? "—"}</b><br>` +
    `Avg reflux score: <b>${stats.avg_reflux_score ?? "—"}</b>`;
  const dayRows = (stats.per_day || [])
    .map(
      (d) =>
        `<tr><td>${d.date}</td><td>${d.meals}</td><td>${d.symptoms}</td><td>${d.food}</td></tr>`
    )
    .join("");
  $("#trends").innerHTML =
    `<table class="mini-table"><thead><tr><th>Day</th><th>Meals</th><th>Sx</th><th>Food</th></tr></thead><tbody>${dayRows || "<tr><td colspan=4>no data</td></tr>"}</tbody></table>`;
}

async function initSettings() {
  $$("[data-setting]").forEach((el) => {
    const key = el.dataset.setting;
    const saveVal = async () => {
      const body = {};
      body[key] =
        el.type === "checkbox"
          ? el.checked
          : el.type === "number" || el.type === "range"
            ? parseFloat(el.value)
            : el.value;
      await j("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const out = el.parentElement.querySelector(".slider-val");
      if (out) out.textContent = el.value;
    };
    el.addEventListener("change", saveVal);
    if (el.type === "range") {
      const out = el.parentElement.querySelector(".slider-val");
      if (out) out.textContent = el.value;
    }
  });
  loadMeds();
}

async function loadMeds() {
  if (!$("#med-list")) return;
  const meds = await j("/api/medications");
  $("#med-list").innerHTML =
    meds
      .map(
        (m) =>
          `<li><b>${m.name}</b> ${m.dose || ""} at ${m.time}
     <button type="button" data-action="del-med" data-id="${m.id}">×</button></li>`
      )
      .join("") || "<li>no medications</li>";
}

async function delMed(id) {
  await j("/api/medications?id=" + id, { method: "DELETE" });
  loadMeds();
}

async function addMed() {
  await j("/api/medications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: $("#med-name").value,
      dose: $("#med-dose").value,
      time: $("#med-time").value,
    }),
  });
  loadMeds();
}

async function initWifi() {
  const statusEl = $("#wifi-status");
  if (!statusEl) return;
  try {
    const s = await j("/api/wifi/status");
    const url = s.url || `http://${s.mdns || "upright.local"}/`;
    statusEl.innerHTML =
      `Connected to <b>${s.ssid || "—"}</b><br>` +
      `Address: <b>${url}</b><br>` +
      `IP: <b>${s.ip || "—"}</b>` +
      (s.manageable ? "" : "<br><i>Wi-Fi switching not available on this host</i>");
    const qr = $("#wifi-qr");
    if (qr) qr.src = "/api/wifi/qr.png?t=" + Date.now();
  } catch (_) {
    statusEl.textContent = "network status unavailable";
  }
}

async function scanWifi() {
  const msg = $("#wifi-msg");
  const list = $("#wifi-list");
  if (!list) return;
  msg.textContent = "scanning…";
  const r = await fetch("/api/wifi/scan", { credentials: "same-origin" });
  if (r.status === 401) {
    msg.innerHTML = 'Please <a href="/login?next=/settings">log in</a> to manage Wi-Fi.';
    return;
  }
  const data = await r.json().catch(() => ({}));
  msg.textContent = data.available ? "" : "Wi-Fi control not available on this device.";
  const nets = data.networks || [];
  list.innerHTML =
    nets
      .map(
        (n) =>
          `<li><button type="button" class="wifi-net" data-ssid="${n.ssid}" data-secure="${n.secure}">
             ${n.secure ? "🔒" : "📶"} ${n.ssid} <span class="sig">${n.signal}%</span>
           </button></li>`
      )
      .join("") || "<li>no networks found</li>";
  list.querySelectorAll(".wifi-net").forEach((b) =>
    b.addEventListener("click", () => connectWifi(b.dataset.ssid, b.dataset.secure === "true"))
  );
}

async function connectWifi(ssid, secure) {
  const msg = $("#wifi-msg");
  let password = null;
  if (secure) {
    password = prompt(`Wi-Fi password for "${ssid}":`);
    if (password === null) return;
  }
  msg.textContent = `connecting to ${ssid}…`;
  const r = await fetch("/api/wifi/connect", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ssid, password }),
  });
  const data = await r.json().catch(() => ({}));
  if (data.ok) {
    showToast(`Connected to ${ssid}`);
    msg.textContent = `Connected to ${ssid} ✓`;
    setTimeout(initWifi, 2000);
  } else {
    msg.textContent = `Failed: ${data.message || "HTTP " + r.status}`;
  }
}

function boot() {
  bindClickDelegation();
  refreshLive();
  loadFoods();
  loadSleep();
  loadReports();
  initSettings();
  initWifi();
  setInterval(refreshLive, 2000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}

window.logMeal = logMeal;
window.logSymptom = logSymptom;
window.logWater = logWater;
window.addFood = addFood;
window.addMed = addMed;
window.delMed = delMed;
window.scanWifi = scanWifi;
window.connectWifi = connectWifi;
