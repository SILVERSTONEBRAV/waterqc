"use strict";

/* ============================================================
 * HTMX ENTERPRISE ENGINE (Django + SPA Hybrid)
 * ============================================================ */

const HTMXEngine = (() => {

    /* ===================== CONFIG ===================== */
    const config = {
        indicators: {
            global: "#global-loader",
        },
        classes: {
            loading: "htmx-loading",
            swapping: "htmx-swapping",
        },
        retry: {
            attempts: 2,
            delay: 800
        }
    };

    /* ===================== STATE ===================== */
    const state = {
        activeRequests: 0,
        retryMap: new Map(),
    };

    /* ===================== UTILITIES ===================== */

    const getCSRF = () =>
        document.cookie.split("; ")
            .find(c => c.startsWith("csrftoken="))
            ?.split("=")[1] || "";

    const log = (...args) => console.log("[HTMX]", ...args);

    const showGlobalLoader = () => {
        const el = document.querySelector(config.indicators.global);
        if (el) el.style.display = "block";
    };

    const hideGlobalLoader = () => {
        const el = document.querySelector(config.indicators.global);
        if (el) el.style.display = "none";
    };

    const addLoadingState = (el) => {
        el?.classList.add(config.classes.loading);
    };

    const removeLoadingState = (el) => {
        el?.classList.remove(config.classes.loading);
    };

    const toast = (msg, type = "info") => {
        if (window.Dashboard?.toast) {
            Dashboard.toast(msg, type);
        } else {
            console.log(`[${type.toUpperCase()}]`, msg);
        }
    };

    /* ===================== CSRF INJECTION ===================== */

    const attachCSRF = () => {
        document.body.addEventListener("htmx:configRequest", (e) => {
            e.detail.headers["X-CSRFToken"] = getCSRF();
            e.detail.headers["X-Requested-With"] = "XMLHttpRequest";
        });
    };

    /* ===================== REQUEST LIFECYCLE ===================== */

    const bindLifecycle = () => {

        document.body.addEventListener("htmx:beforeRequest", (e) => {
            state.activeRequests++;
            showGlobalLoader();

            addLoadingState(e.target);

            log("Request started:", e.detail.pathInfo?.requestPath);
        });

        document.body.addEventListener("htmx:afterRequest", (e) => {
            state.activeRequests--;

            if (state.activeRequests <= 0) {
                hideGlobalLoader();
                state.activeRequests = 0;
            }

            removeLoadingState(e.target);

            log("Request completed");
        });

        document.body.addEventListener("htmx:beforeSwap", (e) => {
            e.target.classList.add(config.classes.swapping);
        });

        document.body.addEventListener("htmx:afterSwap", (e) => {
            e.target.classList.remove(config.classes.swapping);

            rehydrate(e.target);
        });

        document.body.addEventListener("htmx:afterSettle", () => {
            rehydrate(document.body);
        });
    };

    /* ===================== ERROR HANDLING ===================== */

    const bindErrors = () => {

        document.body.addEventListener("htmx:responseError", (e) => {
            const status = e.detail.xhr.status;

            if (status === 403) {
                toast("Session expired. Reloading...", "warning");
                setTimeout(() => location.reload(), 1500);
                return;
            }

            if (status >= 500) {
                toast("Server error. Please try again.", "danger");
                return;
            }

            toast("Request failed", "danger");
        });

        document.body.addEventListener("htmx:sendError", () => {
            toast("Network error. Check connection.", "danger");
        });
    };

    /* ===================== RETRY LOGIC ===================== */

    const bindRetry = () => {

        document.body.addEventListener("htmx:responseError", (e) => {
            const el = e.target;
            const key = el.getAttribute("hx-get") || el.getAttribute("hx-post");

            if (!key) return;

            const attempts = state.retryMap.get(key) || 0;

            if (attempts >= config.retry.attempts) return;

            state.retryMap.set(key, attempts + 1);

            setTimeout(() => {
                log("Retrying:", key);
                htmx.trigger(el, "retry");
            }, config.retry.delay);
        });
    };

    /* ===================== REHYDRATION ===================== */
    /* Re-bind JS after HTMX swap */

    const rehydrate = (root) => {

        // Re-init dashboard widgets
        if (window.Dashboard) {
            Dashboard.init?.();
        }

        // Re-bind tab clicks if injected dynamically
        root.querySelectorAll("[data-tab]").forEach(btn => {
            btn.addEventListener("click", e => {
                e.preventDefault();
                Dashboard.loadTab(btn.dataset.tab);
            });
        });

        // Re-bind filters
        root.querySelectorAll("[data-filter]").forEach(input => {
            input.addEventListener("change", () => {
                triggerFilterEvent();
            });
        });

        // Attach tooltips if bootstrap present
        if (window.bootstrap) {
            root.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
                new bootstrap.Tooltip(el);
            });
        }
    };

    /* ===================== FILTER BRIDGE ===================== */

    const triggerFilterEvent = () => {

        const payload = {
            search: document.querySelector("[data-filter='search']")?.value || "",
            type: document.querySelector("[data-filter='type']")?.value || "",
            start: document.querySelector("[data-filter='start']")?.value || "",
            end: document.querySelector("[data-filter='end']")?.value || "",
            status: Array.from(document.querySelectorAll("[data-filter='status']:checked"))
                .map(el => el.value)
        };

        document.dispatchEvent(new CustomEvent("dashboard:filter", {
            detail: payload
        }));
    };

    /* ===================== INLINE LOADING STATES ===================== */

    const bindIndicators = () => {
        document.body.addEventListener("htmx:beforeRequest", (e) => {
            const indicator = e.target.querySelector(".htmx-indicator");
            if (indicator) indicator.style.display = "inline-block";
        });

        document.body.addEventListener("htmx:afterRequest", (e) => {
            const indicator = e.target.querySelector(".htmx-indicator");
            if (indicator) indicator.style.display = "none";
        });
    };

    /* ===================== SWAP ANIMATION ===================== */

    const bindTransitions = () => {
        document.body.addEventListener("htmx:beforeSwap", (e) => {
            e.target.style.opacity = "0.4";
        });

        document.body.addEventListener("htmx:afterSwap", (e) => {
            e.target.style.opacity = "1";
        });
    };

    /* ===================== CUSTOM EVENTS ===================== */

    const bindCustomEvents = () => {

        // Trigger manual refresh
        document.addEventListener("dashboard:refresh", () => {
            log("Manual refresh triggered");
            htmx.trigger("#dashboard-stats", "refresh");
        });

        // Trigger reload on external updates
        document.addEventListener("dashboard:reload-tab", (e) => {
            if (window.Dashboard?.loadTab) {
                Dashboard.loadTab(e.detail.tab);
            }
        });

    };

    /* ===================== INIT ===================== */

    const init = () => {
        if (!window.htmx) {
            console.warn("HTMX not found.");
            return;
        }

        attachCSRF();
        bindLifecycle();
        bindErrors();
        bindRetry();
        bindIndicators();
        bindTransitions();
        bindCustomEvents();

        log("HTMX Engine initialized");
    };

    return { init };

})();


/* ===================== AUTO INIT ===================== */
document.addEventListener("DOMContentLoaded", () => {
    HTMXEngine.init();
});
