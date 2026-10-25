(function () {
    "use strict";

    if (window.__QAD_LIVE_UPDATES__) return;
    window.__QAD_LIVE_UPDATES__ = true;

    const requestedPlant = document.body.dataset.plantId || new URLSearchParams(location.search).get("plant") || document.querySelector(".notification-container")?.dataset.plantId || "";
    const plantId = ["all", "*"].includes(String(requestedPlant).toLowerCase()) ? "" : requestedPlant;
    const firstSegment = location.pathname.split("/").filter(Boolean)[0] || "";
    const appLabel = firstSegment === "qca" ? "qc_analytics" : firstSegment;
    let socket = null;
    let reconnectTimer = null;
    let reconnectDelay = 1000;
    let refreshTimer = null;
    let fallbackTimer = null;
    let queuedRefresh = false;
    let submitting = false;
    let hasConnected = false;
    let reconnecting = false;

    function isDirty() {
        return Array.from(document.querySelectorAll("form")).some(form => {
            return Array.from(form.elements || []).some(field => {
                if (!field.name || field.disabled) return false;
                if (field.type === "checkbox" || field.type === "radio") return field.checked !== field.defaultChecked;
                if (field.tagName === "SELECT") return Array.from(field.options).some(option => option.selected !== option.defaultSelected);
                if (field.type === "file") return Boolean(field.files && field.files.length);
                return typeof field.defaultValue === "string" && field.value !== field.defaultValue;
            });
        });
    }

    function refreshPage(ignoreDirty = false) {
        if (document.hidden || (!ignoreDirty && isDirty()) || submitting) {
            queuedRefresh = true;
            return;
        }
        queuedRefresh = false;
        if (window.AutoUpdate && document.querySelector("[data-auto-update-url]")) {
            window.AutoUpdate.refresh();
            return;
        }
        window.location.reload();
    }

    function handleChange(data) {
        if (!data || data.type !== "data.changed") return;
        if (data.plant_id && plantId && String(data.plant_id) !== String(plantId)) return;

        const event = new CustomEvent("qad:data-changed", { detail: data, cancelable: true });
        window.dispatchEvent(event);

        if (window.GlobalNotifications && typeof window.GlobalNotifications.scheduleRefresh === "function") {
            window.GlobalNotifications.scheduleRefresh();
        }

        // A dashboard widget may claim and refresh its own data without a page reload.
        if (event.defaultPrevented) return;
        clearTimeout(refreshTimer);
        refreshTimer = window.setTimeout(refreshPage, 180);
    }

    function connect() {
        if (document.hidden || !window.WebSocket) return;
        clearTimeout(reconnectTimer);
        const scheme = location.protocol === "https:" ? "wss:" : "ws:";
        const url = new URL(`${scheme}//${location.host}/ws/live/`);
        if (appLabel) url.searchParams.set("app", appLabel);
        if (plantId) url.searchParams.set("plant", plantId);

        try {
            socket = new WebSocket(url.toString());
        } catch (_) {
            scheduleReconnect();
            return;
        }

        socket.onopen = () => {
            reconnectDelay = 1000;
            if (hasConnected && reconnecting) {
                const resume = new CustomEvent("qad:resume", { cancelable: true });
                window.dispatchEvent(resume);
                if (!resume.defaultPrevented) refreshPage();
            }
            hasConnected = true;
            reconnecting = false;
        };
        socket.onmessage = message => {
            try { handleChange(JSON.parse(message.data)); } catch (_) { /* Ignore malformed frames. */ }
        };
        socket.onerror = () => { if (socket) socket.close(); };
        socket.onclose = () => {
            socket = null;
            if (hasConnected) reconnecting = true;
            scheduleReconnect();
        };
    }

    function scheduleReconnect() {
        if (document.hidden || !navigator.onLine) return;
        clearTimeout(reconnectTimer);
        reconnectTimer = window.setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    }

    fallbackTimer = window.setInterval(() => {
        if (navigator.onLine && (!window.WebSocket || !socket || socket.readyState !== window.WebSocket.OPEN)) refreshPage();
    }, 30000);

    document.addEventListener("submit", () => {
        submitting = true;
        window.setTimeout(() => {
            submitting = false;
            if (queuedRefresh) refreshPage(true);
        }, 1800);
    }, true);

    document.addEventListener("focusout", () => {
        if (queuedRefresh) window.setTimeout(() => { if (!isDirty()) refreshPage(); }, 150);
    }, true);
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            if (socket) socket.close();
            return;
        }
        if (queuedRefresh) {
            refreshPage();
        } else {
            const resume = new CustomEvent("qad:resume", { cancelable: true });
            window.dispatchEvent(resume);
            if (!resume.defaultPrevented) refreshPage();
        }
        if (!socket) connect();
    });
    window.addEventListener("online", () => { if (!socket) connect(); });
    window.addEventListener("qad:data-changed", event => {
        if (event.detail && window.GlobalNotifications) window.GlobalNotifications.scheduleRefresh();
    });

    connect();
})();
