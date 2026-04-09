// Reflux Sentinel — single tiny frontend script. Plain fetch polling, no build step.

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
  const rows = await j("/api/sleep");
  if (!rows.length) {
    $("#sleep-summary").textContent = "No sleep data yet.";
    return;
  }
  const last = rows[0];
  $("#sleep-summary").innerHTML =
    `<b>${last.night_of}</b> — ${Math.round(last.duration_s / 3600)}h, score ${last.score}/100, nudges ${last.nudges}`;
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
    `<li><b>${r.night_of}</b> — score ${r.score}, left ${Math.round(r.left_pct)}%, nudges ${r.nudges}</li>`
  ).join("");
}

// ---- reports ----
async function loadReports() {
  if (!$("#morning-report")) return;
  const rows = await j("/api/sleep");
  const ev = await j("/api/events?limit=500");
  const meals = ev.filter((e) => e.kind === "meal").length;
  const symptoms = ev.filter((e) => e.kind === "symptom").length;
  $("#morning-report").innerHTML =
    `Meals today: <b>${meals}</b><br>Symptoms: <b>${symptoms}</b><br>Sleep score: <b>${rows[0]?.score ?? "—"}</b>`;
  $("#trends").innerHTML = `<p class="muted">Rolling 7-day window based on <b>${ev.length}</b> events.</p>`;
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

// dispatch
window.addEventListener("DOMContentLoaded", () => {
  refreshLive();
  loadFoods();
  loadSleep();
  loadReports();
  initSettings();
  setInterval(refreshLive, 2000);
});
window.logMeal = logMeal;
window.logSymptom = logSymptom;
window.logWater = logWater;
window.addFood = addFood;
window.addMed = addMed;
window.delMed = delMed;
window.calibrate = calibrate;
