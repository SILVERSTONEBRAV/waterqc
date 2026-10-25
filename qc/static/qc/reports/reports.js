(() => {
    "use strict";

    const form = document.getElementById("qcrFilters");
    const root = document.querySelector(".qcr-page");
    if (!form || !root) return;

    const navigateWith = (updates = {}, remove = []) => {
        const next = new URLSearchParams(window.location.search);
        for (const key of remove) next.delete(key);
        for (const [key, value] of Object.entries(updates)) {
            if (value === null || value === undefined || value === "") next.delete(key);
            else next.set(key, String(value));
        }
        const qs = next.toString();
        window.location.href = `${window.location.pathname}${qs ? `?${qs}` : ""}`;
    };

    document.querySelectorAll("[data-qcr-view]").forEach(link => {
        link.addEventListener("click", event => {
            event.preventDefault();
            navigateWith({ view: link.dataset.qcrView, page: 1 });
        });
    });

    document.querySelectorAll("[data-qcr-water-type]").forEach(link => {
        link.addEventListener("click", event => {
            event.preventDefault();
            navigateWith({ water_type: link.dataset.qcrWaterType, page: 1 });
        });
    });

    document.querySelectorAll("[data-qcr-page]").forEach(button => {
        button.addEventListener("click", () => navigateWith({ page: button.dataset.qcrPage }));
    });

    document.querySelectorAll("[data-qcr-daily-page]").forEach(button => {
        button.addEventListener("click", () => navigateWith({ daily_page: button.dataset.qcrDailyPage }));
    });

    const period = document.getElementById("qcrPeriod");
    if (period) {
        period.addEventListener("change", () => {
            if (period.value !== "custom") form.requestSubmit();
        });
    }

    form.querySelectorAll('input[type="date"]').forEach(input => {
        input.addEventListener("change", () => {
            if (period) period.value = "custom";
        });
    });

    const plantSelect = document.getElementById("plantScopeSelect");
    if (plantSelect) {
        plantSelect.addEventListener("change", () => {
            if (plantSelect.value) navigateWith({ plant: plantSelect.value, page: 1 });
        });
    }

    const filterToggle = document.querySelector(".qcr-filter-toggle");
    const filterGrid = document.getElementById("qcrFilterGrid");
    if (filterToggle && filterGrid) {
        filterToggle.addEventListener("click", () => {
            const expanded = filterToggle.getAttribute("aria-expanded") === "true";
            filterToggle.setAttribute("aria-expanded", String(!expanded));
            filterGrid.hidden = expanded;
        });
    }

    const chartDataEl = document.getElementById("qcr-analytics-data");
    let payload = {};
    try { payload = JSON.parse(chartDataEl?.textContent || "{}"); } catch (_) { payload = {}; }
    const series = payload.series || {};
    const dark = document.documentElement.classList.contains("theme-dark") || document.documentElement.dataset.theme === "night";
    const ink = dark ? "#dbeafe" : "#1e293b";
    const muted = dark ? "#94a3b8" : "#64748b";
    const grid = dark ? "rgba(148,163,184,.13)" : "rgba(100,116,139,.15)";
    const transparent = "rgba(0,0,0,0)";
    const config = {
        responsive: true,
        displaylogo: false,
        scrollZoom: true,
        toImageButtonOptions: { format: "png", filename: "qca-analytics", scale: 2 },
        modeBarButtonsToRemove: ["lasso2d", "select2d"],
    };
    const baseLayout = {
        paper_bgcolor: transparent,
        plot_bgcolor: transparent,
        font: { family: "Inter, Segoe UI, sans-serif", color: ink, size: 11 },
        margin: { l: 52, r: 22, t: 22, b: 54 },
        hoverlabel: { bgcolor: dark ? "#0b1727" : "#fff", font: { color: ink } },
        xaxis: { gridcolor: grid, zerolinecolor: grid, tickfont: { color: muted }, titlefont: { color: muted } },
        yaxis: { gridcolor: grid, zerolinecolor: grid, tickfont: { color: muted }, titlefont: { color: muted }, automargin: true },
        legend: { orientation: "h", y: -0.2, font: { color: muted } },
    };

    const render = (id, traces, layout = {}) => {
        const element = document.getElementById(id);
        if (!element || !window.Plotly) return;
        Plotly.newPlot(element, traces, { ...baseLayout, ...layout }, config);
    };

    if (window.Plotly && Object.keys(series).length) {
        const colors = { actual: "#0072b2", trend: "#6b4c9a", rolling: "#e69f00", good: "#009e73", bad: "#d55e00", missing: "#64748b", pending: "#cc79a7", unconfigured: "#56b4e9", forecast: "#6b4c9a" };
        const complianceColors = (series.status || []).map(status => status === "Out of range" ? colors.bad : status === "No limit configured" ? colors.unconfigured : status === "Missing" ? colors.missing : ["Pending entry", "Verify historical value"].includes(status) ? colors.pending : colors.good);
        const complianceSymbols = (series.status || []).map(status => status === "Out of range" ? "x" : status === "No limit configured" ? "diamond" : ["Pending entry", "Verify historical value"].includes(status) ? "triangle-up" : "circle");

        const trendTraces = [
            {
                type: "scatter", mode: "markers", name: "Observed results", x: series.x, y: series.y,
                marker: { color: complianceColors, symbol: complianceSymbols, size: 7, opacity: .82, line: { color: dark ? "#0d1727" : "#fff", width: 1 } },
                customdata: series.reference || [], hovertemplate: "%{x}<br><b>%{y:.5g} " + (series.unit || "") + "</b><br>Sample %{customdata}<extra></extra>",
            },
            { type: "scatter", mode: "lines", name: "Rolling mean", x: series.x, y: series.rolling, line: { color: colors.rolling, width: 2.3, shape: "spline" }, hovertemplate: "%{x}<br>Rolling mean %{y:.5g}<extra></extra>" },
        ];
        if (series.trend?.length) trendTraces.push({ type: "scatter", mode: "lines", name: "OLS trend", x: series.x, y: series.trend, line: { color: colors.trend, width: 2.2, dash: "dash" }, hovertemplate: "%{x}<br>Trend %{y:.5g}<extra></extra>" });
        if (series.forecast?.length) {
            const forecastX = series.forecast.map(item => item.period);
            trendTraces.push({ type: "scatter", mode: "lines", name: "Forecast interval", x: forecastX, y: series.forecast.map(item => item.high), line: { width: 0 }, showlegend: false, hoverinfo: "skip" });
            trendTraces.push({ type: "scatter", mode: "lines", name: "Approx. 95% interval", x: forecastX, y: series.forecast.map(item => item.low), line: { color: "rgba(99,102,241,.25)", width: 1 }, fill: "tonexty", fillcolor: "rgba(99,102,241,.12)", hovertemplate: "%{x}<br>Approx. lower band %{y:.5g}<extra></extra>" });
            trendTraces.push({ type: "scatter", mode: "lines", name: "Forecast", x: forecastX, y: series.forecast.map(item => item.mean), line: { color: colors.forecast, width: 2.4, dash: "dot" }, hovertemplate: "%{x}<br>Forecast %{y:.5g}<extra></extra>" });
        }
        render("qcrTrendChart", trendTraces, {
            xaxis: { ...baseLayout.xaxis, type: "date", rangeslider: { visible: true, thickness: .08, bgcolor: dark ? "#101d30" : "#eff6ff" } },
            yaxis: { ...baseLayout.yaxis, title: series.unit || "Result" },
            shapes: [
                ...(series.lower_limit !== null && series.lower_limit !== undefined ? [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: series.lower_limit, y1: series.lower_limit, line: { color: colors.bad, dash: "dash", width: 1.5 } }] : []),
                ...(series.upper_limit !== null && series.upper_limit !== undefined ? [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: series.upper_limit, y1: series.upper_limit, line: { color: colors.bad, dash: "dash", width: 1.5 } }] : []),
            ],
        });

        render("qcrComplianceChart", [{
            type: "pie", hole: .66, sort: false, direction: "clockwise", rotation: 24,
            labels: ["Within limits", "Out of range", "Missing", "Pending entry", "Historical value to verify", "No limit configured"],
            values: [payload.distribution?.compliant || 0, payload.distribution?.out_of_range || 0, payload.distribution?.missing || 0, payload.distribution?.pending || 0, payload.distribution?.legacy_unverified || 0, payload.distribution?.not_evaluated || 0],
            marker: { colors: [colors.good, colors.bad, colors.missing, colors.pending, "#a85585", colors.unconfigured], line: { color: dark ? "#0d1727" : "#fff", width: 3 } },
            textinfo: "percent", textposition: "inside", insidetextfont: { color: "white", size: 11 },
            hovertemplate: "%{label}: %{value:,} (%{percent})<extra></extra>",
        }], { showlegend: true, legend: { ...baseLayout.legend, y: -.12 }, margin: { l: 15, r: 15, t: 10, b: 30 }, annotations: [{ text: `<b>${((payload.distribution?.compliant || 0) + (payload.distribution?.out_of_range || 0))}</b><br><span style="font-size:10px">evaluated</span>`, showarrow: false, font: { color: ink, size: 15 } }] });

        const periodTraces = [
            { type: "bar", name: "Within limits", x: series.period_labels || series.periods, y: series.period_within, marker: { color: colors.good }, hovertemplate: "%{x}<br>Within: %{y}<extra></extra>" },
            { type: "bar", name: "Out of range", x: series.period_labels || series.periods, y: series.period_out, marker: { color: colors.bad }, hovertemplate: "%{x}<br>Out of range: %{y}<extra></extra>" },
            { type: "scatter", mode: "lines+markers", name: "Mean result", x: series.period_labels || series.periods, y: series.period_mean, yaxis: "y2", line: { color: colors.trend, width: 2.4 }, marker: { size: 7, color: colors.trend }, hovertemplate: "%{x}<br>Mean: %{y:.5g} " + (series.unit || "") + "<extra></extra>" },
        ];
        render("qcrPeriodChart", periodTraces, { barmode: "stack", yaxis: { ...baseLayout.yaxis, title: "Evaluated results" }, yaxis2: { title: `Mean (${series.unit || "result"})`, overlaying: "y", side: "right", showgrid: false, tickfont: { color: muted } }, xaxis: { ...baseLayout.xaxis, tickangle: -28 }, legend: { ...baseLayout.legend, y: -.3 } });

        const distributionTraces = [{ type: "histogram", x: payload.distribution?.values || [], name: "Result frequency", histnorm: "probability density", marker: { color: colors.actual, opacity: .52, line: { color: colors.actual, width: 1 } }, nbinsx: 32, hovertemplate: "Result %{x:.5g}<br>Density %{y:.4f}<extra></extra>" }];
        const boxes = series.phase_boxes || [];
        if (boxes.length) {
            boxes.forEach((box, index) => distributionTraces.push({ type: "violin", name: box.label, x: Array(box.values.length).fill(box.label), y: box.values, xaxis: "x2", yaxis: "y2", side: "both", box: { visible: true }, meanline: { visible: true }, points: false, opacity: .55, line: { color: ["#8b5cf6", "#06b6d4", "#10b981", "#f59e0b"][index % 4] }, fillcolor: ["rgba(139,92,246,.15)", "rgba(6,182,212,.15)", "rgba(16,185,129,.15)", "rgba(245,158,11,.15)"][index % 4], hovertemplate: `${box.label}<br>%{y:.5g}<extra></extra>` }));
        }
        render("qcrDistributionChart", distributionTraces, {
            grid: { rows: 1, columns: 2, pattern: "independent", xgap: .12 },
            xaxis: { ...baseLayout.xaxis, domain: boxes.length ? [0, .46] : [0, 1], title: `Result (${series.unit || ""})` },
            yaxis: { ...baseLayout.yaxis, title: "Density" },
            xaxis2: { ...baseLayout.xaxis, domain: [.57, 1], title: "Phase / comparison" },
            yaxis2: { ...baseLayout.yaxis, anchor: "x2", title: `Result (${series.unit || ""})`, showgrid: false },
            showlegend: boxes.length > 1,
            legend: { ...baseLayout.legend, y: -.23 },
        });

        const heatX = series.heatmap_x?.length ? series.heatmap_x : (series.period_labels || series.periods || []);
        let heatY = series.heatmap_y || [];
        let heatZ = series.heatmap_z || [];
        if (!heatY.length && series.periods?.length) {
            heatY = [payload.focus_parameter || "Compliance"];
            heatZ = [series.period_compliance || []];
        }
        render("qcrHeatmapChart", [{ type: "heatmap", x: heatX, y: heatY, z: heatZ, zmin: 0, zmax: 100, colorscale: [[0,"#f43f5e"],[.35,"#fb923c"],[.65,"#facc15"],[.82,"#34d399"],[1,"#0e7490"]], colorbar: { title: "Compliance %", ticksuffix: "%", tickfont: { color: muted } }, hovertemplate: "%{y}<br>%{x}<br>Compliance %{z:.1f}%<extra></extra>" }], { margin: { l: 95, r: 35, t: 15, b: 68 }, xaxis: { ...baseLayout.xaxis, tickangle: -35 }, yaxis: { ...baseLayout.yaxis, title: "" } });

        const forecast = series.forecast || [];
        const histX = series.periods || [];
        const histY = series.period_mean || [];
        const forecastTraces = [{ type: "scatter", mode: "lines+markers", name: "Historical mean", x: histX, y: histY, line: { color: colors.actual, width: 2.2 }, marker: { color: colors.actual, size: 6 }, hovertemplate: "%{x}<br>Mean %{y:.5g}<extra></extra>" }];
        if (forecast.length) {
            const fx = forecast.map(item => item.period);
            forecastTraces.push({ type: "scatter", mode: "lines", name: "Upper projection band", x: fx, y: forecast.map(item => item.high), line: { width: 0 }, showlegend: false, hoverinfo: "skip" });
            forecastTraces.push({ type: "scatter", mode: "lines", name: "Approx. 95% projection interval", x: fx, y: forecast.map(item => item.low), line: { color: "rgba(99,102,241,.25)", width: 1 }, fill: "tonexty", fillcolor: "rgba(99,102,241,.12)", hovertemplate: "%{x}<br>Approx. low %{y:.5g}<extra></extra>" });
            forecastTraces.push({ type: "scatter", mode: "lines+markers", name: "Damped trend forecast", x: fx, y: forecast.map(item => item.mean), line: { color: colors.forecast, width: 2.4, dash: "dash" }, marker: { symbol: "diamond", size: 7, color: colors.forecast }, hovertemplate: "%{x}<br>Forecast %{y:.5g}<extra></extra>" });
        }
        render("qcrForecastChart", forecastTraces, { xaxis: { ...baseLayout.xaxis, type: "date", tickangle: -30 }, yaxis: { ...baseLayout.yaxis, title: series.unit || "Result" }, legend: { ...baseLayout.legend, y: -.25 } });

        const stageData = payload.stage_comparison || [];
        const stageColors = ["#06b6d4", "#8b5cf6", "#f59e0b", "#10b981", "#ec4899", "#3b82f6"];
        render("qcrStageChart", [
            { type: "bar", name: "Mean result", x: stageData.map(item => item.label), y: stageData.map(item => item.mean), marker: { color: stageData.map((_, index) => stageColors[index % stageColors.length]) }, error_y: { type: "data", symmetric: false, array: stageData.map(item => item.ci_high != null ? Math.max(0, item.ci_high - item.mean) : 0), arrayminus: stageData.map(item => item.ci_low != null ? Math.max(0, item.mean - item.ci_low) : 0), color: muted, thickness: 1.5, width: 5 }, hovertemplate: "%{x}<br>Mean %{y:.5g} " + (series.unit || "") + "<extra></extra>" },
            { type: "scatter", mode: "lines+markers", name: "Compliance", x: stageData.map(item => item.label), y: stageData.map(item => item.compliance_rate), yaxis: "y2", line: { color: "#f43f5e", width: 2.4 }, marker: { color: "#f43f5e", size: 8, symbol: "diamond" }, connectgaps: false, hovertemplate: "%{x}<br>Compliance %{y:.1f}%<extra></extra>" },
        ], { barmode: "group", yaxis: { ...baseLayout.yaxis, title: `Mean (${series.unit || "result"})` }, yaxis2: { title: "Compliance %", overlaying: "y", side: "right", range: [0, 100], showgrid: false, ticksuffix: "%", tickfont: { color: muted } }, xaxis: { ...baseLayout.xaxis, tickangle: -20 }, legend: { ...baseLayout.legend, y: -.22 } });

        const multivariate = payload.multivariate || {};
        if ((multivariate.parameters || []).length > 1) {
            render("qcrCorrelationChart", [{
                type: "heatmap", x: multivariate.parameters, y: multivariate.parameters,
                z: multivariate.spearman_matrix || multivariate.pearson_matrix,
                customdata: multivariate.sample_size_matrix || [], zmin: -1, zmax: 1,
                colorscale: [[0,"#be123c"],[.25,"#fb7185"],[.5,"#f8fafc"],[.75,"#2dd4bf"],[1,"#0e7490"]],
                colorbar: { title: "Spearman ρ", tickfont: { color: muted } },
                hovertemplate: "%{y} × %{x}<br>Spearman ρ %{z:.3f}<br>Paired samples %{customdata}<extra></extra>",
            }], { margin: { l: 110, r: 40, t: 18, b: 105 }, xaxis: { ...baseLayout.xaxis, tickangle: -38 }, yaxis: { ...baseLayout.yaxis, autorange: "reversed" } });
        }
        const pca = multivariate.pca || {};
        if (pca.available && (pca.scores || []).length) {
            const variance = pca.explained_variance || [];
            const varianceText = `${((variance[0] || 0) * 100).toFixed(1)}% / ${((variance[1] || 0) * 100).toFixed(1)}%`;
            render("qcrPcaChart", [{
                type: "scattergl", mode: "markers", name: "Sample scores",
                x: pca.scores.map(item => item.pc1), y: pca.scores.map(item => item.pc2),
                text: pca.scores.map(item => item.sample_id),
                marker: { size: 8, opacity: .78, color: pca.scores.map(item => item.pc1), colorscale: "Viridis", showscale: true, colorbar: { title: "PC1 score", tickfont: { color: muted } } },
                hovertemplate: "Sample %{text}<br>PC1 %{x:.3f}<br>PC2 %{y:.3f}<extra></extra>",
            }], { xaxis: { ...baseLayout.xaxis, title: `PC1 (${((variance[0] || 0) * 100).toFixed(1)}% variance)` }, yaxis: { ...baseLayout.yaxis, title: `PC2 (${((variance[1] || 0) * 100).toFixed(1)}% variance)` }, annotations: [{ text: `PC1 / PC2 explain ${varianceText}`, showarrow: false, xref: "paper", yref: "paper", x: 1, y: 1.12, xanchor: "right", font: { color: muted, size: 10 } }] });
            render("qcrPcaLoadingsChart", [
                { type: "bar", name: "PC1 loading", x: pca.loadings.map(item => item.parameter), y: pca.loadings.map(item => item.pc1), marker: { color: "#06b6d4" }, hovertemplate: "%{x}<br>PC1 loading %{y:.3f}<extra></extra>" },
                { type: "bar", name: "PC2 loading", x: pca.loadings.map(item => item.parameter), y: pca.loadings.map(item => item.pc2), marker: { color: "#8b5cf6" }, hovertemplate: "%{x}<br>PC2 loading %{y:.3f}<extra></extra>" },
            ], { barmode: "group", xaxis: { ...baseLayout.xaxis, tickangle: -32 }, yaxis: { ...baseLayout.yaxis, title: "Standardized loading" } });
        }

        document.querySelector('[data-qcr-chart-action="reset"]')?.addEventListener("click", () => {
            document.querySelectorAll(".qcr-chart").forEach(chart => { if (chart.data) Plotly.relayout(chart, { "xaxis.autorange": true, "yaxis.autorange": true }); });
        });
        document.querySelector('[data-qcr-chart-action="download"]')?.addEventListener("click", () => {
            const chart = document.getElementById("qcrTrendChart");
            if (chart?.data) Plotly.downloadImage(chart, { format: "png", filename: `qca-${(payload.focus_parameter || "analytics").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-trend`, width: 1800, height: 900, scale: 2 });
        });
    }
})();
