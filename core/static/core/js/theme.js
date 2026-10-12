/**
 * QCA Analytics — Quad-Theme & Continuous Display Engine
 * 4 time-of-day themes: Dawn · Day · Dusk · Night
 * Auto-selects based on local time, cycles on click, persists in localStorage.
 * Runs 24/7 with automatic shift/time transitions and full-screen enforcement.
 */

(function () {
    'use strict';

    // === THEME DEFINITIONS ===================================================
    const THEMES = [
        {
            name: "dawn",
            icon: "fas fa-cloud-sun",
            label: "Dawn — Warm Amber (click for Day)",
            timeRange: [5, 9],
        },
        {
            name: "day",
            icon: "fas fa-sun",
            label: "Day — Bright Light (click for Dusk)",
            timeRange: [9, 17],
        },
        {
            name: "dusk",
            icon: "fas fa-cloud-sun-rain",
            label: "Dusk — Warm Purple (click for Night)",
            timeRange: [17, 21],
        },
        {
            name: "night",
            icon: "fas fa-moon",
            label: "Night — Deep Dark (click for Dawn)",
            timeRange: [21, 5],
        },
    ];

    const THEME_NAMES = THEMES.map(t => t.name);
    const root = document.documentElement;

    // === AUTO-SELECT BY TIME OF DAY ==========================================
    function getAutoTheme() {
        const hour = new Date().getHours();
        for (const t of THEMES) {
            const [start, end] = t.timeRange;
            if (start < end) {
                if (hour >= start && hour < end) return t.name;
            } else {
                if (hour >= start || hour < end) return t.name;
            }
        }
        return "night";
    }

    // === APPLY THEME =========================================================
    function applyTheme(name, dispatch) {
        if (dispatch === undefined) dispatch = true;
        if (!THEME_NAMES.includes(name)) name = getAutoTheme();
        root.setAttribute("data-theme", name);
        localStorage.setItem("qca_theme", name);
        updateToggleBtn(name);
        if (dispatch) {
            window.dispatchEvent(new CustomEvent("themeChanged", { detail: { theme: name } }));
        }
    }

    // === CYCLE THEME =========================================================
    function cycleTheme() {
        const current = root.getAttribute("data-theme") || getAutoTheme();
        const idx = THEME_NAMES.indexOf(current);
        const next = THEME_NAMES[(idx + 1) % THEME_NAMES.length];
        localStorage.setItem("qca_theme_manual", "true");
        applyTheme(next, true);
    }

    // === UPDATE ALL THEME BUTTONS ============================================
    function updateToggleBtn(name) {
        document.querySelectorAll("#themeToggle, .theme-toggle, [data-theme-toggle]").forEach(function(btn) {
            var def = THEMES.find(function(t) { return t.name === name; }) || THEMES[3];
            var icon = btn.querySelector("i");
            if (icon) icon.className = def.icon;
            btn.setAttribute("title", def.label);
            btn.setAttribute("aria-label", def.label);
        });
    }

    // === INITIALIZE ==========================================================
    function init() {
        var isManual = localStorage.getItem("qca_theme_manual") === "true";
        var saved = localStorage.getItem("qca_theme") || localStorage.getItem("theme");
        // Migrate legacy theme keys
        if (saved === "default" || saved === "light") saved = "day";
        if (saved === "oled" || saved === "amoled" || saved === "dark") saved = "night";
        if (saved === "emerald") saved = "dawn";
        if (saved === "ocean") saved = "dusk";

        if (!isManual || !THEME_NAMES.includes(saved)) {
            saved = getAutoTheme();
        }
        applyTheme(saved, false);

        // Ensure root has fullscreen class for seamless viewport display
        root.classList.add("fullscreen-app");
    }

    // === 24/7 BACKGROUND TIME CHECK (Every 60s) ===============================
    setInterval(function() {
        if (localStorage.getItem("qca_theme_manual") !== "true") {
            var autoTheme = getAutoTheme();
            var current = root.getAttribute("data-theme");
            if (autoTheme !== current) {
                applyTheme(autoTheme, true);
            }
        }
    }, 60000);

    // === FULLSCREEN AUTO-ENFORCEMENT FOR ALL APPS =============================
    function enterFullscreen() {
        if (!document.fullscreenElement) {
            var docEl = document.documentElement;
            var rfs = docEl.requestFullscreen || docEl.webkitRequestFullscreen || docEl.msRequestFullscreen;
            if (rfs) {
                rfs.call(docEl).catch(function () {});
            }
        }
    }

    // Enter fullscreen on first user touch / click / keypress anywhere
    window.addEventListener("click", enterFullscreen, { passive: true });
    window.addEventListener("keydown", enterFullscreen, { passive: true });
    window.addEventListener("touchstart", enterFullscreen, { passive: true });

    // === WIRE BUTTONS ========================================================
    function wireButtons() {
        document.querySelectorAll("#themeToggle, .theme-toggle, [data-theme-toggle]").forEach(function(btn) {
            var fresh = btn.cloneNode(true);
            btn.parentNode.replaceChild(fresh, btn);
            fresh.addEventListener("click", function(e) {
                e.preventDefault();
                cycleTheme();
            });
        });
        updateToggleBtn(root.getAttribute("data-theme") || getAutoTheme());
    }

    // Apply immediately to prevent FOUC
    init();

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", wireButtons);
    } else {
        wireButtons();
    }

    // === GLOBAL API ==========================================================
    window.ThemeEngine = {
        set: function(name) {
            localStorage.setItem("qca_theme_manual", "true");
            applyTheme(name, true);
        },
        cycle: cycleTheme,
        get: function() { return root.getAttribute("data-theme") || getAutoTheme(); },
        list: function() { return THEME_NAMES.slice(); },
        auto: getAutoTheme,
        resetAuto: function() {
            localStorage.removeItem("qca_theme_manual");
            applyTheme(getAutoTheme(), true);
        },
        toggle: cycleTheme,
        enterFullscreen: enterFullscreen,
    };

})();