// Offline shell — network-first for JS/CSS/HTML so UI updates always land.
const CACHE = "upright-v4";

const SHELL = [
  "/",
  "/food-log",
  "/sleep",
  "/reports",
  "/settings",
  "/control",
  "/static/style.css",
  "/static/manifest.json",
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (url.pathname.startsWith("/api/")) return;

  if (url.pathname.startsWith("/static/") && url.pathname.endsWith(".js")) {
    e.respondWith(networkFirst(e.request));
    return;
  }
  if (url.pathname.startsWith("/static/") && url.pathname.endsWith(".css")) {
    e.respondWith(networkFirst(e.request));
    return;
  }
  e.respondWith(
    fetch(e.request)
      .then((r) => r)
      .catch(() => caches.match(e.request))
  );
});

async function networkFirst(request) {
  try {
    const res = await fetch(request);
    const cache = await caches.open(CACHE);
    cache.put(request, res.clone());
    return res;
  } catch (_) {
    return (await caches.match(request)) || new Response("", { status: 503 });
  }
}
