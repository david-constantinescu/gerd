// UpRight — single tiny frontend script. Plain fetch polling, no build step.

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

async function j(url, opts) {
  const r = await fetch(url, opts);
  return r.json();
}

async function refreshLive() {
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
        return `<li><b>${when}</b> — ${e.kind} ${badgeFor(e.payload)}</li>`;
      }).join("");
    }
    if (d.last_meal && $("#last-meal")) {
      const at = new Date(d.last_meal.ts * 1000);
      const mins = Math.floor((Date.now() - at) / 60000);
      $("#last-meal").innerHTML = `<b>${mins}m ago</b> <div class="muted">${d.last_meal.notes || ""}</div>`;
    }
  } catch (e) {
    console.warn(e);
  }
}

function badgeFor(p) {
  if (!p || !p.risk) return "";
  const c = { LOW: "low", MEDIUM: "med", HIGH: "high" }[p.risk] || "";
  return `<span class="badge ${c}">${p.risk}</span>`;
}

async function logMeal() {
  const notes = prompt("Meal notes (optional)") || "";
  await j("/api/log/meal", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notes }) });
  refreshLive();
}
async function logSymptom() {
  const sev = prompt("Severity 1-3", "2");
  if (!sev) return;
  const type = prompt("Type (heartburn / regurgitation / bloating / chest pain / other)", "heartburn");
  await j("/api/log/symptom", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ severity: sev, type }) });
  refreshLive();
}
async function logWater() {
  await j("/api/log/water", { method: "POST" });
  refreshLive();
}
async function calibrate() {
  await j("/api/log/meal", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  alert("calibration queued");
}

// ---- food log page ----
async function loadFoods() {
  if (!$("#foods-table")) return;
  const data = await j("/api/foods");
  const tbody = $("#foods-table tbody");
  tbody.innerHTML = Object.values(data).map((f) =>
    `<tr><td>${f.name}</td><td>${f.risk}</td><td>${f.upright_hours}</td><td></td></tr>`
  ).join("");
  const ev = await j("/api/events?limit=100");
  const meals = ev.filter((e) => e.kind === "food_photo" || e.kind === "meal");
  $("#food-list").innerHTML = meals.map((e) => {
    const when = new Date(e.ts * 1000).toLocaleString();
    return `<li><b>${when}</b> — ${e.payload.name || "meal"} ${badgeFor(e.payload)}</li>`;
  }).join("") || "<li>no entries yet</li>";
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

// ---- sleep page ----
async function loadSleep() {
  if (!$("#sleep-summary")) return;
  const [rows, stats] = await Promise.all([j("/api/sleep"), j("/api/analytics?days=7")]);
  if (!rows.length) {
    $("#sleep-summary").textContent = "No sleep data yet. Try Settings → Demo mode on the device.";
    return;
  }
  const last = rows[0];
  const avg = stats.avg_sleep_score != null ? ` · 7d avg <b>${stats.avg_sleep_score}</b>` : "";
  $("#sleep-summary").innerHTML =
    `<b>${last.night_of}</b> — ${Math.round(last.duration_s / 3600)}h, score ${last.score}/100, nudges ${last.nudges}${avg}`;
  const bar = $("#sleep-bar");
  bar.innerHTML = "";
  for (const [k, cls] of [["left_pct", "left"], ["right_pct", "right"], ["back_pct", "back"], ["front_pct", "front"]]) {
    const s = document.createElement("span");
    s.className = `sw ${cls}`;
    s.style.width = (last[k] || 0) + "%";
    s.style.display = "inline-block";
    bar.appendChild(s);
  }
  $("#sleep-history").innerHTML = rows.map((r) =>
    `<li><b>${r.night_of}</b> — score ${r.score}, left ${Math.round(r.left_pct)}%, back ${Math.round(r.back_pct)}%, nudges ${r.nudges}</li>`
  ).join("");
  if ($("#sleep-analytics")) {
    $("#sleep-analytics").innerHTML =
      `<p>Best night: <b>${stats.best_sleep_night || "—"}</b> (${stats.best_sleep_score ?? "—"}/100)</p>` +
      `<p class="muted">Meals ${stats.meals} · symptoms ${stats.symptoms} · avg reflux ${stats.avg_reflux_score ?? "—"}</p>`;
  }
}

// ---- reports ----
async function loadReports() {
  if (!$("#morning-report")) return;
  const stats = await j("/api/analytics?days=7");
  $("#morning-report").innerHTML =
    `7-day meals: <b>${stats.meals}</b><br>` +
    `Symptoms: <b>${stats.symptoms}</b><br>` +
    `Food photos: <b>${stats.food_photos}</b><br>` +
    `Avg sleep score: <b>${stats.avg_sleep_score ?? "—"}</b><br>` +
    `Avg reflux score: <b>${stats.avg_reflux_score ?? "—"}</b>`;
  const dayRows = (stats.per_day || []).map((d) =>
  `<tr><td>${d.date}</td><td>${d.meals}</td><td>${d.symptoms}</td><td>${d.food}</td></tr>`
  ).join("");
  $("#trends").innerHTML =
    `<table class="mini-table"><thead><tr><th>Day</th><th>Meals</th><th>Sx</th><th>Food</th></tr></thead><tbody>${dayRows || "<tr><td colspan=4>no data</td></tr>"}</tbody></table>`;
}

// ---- settings ----
async function initSettings() {
  $$("[data-setting]").forEach((el) => {
    const key = el.dataset.setting;
    const saveVal = async () => {
      const body = {};
      body[key] = el.type === "checkbox" ? el.checked :
                  el.type === "number" || el.type === "range" ? parseFloat(el.value) : el.value;
      await j("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
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
  $("#med-list").innerHTML = meds.map((m) =>
    `<li><b>${m.name}</b> ${m.dose || ""} at ${m.time}
     <button onclick="delMed(${m.id})">×</button></li>`
  ).join("") || "<li>no medications</li>";
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
async function delMed(id) {
  await j("/api/medications?id=" + id, { method: "DELETE" });
  loadMeds();
}

async function sendDeviceCommand(command, payload = {}) {
  const r = await fetch("/api/device/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ command, payload }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function initControl() {
  const status = $("#cmd-status");
  const grid = $("#cmd-grid");
  if (!grid) return;

  const flash = (msg, ok = true) => {
    if (status) {
      status.textContent = msg;
      status.style.color = ok ? "" : "var(--err)";
    }
  };

  grid.querySelectorAll("button[data-cmd]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        let payload = {};
        if (btn.dataset.payload) payload = JSON.parse(btn.dataset.payload);
        const res = await sendDeviceCommand(btn.dataset.cmd, payload);
        flash(`Sent ${res.command} → ${res.queued}`);
      } catch (e) {
        flash(e.message, false);
      }
    });
  });

  const sym = $("#sym-send");
  if (sym) {
    sym.addEventListener("click", async () => {
      try {
        await sendDeviceCommand("symptom", {
          severity: parseInt($("#sym-sev").value, 10),
          type: $("#sym-type").value,
        });
        flash("Symptom queued");
      } catch (e) {
        flash(e.message, false);
      }
    });
  }

  const custom = $("#cmd-send");
  if (custom) {
    custom.addEventListener("click", async () => {
      try {
        const cmd = $("#cmd-select").value;
        const raw = ($("#cmd-payload").value || "").trim();
        const payload = raw ? JSON.parse(raw) : {};
        const res = await sendDeviceCommand(cmd, payload);
        flash(`Sent ${res.command}`);
      } catch (e) {
        flash(e.message, false);
      }
    });
  }
}

// dispatch
window.addEventListener("DOMContentLoaded", () => {
  refreshLive();
  loadFoods();
  loadSleep();
  loadReports();
  initSettings();
  initControl();
  setInterval(refreshLive, 2000);
});
window.logMeal = logMeal;
window.logSymptom = logSymptom;
window.logWater = logWater;
window.addFood = addFood;
window.addMed = addMed;
window.delMed = delMed;
window.calibrate = calibrate;
