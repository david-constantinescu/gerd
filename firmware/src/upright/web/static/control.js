// Control page only — terminal + authenticated device commands.

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

function initTerminal() {
  const el = document.getElementById("terminal");
  if (!el || typeof Terminal === "undefined") return;

  try {
    const term = new Terminal({
      cursorBlink: true,
      theme: { background: "#0d1117", foreground: "#e6edf3" },
      fontSize: 13,
      fontFamily: "Menlo, Monaco, 'Courier New', monospace",
    });
    let fitAddon = null;
    if (typeof FitAddon !== "undefined") {
      const FitCtor = FitAddon.FitAddon || FitAddon;
      fitAddon = new FitCtor();
      term.loadAddon(fitAddon);
    }
    term.open(el);
    if (fitAddon) fitAddon.fit();

    const resize = () => {
      if (fitAddon) fitAddon.fit();
      fetch("/api/terminal/resize", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: term.rows, cols: term.cols }),
      }).catch(() => {});
    };
    window.addEventListener("resize", resize);
    resize();

    term.writeln("UpRight Pi shell — connected.");
    term.writeln("");

    term.onData((data) => {
      fetch("/api/terminal/input", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data }),
      }).catch(() => term.writeln("\r\n[send failed]"));
    });

    const poll = async () => {
      try {
        const r = await fetch("/api/terminal/output", { credentials: "same-origin" });
        if (r.status === 401) return;
        const { data } = await r.json();
        if (data) term.write(data);
      } catch (_) {
        /* ignore */
      }
      setTimeout(poll, 80);
    };
    poll();
  } catch (e) {
    console.error("terminal init failed", e);
    el.textContent = "Terminal failed to start. Check login and refresh.";
  }
}

function initControlPage() {
  initTerminal();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initControlPage);
} else {
  initControlPage();
}
