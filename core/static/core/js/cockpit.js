/* =========================================================
   QAD COCKPIT — Shared Chart & Telemetry Engine
   Reused by all advanced dashboards
   ========================================================= */
(function () {
    "use strict";

    const QADCockpit = window.QADCockpit || {};

    /* ── colour palettes ── */
    QADCockpit.PALETTE = {
        cyan:    { bg: "rgba(56,189,248,0.15)", border: "#38bdf8", solid: "#0ea5e9" },
        emerald: { bg: "rgba(16,185,129,0.15)", border: "#34d399", solid: "#059669" },
        amber:   { bg: "rgba(245,158,11,0.15)", border: "#fbbf24", solid: "#d97706" },
        rose:    { bg: "rgba(244,63,94,0.15)",  border: "#fb7185", solid: "#e11d48" },
        purple:  { bg: "rgba(168,85,247,0.15)", border: "#c084fc", solid: "#7c3aed" },
        blue:    { bg: "rgba(59,130,246,0.15)",  border: "#60a5fa", solid: "#3b82f6" },
        slate:   { bg: "rgba(100,116,139,0.15)", border: "#94a3b8", solid: "#64748b" },
    };

    QADCockpit.COLORS = Object.values(QADCockpit.PALETTE);

    /* ── default chart options ── */
    QADCockpit.defaultOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600, easing: "easeOutQuart" },
        plugins: {
            legend: {
                display: true,
                position: "bottom",
                labels: {
                    color: "#94a3b8",
                    font: { size: 10, family: "'Plus Jakarta Sans', sans-serif" },
                    boxWidth: 10,
                    padding: 8,
                },
            },
            tooltip: {
                backgroundColor: "rgba(15,23,42,0.92)",
                titleColor: "#f8fafc",
                bodyColor: "#cbd5e1",
                borderColor: "rgba(56,189,248,0.3)",
                borderWidth: 1,
                cornerRadius: 6,
                padding: 8,
                titleFont: { size: 11, weight: "600" },
                bodyFont: { size: 10 },
            },
        },
        scales: {
            x: {
                ticks: { color: "#64748b", font: { size: 9 } },
                grid: { color: "rgba(51,65,85,0.25)" },
                border: { color: "rgba(51,65,85,0.35)" },
            },
            y: {
                ticks: { color: "#64748b", font: { size: 9 } },
                grid: { color: "rgba(51,65,85,0.2)" },
                border: { display: false },
            },
        },
    };

    /* ── render doughnut ── */
    QADCockpit.doughnut = function (canvasId, labels, data, colorKeys) {
        const el = document.getElementById(canvasId);
        if (!el) return null;
        const ctx = el.getContext("2d");
        const colors = (colorKeys || Object.keys(QADCockpit.PALETTE)).map(
            (k) => QADCockpit.PALETTE[k] || QADCockpit.PALETTE.slate
        );
        return new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: colors.map((c) => c.bg),
                    borderColor: colors.map((c) => c.border),
                    borderWidth: 1.5,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "70%",
                plugins: {
                    legend: QADCockpit.defaultOptions.plugins.legend,
                    tooltip: QADCockpit.defaultOptions.plugins.tooltip,
                },
                animation: { animateRotate: true, duration: 800 },
            },
        });
    };

    /* ── render bar chart ── */
    QADCockpit.bar = function (canvasId, labels, datasets) {
        const el = document.getElementById(canvasId);
        if (!el) return null;
        const ctx = el.getContext("2d");
        return new Chart(ctx, {
            type: "bar",
            data: { labels: labels, datasets: datasets },
            options: {
                ...QADCockpit.defaultOptions,
                scales: {
                    ...QADCockpit.defaultOptions.scales,
                    x: { ...QADCockpit.defaultOptions.scales.x, stacked: false },
                },
                plugins: {
                    ...QADCockpit.defaultOptions.plugins,
                    legend: { ...QADCockpit.defaultOptions.plugins.legend, display: datasets.length > 1 },
                },
            },
        });
    };

    /* ── render line chart ── */
    QADCockpit.line = function (canvasId, labels, datasets) {
        const el = document.getElementById(canvasId);
        if (!el) return null;
        const ctx = el.getContext("2d");
        return new Chart(ctx, {
            type: "line",
            data: { labels: labels, datasets: datasets },
            options: {
                ...QADCockpit.defaultOptions,
                elements: {
                    point: { radius: 2.5, hoverRadius: 5 },
                    line: { tension: 0.35, borderWidth: 2 },
                },
            },
        });
    };

    /* ── render horizontal bar ── */
    QADCockpit.horizontalBar = function (canvasId, labels, data, colorKey) {
        const el = document.getElementById(canvasId);
        if (!el) return null;
        const ctx = el.getContext("2d");
        const p = QADCockpit.PALETTE[colorKey || "cyan"];
        return new Chart(ctx, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: p.bg,
                    borderColor: p.border,
                    borderWidth: 1,
                }],
            },
            options: {
                ...QADCockpit.defaultOptions,
                indexAxis: "y",
                plugins: { ...QADCockpit.defaultOptions.plugins, legend: { display: false } },
            },
        });
    };

    /* ── build dataset helper ── */
    QADCockpit.dataset = function (label, data, colorKey, fill) {
        const p = QADCockpit.PALETTE[colorKey || "cyan"];
        return {
            label: label,
            data: data,
            backgroundColor: fill ? p.bg : "transparent",
            borderColor: p.border,
            borderWidth: 2,
            fill: !!fill,
            pointBackgroundColor: p.border,
        };
    };

    /* ── tab toggle ── */
    QADCockpit.initTabs = function () {
        document.querySelectorAll(".panel-tabs__tab").forEach(function (tab) {
            tab.addEventListener("click", function () {
                const panel = tab.closest(".panel");
                if (!panel) return;
                panel.querySelectorAll(".panel-tabs__tab").forEach((t) =>
                    t.classList.remove("panel-tabs__tab--active")
                );
                tab.classList.add("panel-tabs__tab--active");
                const target = tab.dataset.tab;
                panel.querySelectorAll(".panel-tab-content").forEach((c) =>
                    c.classList.toggle("panel-tab-content--active", c.dataset.tabContent === target)
                );
            });
        });
    };

    /* ── auto-refresh tick ── */
    QADCockpit.autoRefreshInterval = null;
    QADCockpit.startAutoRefresh = function (url, intervalMs) {
        if (QADCockpit.autoRefreshInterval) clearInterval(QADCockpit.autoRefreshInterval);
        QADCockpit.autoRefreshInterval = setInterval(function () {
            fetch(url, {
                headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                document.dispatchEvent(new CustomEvent("cockpit:refresh", { detail: data }));
            })
            .catch(function () {});
        }, intervalMs || 30000);
    };

    /* ── init on DOMContentLoaded ── */
    document.addEventListener("DOMContentLoaded", function () {
        QADCockpit.initTabs();
    });

    window.QADCockpit = QADCockpit;
})();
