(function () {
    function readJson(id) {
        const node = document.getElementById(id);
        if (!node) return null;
        try { return JSON.parse(node.textContent); } catch (_) { return null; }
    }

    function tooltipController() {
        const popup = document.createElement("div");
        popup.className = "fw-global-tooltip";
        popup.setAttribute("role", "tooltip");
        popup.hidden = true;
        document.body.appendChild(popup);
        let activeCard = null;
        let hideTimer = null;

        function position() {
            if (!activeCard || popup.hidden) return;
            const rect = activeCard.getBoundingClientRect();
            const margin = 12;
            const bounds = popup.getBoundingClientRect();
            const left = Math.min(Math.max(margin, rect.left), window.innerWidth - bounds.width - margin);
            let top = rect.bottom + 8;
            if (top + bounds.height > window.innerHeight - margin) top = rect.top - bounds.height - 8;
            top = Math.max(margin, Math.min(top, window.innerHeight - bounds.height - margin));
            popup.style.left = `${left}px`;
            popup.style.top = `${top}px`;
        }

        function show(card) {
            const source = card.querySelector(".fw-filter-tooltip");
            if (!source) return;
            activeCard = card;
            popup.innerHTML = source.innerHTML;
            popup.hidden = false;
            card.setAttribute("aria-describedby", `${source.id}-popup`);
            popup.id = `${source.id}-popup`;
            requestAnimationFrame(position);
        }

        function hide(card) {
            if (card && card.contains(document.activeElement)) return;
            if (activeCard) {
                const source = activeCard.querySelector(".fw-filter-tooltip");
                if (source) activeCard.setAttribute("aria-describedby", source.id);
            }
            activeCard = null;
            popup.hidden = true;
        }

        function scheduleHide(card) {
            window.clearTimeout(hideTimer);
            hideTimer = window.setTimeout(() => {
                if (popup.matches(":hover") || (card && card.contains(document.activeElement))) return;
                hide(card);
            }, 140);
        }

        popup.addEventListener("pointerenter", () => window.clearTimeout(hideTimer));
        popup.addEventListener("pointerleave", () => scheduleHide(activeCard));

        document.querySelectorAll("[data-filter-card]").forEach((card) => {
            card.addEventListener("pointerenter", () => show(card));
            card.addEventListener("pointerleave", () => scheduleHide(card));
            card.addEventListener("focus", () => show(card));
            card.addEventListener("blur", () => hide(card));
        });
        window.addEventListener("resize", position, { passive: true });
        window.addEventListener("scroll", position, { passive: true, capture: true });
    }

    function buildCharts() {
        if (typeof Chart === "undefined") return;
        const payload = readJson("filtered-water-dashboard-data");
        if (!payload) return;
        Chart.defaults.color = "#8da5b8";
        Chart.defaults.font.family = 'Inter, "Segoe UI", sans-serif';
        Chart.defaults.font.size = 10;

        const trendNode = document.getElementById("fwResultTrend");
        if (trendNode) {
            const data = payload.daily_results;
            new Chart(trendNode, {
                type: "line",
                data: {
                    labels: data.labels,
                    datasets: [
                        { label: "Within healthy margin", data: data.within, borderColor: "#40e0ad", backgroundColor: "rgba(64,224,173,.1)", fill: true, tension: .3, pointRadius: 0, borderWidth: 2 },
                        { label: "Near limit", data: data.near, borderColor: "#ffb454", backgroundColor: "rgba(255,180,84,.08)", fill: false, tension: .3, pointRadius: 0, borderWidth: 1.5 },
                        { label: "Out of range", data: data.out, borderColor: "#ff5d70", backgroundColor: "rgba(255,93,112,.08)", fill: false, tension: .25, pointRadius: 0, borderWidth: 1.5 },
                        { label: "No configured limit", data: data.unknown, borderColor: "#8795a5", backgroundColor: "rgba(135,149,165,.05)", fill: false, tension: .2, pointRadius: 0, borderWidth: 1, borderDash: [4, 3] }
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
                    plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 6, padding: 10 } }, tooltip: { backgroundColor: "#081626", borderColor: "rgba(93,190,215,.3)", borderWidth: 1 } },
                    scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 7, maxRotation: 0 } }, y: { beginAtZero: true, grid: { color: "rgba(131,163,184,.1)" }, ticks: { precision: 0 } } }
                }
            });
        }

        const healthNode = document.getElementById("fwHealthChart");
        if (healthNode) {
            new Chart(healthNode, {
                type: "doughnut",
                data: { labels: payload.filter_health.labels, datasets: [{ data: payload.filter_health.data, backgroundColor: ["#40e0ad", "#ffb454", "#ff5d70"], borderColor: "#0b1727", borderWidth: 4, hoverOffset: 7 }] },
                options: { responsive: true, maintainAspectRatio: false, cutout: "72%", plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 6, padding: 10 } } } }
            });
        }

        const parameterNode = document.getElementById("fwParameterChart");
        if (parameterNode) {
            const rows = payload.parameter_performance.slice(0, 12).reverse();
            new Chart(parameterNode, {
                type: "bar",
                data: { labels: rows.map((row) => row.name), datasets: [{ label: "Within configured limits (%)", data: rows.map((row) => row.compliance), backgroundColor: rows.map((row) => row.compliance === null ? "rgba(135,149,165,.55)" : row.compliance >= 95 ? "rgba(64,224,173,.78)" : row.compliance >= 80 ? "rgba(255,180,84,.78)" : "rgba(255,93,112,.82)"), borderRadius: 4, barThickness: 9 }] },
                options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: (context) => { const row = rows[context.dataIndex]; return `${row.readings} results · ${row.excursions} excursions · ${row.unbounded} without limits`; } } } }, scales: { x: { min: 0, max: 100, grid: { color: "rgba(131,163,184,.1)" }, ticks: { callback: (value) => `${value}%` } }, y: { grid: { display: false }, ticks: { autoSkip: false } } } }
            });
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        tooltipController();
        buildCharts();
    });
})();
