/* Yummy service worker: network-first shell, cache-first immutable assets. */
const V = "yummy-v3";
const PRECACHE = [
  "/", "/static/app.css", "/static/app.js",
  "/static/img/logo.png", "/static/img/favicon.png"
];

self.addEventListener("install", e => {
  self.skipWaiting();
  e.waitUntil(caches.open(V).then(c => c.addAll(PRECACHE)).catch(() => {}));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request)
        .then(r => { const cl = r.clone(); caches.open(V).then(c => c.put("/", cl)); return r; })
        .catch(() => caches.match("/"))
    );
    return;
  }
  if (url.pathname.endsWith("/app.css") || url.pathname.endsWith("/app.js")) {
    e.respondWith(
      fetch(e.request).then(res => {
        const cl = res.clone(); caches.open(V).then(c => c.put(e.request, cl)); return res;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
  if (url.pathname.includes("/static/img/")) {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request).then(res => {
        const cl = res.clone(); caches.open(V).then(c => c.put(e.request, cl)); return res;
      }))
    );
  }
});
