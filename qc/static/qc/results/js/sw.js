// qc/static/qc/results/js/sw.js
// ──────────────────────────────────────────────────────────────
// QC Analytics Progressive Web App Service Worker
// ──────────────────────────────────────────────────────────────

const CACHE_NAME = "qca-shell-v2";
const STATIC_ASSETS = [
    "/static/qc/results/css/dashboard_v2.css",
    "/static/qc/results/css/excell.css",
    "/static/qc/results/js/result_card.js",
    "/static/core/css/theme.css",
    "/static/core/js/theme.js",
    "/static/ca/js/htmx.js",
    "/static/qc/results/manifest.json"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS).catch((err) => {
                console.warn("[QCA SW] Static asset caching partial:", err);
            });
        }).then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Skip non-GET and websocket connections
    if (request.method !== "GET" || url.pathname.startsWith("/ws/")) {
        return;
    }

    // Static assets: cache-first
    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.match(request).then((cached) => {
                if (cached) return cached;
                return fetch(request).then((response) => {
                    if (response && response.status === 200) {
                        const copy = response.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                    }
                    return response;
                });
            })
        );
        return;
    }

    // HTML & Dynamic API: network-first with cache fallback
    event.respondWith(
        fetch(request)
            .then((response) => {
                if (response && response.status === 200 && response.type === "basic") {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                }
                return response;
            })
            .catch(() => {
                return caches.match(request);
            })
    );
});
