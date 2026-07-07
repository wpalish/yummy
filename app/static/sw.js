/* Yummy service worker: оффлайн-доступ к странице (и кодам заказов в localStorage). */
const V = "yummy-v1";
const PRECACHE = ["./", "img/logo.png", "img/favicon.png"];

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
  // страница: сеть в приоритете (свежие боксы), офлайн — из кэша
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request)
        .then(r => { const cl = r.clone(); caches.open(V).then(c => c.put("./", cl)); return r; })
        .catch(() => caches.match("./"))
    );
    return;
  }
  // картинки: кэш в приоритете
  if (url.pathname.includes("/img/")) {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request).then(res => {
        const cl = res.clone(); caches.open(V).then(c => c.put(e.request, cl)); return res;
      }))
    );
  }
});
