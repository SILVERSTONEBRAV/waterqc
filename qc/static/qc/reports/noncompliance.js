(() => {
    "use strict";
    const root = document.querySelector(".qcnc-page");
    if (!root) return;

    const form = document.getElementById("qcncFilters");
    const navigate = updates => {
        const params = new URLSearchParams(window.location.search);
        Object.entries(updates).forEach(([key, value]) => value == null ? params.delete(key) : params.set(key, String(value)));
        window.location.href = `${window.location.pathname}?${params.toString()}`;
    };
    document.querySelectorAll("[data-qcnc-page]").forEach(button => button.addEventListener("click", () => navigate({ page: button.dataset.qcncPage })));
    document.getElementById("qcncPeriod")?.addEventListener("change", event => {
        if (event.target.value !== "custom") form?.requestSubmit();
    });
    form?.querySelectorAll('input[type="date"]').forEach(input => input.addEventListener("change", () => {
        const period = document.getElementById("qcncPeriod");
        if (period) period.value = "custom";
    }));
    const toggle = document.querySelector(".qcnc-page .qcr-filter-toggle");
    const filterGrid = document.getElementById("qcncFilterGrid");
    toggle?.addEventListener("click", () => {
        const expanded = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", String(!expanded));
        if (filterGrid) filterGrid.hidden = expanded;
    });
    document.getElementById("plantScopeSelect")?.addEventListener("change", event => navigate({ plant: event.target.value, page: 1 }));

    let analytics = {}, cases = [];
    try { analytics = JSON.parse(document.getElementById("qcnc-analytics-data")?.textContent || "{}"); } catch (_) {}
    try { cases = JSON.parse(document.getElementById("qcnc-case-data")?.textContent || "[]"); } catch (_) {}
    if (!window.Plotly) return;
    const dark = document.documentElement.classList.contains("theme-dark") || document.documentElement.dataset.theme === "night";
    const ink = dark ? "#e2e8f0" : "#172b40";
    const muted = dark ? "#94a3b8" : "#64748b";
    const grid = dark ? "rgba(148,163,184,.16)" : "rgba(100,116,139,.16)";
    const palette = { critical: "#b91c1c", high: "#d55e00", moderate: "#e69f00", low: "#0072b2", open: "#d55e00", review: "#0072b2", closed: "#009e73", derived: "#8b5cf6" };
    const layout = { paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { family: "Inter, Segoe UI, sans-serif", color: ink, size: 12 }, margin: { l: 58, r: 24, t: 20, b: 55 }, xaxis: { gridcolor: grid, tickfont: { color: muted }, automargin: true }, yaxis: { gridcolor: grid, tickfont: { color: muted }, automargin: true }, legend: { orientation: "h", y: -0.24, font: { color: muted } }, hoverlabel: { bgcolor: dark ? "#0b1727" : "#fff", font: { color: ink } } };
    const config = { responsive: true, displaylogo: false, scrollZoom: true, toImageButtonOptions: { format: "png", filename: "qca-noncompliance", scale: 2 }, modeBarButtonsToRemove: ["lasso2d", "select2d"] };
    const render = (id, traces, options = {}) => { const element = document.getElementById(id); if (element) Plotly.newPlot(element, traces, { ...layout, ...options }, config); };

    const periods = analytics.periods || [];
    const trend = analytics.trend;
    const trendX = periods.map((_, i) => i);
    const trendY = trend ? trendX.map(i => trend.intercept + trend.slope_per_period * i) : [];
    render("qcncTrendChart", [
        { type: "scatter", mode: "lines+markers", name: "Recorded cases", x: periods.map(row => row.label), y: periods.map(row => row.cases), line: { color: "#0072b2", width: 2.5 }, marker: { color: "#0072b2", size: 8 }, hovertemplate: "%{x}<br>%{y} cases<extra></extra>" },
        ...(trend ? [{ type: "scatter", mode: "lines", name: "Theil–Sen trend", x: periods.map(row => row.label), y: trendY, line: { color: "#cc79a7", width: 2, dash: "dash" }, hovertemplate: "%{x}<br>Trend %{y:.2f}<extra></extra>" }] : []),
    ], { yaxis: { ...layout.yaxis, title: "Case count", rangemode: "tozero" }, xaxis: { ...layout.xaxis, tickangle: -25 } });

    const statuses = analytics.status_counts || [];
    const statusColor = row => row.label.toLowerCase().includes("closed") ? palette.closed : row.label.toLowerCase().includes("review") ? palette.review : row.label.toLowerCase().includes("derived") ? palette.derived : palette.open;
    render("qcncStatusChart", [{ type: "pie", hole: .62, sort: false, labels: statuses.map(row => row.label), values: statuses.map(row => row.count), marker: { colors: statuses.map(statusColor), line: { color: dark ? "#101d30" : "#fff", width: 3 } }, textinfo: "percent", hovertemplate: "%{label}: %{value:,} (%{percent})<extra></extra>" }], { margin: { l: 12, r: 12, t: 10, b: 28 }, legend: { ...layout.legend, y: -.08 }, annotations: [{ text: `<b>${analytics.total || 0}</b><br>cases`, showarrow: false, font: { color: ink, size: 15 } }] });

    const risks = analytics.risk_counts || [];
    const riskColor = { Critical: palette.critical, High: palette.high, Moderate: palette.moderate, Low: palette.low };
    render("qcncRiskChart", [{ type: "pie", hole: .62, sort: false, labels: risks.map(row => row.label), values: risks.map(row => row.count), marker: { colors: risks.map(row => riskColor[row.label] || "#64748b"), line: { color: dark ? "#101d30" : "#fff", width: 3 } }, textinfo: "percent", hovertemplate: "%{label}: %{value:,} (%{percent})<extra></extra>" }], { margin: { l: 12, r: 12, t: 10, b: 28 }, legend: { ...layout.legend, y: -.08 }, annotations: [{ text: `<b>${analytics.critical_high || 0}</b><br>high / critical`, showarrow: false, font: { color: ink, size: 13 } }] });

    const parameters = analytics.top_parameters || [];
    const total = parameters.reduce((sum, row) => sum + (row.cases || 0), 0);
    let cumulative = 0;
    const cumulativePct = parameters.map(row => { cumulative += row.cases || 0; return total ? cumulative / total * 100 : 0; });
    render("qcncParetoChart", [
        { type: "bar", name: "Cases", x: parameters.map(row => row.parameter), y: parameters.map(row => row.cases), marker: { color: parameters.map((_, i) => ["#0072b2", "#009e73", "#e69f00", "#cc79a7", "#56b4e9", "#d55e00"][i % 6]) }, hovertemplate: "%{x}<br>%{y} cases<extra></extra>" },
        { type: "scatter", mode: "lines+markers", name: "Cumulative share", x: parameters.map(row => row.parameter), y: cumulativePct, yaxis: "y2", line: { color: "#6b4c9a", width: 2.4 }, marker: { symbol: "diamond", size: 7 }, hovertemplate: "%{x}<br>Cumulative %{y:.1f}%<extra></extra>" },
    ], { barmode: "group", yaxis: { ...layout.yaxis, title: "Cases", rangemode: "tozero" }, yaxis2: { title: "Cumulative %", overlaying: "y", side: "right", range: [0, 100], showgrid: false, ticksuffix: "%", tickfont: { color: muted } }, xaxis: { ...layout.xaxis, tickangle: -28 } });

    const aging = analytics.aging_buckets || [];
    render("qcncAgingChart", [{ type: "bar", x: aging.map(row => row.label), y: aging.map(row => row.count), marker: { color: ["#009e73", "#e69f00", "#d55e00", "#b91c1c"] }, text: aging.map(row => row.count), textposition: "outside", hovertemplate: "%{x}<br>%{y} active cases<extra></extra>" }], { yaxis: { ...layout.yaxis, title: "Open / review cases", rangemode: "tozero" }, xaxis: { ...layout.xaxis, tickangle: -18 }, showlegend: false });
    const causes = analytics.top_causes || [];
    render("qcncCauseChart", [{ type: "bar", orientation: "h", y: causes.map(row => row.cause).reverse(), x: causes.map(row => row.cases).reverse(), marker: { color: causes.map((_, i) => ["#0072b2", "#009e73", "#e69f00", "#cc79a7", "#56b4e9", "#d55e00"][i % 6]).reverse() }, hovertemplate: "%{y}<br>%{x} cases<extra></extra>" }], { xaxis: { ...layout.xaxis, title: "Cases", rangemode: "tozero" }, yaxis: { ...layout.yaxis, title: "", automargin: true }, showlegend: false });

    const bands = ["Critical", "High", "Moderate", "Low"];
    const scatterTraces = bands.map(band => {
        const points = cases.filter(row => row.risk_band === band && row.deviation != null);
        return { type: "scattergl", mode: "markers", name: band, x: points.map(row => Math.abs(row.deviation)), y: points.map(row => row.risk_score), text: points.map(row => `${row.reference || "—"} · ${row.parameter}`), marker: { color: riskColor[band], size: 9, opacity: .78, symbol: band === "Critical" ? "x" : band === "High" ? "diamond" : band === "Moderate" ? "circle" : "square" }, hovertemplate: "%{text}<br>|Deviation| %{x:.5g}<br>Risk %{y:.2f}<extra>%{fullData.name}</extra>" };
    }).filter(trace => trace.x.length);
    const scatter = cases.filter(row => row.deviation != null && row.risk_score != null);
    if (scatter.length >= 3) {
        const xs = scatter.map(row => Math.abs(row.deviation)), ys = scatter.map(row => row.risk_score);
        const meanX = xs.reduce((a, b) => a + b, 0) / xs.length, meanY = ys.reduce((a, b) => a + b, 0) / ys.length;
        const covariance = xs.reduce((sum, x, i) => sum + (x - meanX) * (ys[i] - meanY), 0);
        const variance = xs.reduce((sum, x) => sum + (x - meanX) ** 2, 0);
        const slope = variance ? covariance / variance : 0;
        const minX = Math.min(...xs), maxX = Math.max(...xs);
        scatterTraces.push({ type: "scatter", mode: "lines", name: "OLS reference line", x: [minX, maxX], y: [meanY + slope * (minX - meanX), meanY + slope * (maxX - meanX)], line: { color: "#6b4c9a", dash: "dash", width: 2 }, hoverinfo: "skip" });
    }
    render("qcncScatterChart", scatterTraces, { xaxis: { ...layout.xaxis, title: "Absolute deviation" }, yaxis: { ...layout.yaxis, title: "Risk score", rangemode: "tozero" } });

    document.querySelector("[data-qcnc-download]")?.addEventListener("click", async () => {
        const charts = [...document.querySelectorAll(".qcnc-chart-grid .qcr-chart")].filter(chart => chart.data?.length);
        if (!charts.length) return;
        // Keep the returned window handle so the click can populate and print it.
        const report = window.open("", "_blank", "width=1200,height=900");
        if (!report) return;
        const images = await Promise.all(charts.map(chart => Plotly.toImage(chart, { format: "png", width: 1100, height: 600, scale: 1 })));
        report.document.write(`<title>Non-compliance visual report</title><style>body{font:16px system-ui;color:#172b40;max-width:1180px;margin:30px auto;padding:0 20px}img{display:block;width:100%;margin:20px 0;border:1px solid #cbd5e1}h1{font-size:26px}</style><h1>Non-compliance visual report</h1>${images.map(src => `<img src="${src}" alt="Non-compliance chart">`).join("")}`);
        report.document.close();
        setTimeout(() => report.print(), 500);
    });
})();
