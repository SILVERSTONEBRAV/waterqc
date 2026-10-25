/* Plant-scoped invalidation socket for the shared notification bell. */
(function () {
    "use strict";

    if (window.__QAD_NOTIFICATION_UPDATES__) return;
    window.__QAD_NOTIFICATION_UPDATES__ = true;

    const container = document.querySelector(".notification-container");
    if (!container || !window.WebSocket) return;

    const plantId = container.dataset.plantId || document.body.dataset.plantId ||
        new URLSearchParams(window.location.search).get("plant") || "";
    // A superuser with no active plant has an intentionally empty inbox.
    if (!plantId || ["all", "none", "*"].includes(String(plantId).toLowerCase())) return;

    let socket = null;
    let retryTimer = null;
    let retryDelay = 1000;
    let stopped = false;

    function refreshFeed() {
        if (window.GlobalNotifications?.scheduleRefresh) {
            window.GlobalNotifications.scheduleRefresh();
        }
    }

    function connect() {
        if (stopped || document.hidden || !navigator.onLine) return;
        clearTimeout(retryTimer);
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const url = new URL(`${protocol}//${window.location.host}/ws/live/`);
        url.searchParams.set("plant", plantId);

        try {
            socket = new WebSocket(url.toString());
        } catch (_) {
            scheduleReconnect();
            return;
        }

        socket.onopen = () => {
            retryDelay = 1000;
        };
        socket.onmessage = event => {
            let data;
            try { data = JSON.parse(event.data); } catch (_) { return; }
            if (data.type === "connection.ready") {
                refreshFeed();
                return;
            }
            if (
                data.type === "data.changed" &&
                (!data.plant_id || String(data.plant_id) === String(plantId)) &&
                ["ca", "alerts", "qc"].includes(String(data.app_label || ""))
            ) {
                refreshFeed();
            }
        };
        socket.onerror = () => socket?.close();
        socket.onclose = () => {
            socket = null;
            scheduleReconnect();
        };
    }

    function scheduleReconnect() {
        if (stopped || document.hidden || !navigator.onLine) return;
        clearTimeout(retryTimer);
        retryTimer = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30000);
    }

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            if (socket) socket.close();
            return;
        }
        refreshFeed();
        if (!socket) connect();
    });
    window.addEventListener("online", () => { if (!socket) connect(); });
    window.addEventListener("pageshow", refreshFeed);
    window.addEventListener("beforeunload", () => {
        stopped = true;
        clearTimeout(retryTimer);
        if (socket) socket.close();
    }, { once: true });

    connect();
})();
