// Minimal offline-first service worker: cache shell, pass through API.
const CACHE = "sentinel-v1";
const SHELL = ["/", "/food-log", "/sleep", "/reports", "/settings",
               "/static/style.css", "/static/app.js", "/static/manifest.json"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // always live
  e.respondWith(
    caches.match(e.request).then((r) => r || fetch(e.request))
  );
});
