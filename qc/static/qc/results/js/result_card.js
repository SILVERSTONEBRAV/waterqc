// static/qc/results/js/result_card.js

(() => {
    "use strict";

    if (window.__QC_RESULTS_INITIALIZED__) return;
    window.__QC_RESULTS_INITIALIZED__ = true;

    const WS_PREFIX = "[QC WS]";
    const MAX_RECONNECT_DELAY = 30000;
    const INITIAL_RECONNECT_DELAY = 1000;
    const REFRESH_DEBOUNCE = 150;

    let socket = null;
    let reconnectAttempts = 0;
    let reconnectTimer = null;
    let refreshTimer = null;

    let busy = false;
    let editing = false;
    let queued = false;
    let shuttingDown = false;

    function log(...args) { console.log(WS_PREFIX, ...args); }
    function warn(...args) { console.warn(WS_PREFIX, ...args); }
    function error(...args) { console.error(WS_PREFIX, ...args); }

    function hasHTMX() { return typeof window.htmx !== "undefined"; }
    function getContainer() { return document.getElementById("cards-container"); }

    function buildRefreshUrl() {
        const url = new URL(window.location.href);
        url.searchParams.set("partial", "cards");
        return `${url.pathname}${url.search}`;
    }

    function scheduleRefresh() {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(() => refreshCards(), REFRESH_DEBOUNCE);
    }

    function refreshCards(force = false) {
        if (!hasHTMX()) { warn("HTMX not available."); return; }
        const container = getContainer();
        if (!container) { warn("cards-container not found."); return; }
        if (document.hidden && !force) { queued = true; return; }
        if ((busy || editing) && !force) { queued = true; return; }

        busy = true;
        queued = false;
        log("Refreshing cards...");

        htmx.ajax("GET", buildRefreshUrl(), {
            target: "#cards-container",
            swap: "outerHTML"
        });
    }

    function connect() {
        if (shuttingDown) return;
        if (socket) {
            socket.onclose = null;
            socket.close();
            socket = null;
        }
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const wsUrl = `${protocol}://${window.location.host}/ws/qc/dashboard/`;
        log("Connecting:", wsUrl);

        socket = new WebSocket(wsUrl);

        socket.onopen = () => { reconnectAttempts = 0; log("Connected."); };
        socket.onmessage = event => {
            let data;
            try { data = JSON.parse(event.data); }
            catch (err) { error("Invalid websocket payload.", err); return; }
            log("Received:", data);
            switch (data.type) {
                case "connection.ready": log("Ready."); break;
                case "analysis.created":
                case "results.updated":
                case "dashboard.refresh": scheduleRefresh(); break;
                default: log("Ignored:", data.type);
            }
        };
        socket.onerror = event => { error("Socket error.", event); };
        socket.onclose = event => {
            socket = null;
            if (shuttingDown) return;
            warn(`Disconnected (${event.code}).`);
            reconnect();
        };
    }

    function reconnect() {
        clearTimeout(reconnectTimer);
        reconnectAttempts++;
        const delay = Math.min(INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
        warn(`Reconnect in ${delay} ms`);
        reconnectTimer = setTimeout(connect, delay);
    }

    // HTMX lifecycle hooks
    document.body.addEventListener("htmx:beforeRequest", e => {
        if (e.detail.target?.id === "cards-container") busy = true;
    });

    document.body.addEventListener("htmx:afterSwap", e => {
        if (e.target.id !== "cards-container") return;
        busy = false;
        log("Cards refreshed.");
        if (queued && !editing) { queued = false; scheduleRefresh(); }
        initCardConfig();       // re‑init validation
        applyWaterTypeThemes(); // re‑apply background themes
        animateCards();         // fade‑in animation
    });

    document.body.addEventListener("htmx:responseError", e => {
        if (e.detail.target?.id === "cards-container") busy = false;
    });

    document.addEventListener("focusin", e => {
        if (e.target.closest("#cards-container input")) editing = true;
    });

    document.addEventListener("focusout", e => {
        if (!e.target.closest("#cards-container input")) return;
        editing = false;
        if (queued && !busy) { queued = false; scheduleRefresh(); }
    });

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && queued && !busy && !editing) {
            queued = false;
            scheduleRefresh();
        }
    });

    window.addEventListener("beforeunload", () => {
        shuttingDown = true;
        clearTimeout(reconnectTimer);
        clearTimeout(refreshTimer);
        if (socket) {
            socket.onclose = null;
            socket.close();
            socket = null;
        }
    });

    document.addEventListener("DOMContentLoaded", () => {
        const plantId = document.body.dataset.plantId;
        if (!plantId) { warn("No plant ID. WebSocket disabled."); return; }
        if (!hasHTMX()) { error("HTMX is required."); return; }
        connect();
        initCardConfig();
        applyWaterTypeThemes();
        animateCards();
    });

    /* ================================
       Spec Visibility Logic
       ================================ */
    function initCardConfig() {
        const inputs = document.querySelectorAll("#cards-container .form-control");
        inputs.forEach(input => {
            input.addEventListener("input", () => handleValidation(input));
            input.addEventListener("blur", () => handleValidation(input));
        });
    }

    function handleValidation(input) {
        const spec = input.nextElementSibling;
        if (!spec || !spec.classList.contains("spec-text")) return;

        const value = parseFloat(input.value);
        const specText = spec.textContent || "";
        const limits = parseSpec(specText);

        if (isNaN(value) || !limits) {
            hideSpec(input, spec);
            return;
        }
        if (value < limits.min || value > limits.max) {
            showSpec(input, spec);
        } else {
            hideSpec(input, spec);
        }
    }

    function parseSpec(text) {
        const match = text.match(/(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)/);
        return match ? { min: parseFloat(match[1]), max: parseFloat(match[2]) } : null;
    }

    function showSpec(input, spec) {
        input.classList.add("form-control-danger");
        spec.style.display = "block";
        spec.style.color = "var(--danger-700)";
        spec.style.transition = "opacity 0.3s ease";
        spec.style.opacity = "1";
    }

    function hideSpec(input, spec) {
        input.classList.remove("form-control-danger");
        spec.style.transition = "opacity 0.3s ease";
        spec.style.opacity = "0";
        setTimeout(() => { spec.style.display = "none"; }, 300);
    }

    /* ================================
       Water Type Themes
       ================================ */
    function applyWaterTypeThemes() {
        const cards = document.querySelectorAll("#cards-container .card");
        cards.forEach(card => {
            const type = card.dataset.waterType?.toLowerCase() || "";
            switch (type) {
                case "raw":
                    card.style.background = "linear-gradient(135deg, #2c3e50, #34495e)";
                    break;
                case "treated":
                    card.style.background = "linear-gradient(135deg, #1e3c72, #2a5298)";
                    break;
                case "recycled":
                    card.style.background = "linear-gradient(135deg, #0f2027, #203a43, #2c5364)";
                    break;
                case "potable":
                    card.style.background = "linear-gradient(135deg, #283e51, #485563)";
                    break;
                default:
                    card.style.background = "linear-gradient(135deg, #3c4a57, #5a6a7f)";
            }
            card.style.color = "#f0f4f8";
            card.style.borderRadius = "12px";
            card.style.boxShadow = "0 4px 12px rgba(0,0,0,0.4)";
        });
    }

    /* ================================
       Advanced Enhancements
       ================================ */
    function animateCards() {
        const cards = document.querySelectorAll("#cards-container .card");
        cards.forEach((card, i) => {
            card.style.opacity = 0;
            setTimeout(() => {
                card.style.transition = "opacity 0.6s ease, transform 0.6s ease";
                card.style.opacity = 1;
                card.style.transform = "translateY(0)";
            }, i * 120);
        });
    }

})();
