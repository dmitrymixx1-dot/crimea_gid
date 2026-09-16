/* Крым.Гид — service worker: офлайн-оболочка приложения.
   Статика — cache-first, API — network-first с откатом в кэш. */
const CACHE = "crimea-gid-v0.11.0";
const SHELL = [
  "/",
  "/static/index.html",
  "/static/style.css",
  "/static/plan-link.js",
  "/static/app.js",
  "/static/manifest.webmanifest",
  "/static/img/hero.jpg",
  "/static/img/icon-192.png",
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;

  // API: сеть важнее, в кэш складываем последний успешный ответ.
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then(c => c.put(e.request, copy));
          }
          return res;
        })
        .catch(() => caches.match(e.request).then(hit => hit || Response.error()))
    );
    return;
  }

  // Статика и SPA: кэш первым делом + фоновое обновление.
  e.respondWith(
    caches.match(e.request).then(hit => {
      const refresh = fetch(e.request).then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, copy));
        }
        return res;
      }).catch(() => hit);
      return hit || refresh;
    })
  );
});
