"use strict";

/* ============================================================
 * ULTRA ENTERPRISE DASHBOARD ENGINE v2.0
 * (SPA + HTMX Hybrid + WebSocket + Virtualization + Caching)
 * ============================================================ */

const Dashboard = (() => {

    /* ============================================================
     * CONFIGURATION LAYER
     * ============================================================ */
    const config = {
        debug: true,

        selectors: {
            root: "#dashboard-container",
            statCards: "#dashboard-stats",
            tabNav: "#dashboard-tabs nav",
            tabContent: "#dashboard-tab-contents",
            batchContainer: "#batches-container",
            requestContainer: "#requests-container",
            notifications: "#dashboard-notifications",
        },

        endpoints: {
            dashboard: "/ca/dashboard/?format=json",
            tab: (id) => `/ca/dashboard/tab-content/${id}/`,
            batch: (id) => `/ca/dashboard/batch/${id}/progress/`,
            request: (id) => `/ca/dashboard/request/${id}/progress/`,
            export: "/ca/dashboard/export/",
        },

        timing: {
            refresh: 30000,
            poll: 4000,
            heartbeat: 15000,
        },

        websocket: {
            url: `ws://${window.location.host}/ws/dashboard/`,
            maxRetries: 10
        },

        cacheTTL: 15000,
        maxRows: 200,
    };

    /* ============================================================
     * GLOBAL STATE
     * ============================================================ */
    const state = {
        activeTab: null,
        ws: null,
        retryCount: 0,
        cache: new Map(),
        batchHistory: {},
        requestHistory: {},
        visible: true,
        initialized: false,
    };

    /* ============================================================
     * EVENT BUS (Decoupled Communication)
     * ============================================================ */
    const EventBus = {
        events: {},
        on(event, handler) {
            if (!this.events[event]) this.events[event] = [];
            this.events[event].push(handler);
        },
        emit(event, payload) {
            (this.events[event] || []).forEach(fn => fn(payload));
        }
    };

    /* ============================================================
     * LOGGER
     * ============================================================ */
    const log = (...args) => config.debug && console.log("[Dashboard]", ...args);

    /* ============================================================
     * CACHE SYSTEM (Stale-While-Revalidate)
     * ============================================================ */
    const cacheGet = (key) => {
        const entry = state.cache.get(key);
        if (!entry) return null;
        if (Date.now() - entry.timestamp > config.cacheTTL) return null;
        return entry.data;
    };

    const cacheSet = (key, data) => {
        state.cache.set(key, {
            data,
            timestamp: Date.now()
        });
    };

    /* ============================================================
     * NETWORK LAYER
     * ============================================================ */
    const fetchJSON = async (url, useCache = true) => {
        if (useCache) {
            const cached = cacheGet(url);
            if (cached) return cached;
        }

        try {
            const res = await fetch(url, {
                headers: { "X-Requested-With": "XMLHttpRequest" }
            });

            const json = await res.json();

            if (useCache) cacheSet(url, json);

            return json;

        } catch (err) {
            log("Fetch error:", err);
            return { success: false, error: err.message };
        }
    };

    /* ============================================================
     * DOM HELPERS
     * ============================================================ */
    const el = (tag, attrs = {}) => {
        const node = document.createElement(tag);
        Object.entries(attrs).forEach(([k, v]) => {
            if (k === "html") node.innerHTML = v;
            else if (k === "text") node.textContent = v;
            else node.setAttribute(k, v);
        });
        return node;
    };

    /* ============================================================
     * PERFORMANCE TRACKER
     * ============================================================ */
    const perf = {
        start(label) {
            performance.mark(label + "-start");
        },
        end(label) {
            performance.mark(label + "-end");
            performance.measure(label, label + "-start", label + "-end");
        }
    };

    /* ============================================================
     * UI RENDER ENGINE
     * ============================================================ */
    const UI = {

        renderCards(cards) {
            const container = document.querySelector(config.selectors.statCards);
            if (!container) return;

            container.innerHTML = "";

            cards.forEach(card => {
                const node = el("div", { class: "card stat-card" });
                node.dataset.type = card.type;

                node.innerHTML = `
                    <div class="card-body">
                        <h5>${card.label}</h5>
                        <h2>${card.value}</h2>
                        <small>${card.delta || ""}</small>
                    </div>
                `;

                container.appendChild(node);
            });
        },

        renderVirtualList(container, items, renderer) {
            container.innerHTML = "";

            const fragment = document.createDocumentFragment();
            items.slice(0, config.maxRows).forEach(item => {
                fragment.appendChild(renderer(item));
            });

            container.appendChild(fragment);
        },

        toast(msg, type = "success") {
            console.log(`[${type.toUpperCase()}] ${msg}`);
        }
    };

    /* ============================================================
     * DATA CONTROLLERS
     * ============================================================ */
    const DataController = {

        async loadDashboard() {
            perf.start("dashboard-load");

            const res = await fetchJSON(config.endpoints.dashboard);

            if (res.success !== false) {
                UI.renderCards(res.data.cards || []);
            }

            perf.end("dashboard-load");
        },

        async loadTab(tabId) {
            const container = document.querySelector(config.selectors.tabContent);
            if (!container) return;

            container.innerHTML = "Loading...";

            const res = await fetchJSON(config.endpoints.tab(tabId), false);

            if (res?.html) container.innerHTML = res.html;

            state.activeTab = tabId;
        }
    };

    /* ============================================================
     * WEBSOCKET ENGINE (Robust + Heartbeat)
     * ============================================================ */
    const WS = {

        connect() {
            state.ws = new WebSocket(config.websocket.url);

            state.ws.onopen = () => {
                log("WS connected");
                state.retryCount = 0;
                WS.heartbeat();
            };

            state.ws.onmessage = (e) => {
                const msg = JSON.parse(e.data);
                WS.handle(msg);
            };

            state.ws.onclose = () => WS.reconnect();
        },

        heartbeat() {
            setInterval(() => {
                if (state.ws?.readyState === 1) {
                    state.ws.send(JSON.stringify({ type: "ping" }));
                }
            }, config.timing.heartbeat);
        },

        reconnect() {
            if (state.retryCount >= config.websocket.maxRetries) return;

            state.retryCount++;
            setTimeout(WS.connect, state.retryCount * 2000);
        },

        handle(msg) {
            switch (msg.type) {
                case "dashboard_update":
                    UI.renderCards(msg.data.cards);
                    break;

                case "batch_update":
                    EventBus.emit("batch:update", msg.data);
                    break;

                case "request_update":
                    EventBus.emit("request:update", msg.data);
                    break;

                default:
                    log("Unknown WS event:", msg);
            }
        }
    };

    /* ============================================================
     * POLLING FALLBACK
     * ============================================================ */
    const Polling = {

        start() {
            setInterval(() => {
                if (!state.visible) return;

                DataController.loadDashboard();

            }, config.timing.refresh);
        }
    };

    /* ============================================================
     * VISIBILITY HANDLER (PERFORMANCE BOOST)
     * ============================================================ */
    const Visibility = {

        init() {
            document.addEventListener("visibilitychange", () => {
                state.visible = !document.hidden;
                log("Visibility:", state.visible);
            });
        }
    };

    /* ============================================================
     * TABS SYSTEM
     * ============================================================ */
    const Tabs = {

        init() {
            const nav = document.querySelector(config.selectors.tabNav);
            if (!nav) return;

            nav.addEventListener("click", (e) => {
                const btn = e.target.closest("[data-tab]");
                if (!btn) return;

                e.preventDefault();

                nav.querySelectorAll("[data-tab]").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");

                DataController.loadTab(btn.dataset.tab);
            });
        }
    };

    /* ============================================================
     * FILTER ENGINE (Advanced)
     * ============================================================ */
    const Filters = (() => {

        let stateFilter = {
            search: "",
            status: [],
        };

        const apply = () => {
            document.querySelectorAll(".stat-card").forEach(card => {
                const text = card.textContent.toLowerCase();

                const visible = text.includes(stateFilter.search.toLowerCase());
                card.style.display = visible ? "" : "none";
            });
        };

        return {
            update(filters) {
                stateFilter = { ...stateFilter, ...filters };
                apply();
            }
        };

    })();

    /* ============================================================
     * EXPORT ENGINE
     * ============================================================ */
    const Exporter = {

        async export(format = "csv") {
            const res = await fetchJSON(config.endpoints.export, false);

            if (res.url) {
                const a = document.createElement("a");
                a.href = res.url;
                a.download = `dashboard.${format}`;
                a.click();
            }
        }
    };

    /* ============================================================
     * INITIALIZER
     * ============================================================ */
    const init = () => {
        if (state.initialized) return;

        log("Initializing dashboard...");

        Tabs.init();
        Visibility.init();
        WS.connect();
        Polling.start();

        DataController.loadDashboard();

        state.initialized = true;
    };

    return {
        init,
        loadTab: DataController.loadTab,
        export: Exporter.export,
        filter: Filters.update
    };

})();

/* ============================================================
 * BOOTSTRAP
 * ============================================================ */
document.addEventListener("DOMContentLoaded", () => {
    Dashboard.init();
});
