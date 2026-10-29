(function () {
    function readJson() {
        const node = document.getElementById("filtered-water-filter-detail-data");
        if (!node) return null;
        try { return JSON.parse(node.textContent); } catch (_) { return null; }
    }

    function init() {
        const payload = readJson();
        if (!payload || typeof Chart === "undefined") return;
        Chart.defaults.color = "#8da5b8";
        Chart.defaults.font.family = 'Inter, "Segoe UI", sans-serif';
        Chart.defaults.font.size = 10;

        const trendNode = document.getElementById("fwParameterTrend");
        const selector = document.getElementById("fwParameterSelect");
        if (trendNode && selector && payload.parameters.length) {
            const emptyNode = trendNode.parentElement.querySelector(".fw-chart-empty");
            let trendChart;

            function drawTrend() {
                const parameter = payload.parameters.find((item) => String(item.id) === String(selector.value)) || payload.parameters[0];
                if (trendChart) trendChart.destroy();
                if (emptyNode) emptyNode.remove();
                if (!parameter.values.length) {
                    const message = document.createElement("div");
                    message.className = "fw-chart-empty";
                    message.textContent = "No recorded values for this parameter in the selected period.";
                    trendNode.parentElement.appendChild(message);
                    trendChart = null;
                    return;
                }
                const datasets = [{
                    label: parameter.name + (parameter.unit ? ` (${parameter.unit})` : ""),
                    data: parameter.values,
                    borderColor: "#38d7f2",
                    backgroundColor: "rgba(56,215,242,.12)",
                    fill: true,
                    tension: .24,
                    pointRadius: parameter.values.length > 35 ? 0 : 2,
                    pointHoverRadius: 4,
                    borderWidth: 2
                }];
                if (parameter.minimum !== null) datasets.push({ label: "Lower limit", data: parameter.labels.map(() => parameter.minimum), borderColor: "#ffb454", borderDash: [5, 4], pointRadius: 0, borderWidth: 1.2, fill: false });
                if (parameter.maximum !== null) datasets.push({ label: "Upper limit", data: parameter.labels.map(() => parameter.maximum), borderColor: "#ff5d70", borderDash: [5, 4], pointRadius: 0, borderWidth: 1.2, fill: false });
                trendChart = new Chart(trendNode, {
                    type: "line",
                    data: { labels: parameter.labels, datasets },
                    options: {
                        responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
                        plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 7, padding: 11 } }, tooltip: { backgroundColor: "#081626", borderColor: "rgba(93,190,215,.3)", borderWidth: 1 } },
                        scales: {
                            x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0, callback(value, index) { const label = parameter.labels[index] || ""; return label.replace("T", " ").slice(5, 16); } } },
                            y: { grid: { color: "rgba(131,163,184,.1)" }, title: { display: Boolean(parameter.unit), text: parameter.unit } }
                        }
                    }
                });
            }
            selector.addEventListener("change", drawTrend);
            drawTrend();
        }

        const performanceNode = document.getElementById("fwPerformanceChart");
        if (performanceNode) {
            new Chart(performanceNode, {
                type: "bar",
                data: { labels: payload.performance.labels, datasets: [{ label: "Period compliance (%)", data: payload.performance.values, backgroundColor: payload.performance.values.map((value) => value >= 95 ? "rgba(64,224,173,.8)" : value >= 80 ? "rgba(255,180,84,.8)" : "rgba(255,93,112,.82)"), borderRadius: 4, barThickness: 11 }] },
                options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { min: 0, max: 100, grid: { color: "rgba(131,163,184,.1)" }, ticks: { callback: (value) => `${value}%` } }, y: { grid: { display: false }, ticks: { autoSkip: false } } } }
            });
        }

        const capacityNode = document.getElementById("fwCapacityChart");
        if (capacityNode) {
            const current = payload.capacity.values[0];
            const design = payload.capacity.values[1];
            new Chart(capacityNode, {
                type: "bar",
                data: { labels: payload.capacity.labels, datasets: [{ label: "m³/h", data: [current, design], backgroundColor: ["rgba(56,215,242,.82)", "rgba(90,118,144,.55)"], borderRadius: 4, barThickness: 17 }] },
                options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: () => design > 0 ? `Capacity utilization: ${(current / design * 100).toFixed(1)}%` : "Design capacity unavailable" } } }, scales: { x: { beginAtZero: true, suggestedMax: Math.max(current, design) * 1.15, grid: { color: "rgba(131,163,184,.1)" }, title: { display: true, text: "m³/h" } }, y: { grid: { display: false } } } }
            });
        }
    }

    document.addEventListener("DOMContentLoaded", init);
})();
