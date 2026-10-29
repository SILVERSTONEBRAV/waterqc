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

    const filterToggle = document.getElementById("qcrFilterToggle") || document.querySelector(".qcr-filter-toggle");
    const filterGrid = document.getElementById("qcrFilterGrid");
    const storageKey = "qcr_filters_collapsed";
    if (filterToggle && filterGrid) {
        const isVizPage = window.location.pathname.includes("visualizations") || window.location.pathname.includes("analytics");
        let savedState = localStorage.getItem(storageKey);
        // Default to collapsed on visualizations and analytics dashboards so charts take center stage
        if (savedState === null) {
            savedState = isVizPage ? "true" : "false";
        }
        const setCollapsed = (collapsed) => {
            filterToggle.setAttribute("aria-expanded", String(!collapsed));
            filterGrid.hidden = collapsed;
            localStorage.setItem(storageKey, String(collapsed));
        };
        setCollapsed(savedState === "true");

        filterToggle.addEventListener("click", () => {
            const currentlyCollapsed = filterGrid.hidden;
            setCollapsed(!currentlyCollapsed);
        });
    }

    // Quick preset buttons (7D, 14D, 30D, 90D, 1Y, All)
    document.querySelectorAll("[data-qcr-period]").forEach(btn => {
        btn.addEventListener("click", () => {
            const periodVal = btn.dataset.qcrPeriod;
            if (period) {
                period.value = periodVal;
                // Clear explicit custom dates so the preset window calculates cleanly
                form.querySelectorAll('input[type="date"]').forEach(inp => inp.value = "");
                form.requestSubmit();
            }
        });
    });

    const chartDataEl = document.getElementById("qcr-analytics-data");
    let payload = {};
    try { payload = JSON.parse(chartDataEl?.textContent || "{}"); } catch (_) { payload = {}; }
    const series = payload.series || {};
    const dark = document.documentElement.classList.contains("theme-dark") || document.documentElement.dataset.theme === "night" || true;
    const ink = "#e0f2fe";
    const muted = "#94a3b8";
    const grid = "rgba(56, 189, 248, 0.08)";
    const transparent = "rgba(0,0,0,0)";
    const config = {
        responsive: true,
        displaylogo: false,
        scrollZoom: true,
        toImageButtonOptions: { format: "png", filename: "qca-advanced-analytics", scale: 2 },
        modeBarButtonsToRemove: ["lasso2d", "select2d"],
    };
    const baseLayout = {
        paper_bgcolor: transparent,
        plot_bgcolor: transparent,
        font: { family: "'Inter', 'JetBrains Mono', Segoe UI, sans-serif", color: ink, size: 10.5 },
        margin: { l: 48, r: 20, t: 18, b: 46 },
        hoverlabel: { bgcolor: "#07172b", bordercolor: "rgba(56, 189, 248, 0.35)", font: { color: "#effaff", family: "'JetBrains Mono', monospace", size: 11 } },
        xaxis: { gridcolor: grid, zerolinecolor: "rgba(56, 189, 248, 0.15)", tickfont: { color: muted, size: 10 }, titlefont: { color: muted, size: 10.5 } },
        yaxis: { gridcolor: grid, zerolinecolor: "rgba(56, 189, 248, 0.15)", tickfont: { color: muted, size: 10 }, titlefont: { color: muted, size: 10.5 }, automargin: true },
        legend: { orientation: "h", y: -0.22, font: { color: muted, size: 10 } },
    };

    const render = (id, traces, layout = {}) => {
        const element = document.getElementById(id);
        if (!element || !window.Plotly) return;
        Plotly.newPlot(element, traces, { ...baseLayout, ...layout }, config);
    };

    if (window.Plotly && Object.keys(series).length) {
        // Ultra-futuristic Cybernetic Neon Palette
        const colors = {
            actual: "#00e5ff",       // Electric Cyan
            trend: "#a855f7",        // Electric Violet
            rolling: "#38bdf8",      // Sky Glow
            good: "#10b981",         // Laser Emerald
            bad: "#f43f5e",          // Neon Crimson
            missing: "#64748b",      // Slate Muted
            pending: "#f59e0b",      // Cyber Amber
            unconfigured: "#818cf8", // Tech Indigo
            forecast: "#c084fc",     // Purple Glow
            specLine: "#fb7185",     // Rose boundary
            sigmaLine: "#38bdf8"     // Statistical bound
        };
        const complianceColors = (series.status || []).map(status =>
            status === "Out of range" ? colors.bad :
            status === "No limit configured" ? colors.unconfigured :
            status === "Missing" ? colors.missing :
            ["Pending entry", "Verify historical value"].includes(status) ? colors.pending : colors.good
        );
        const complianceSymbols = (series.status || []).map(status =>
            status === "Out of range" ? "x" :
            status === "No limit configured" ? "diamond" :
            ["Pending entry", "Verify historical value"].includes(status) ? "triangle-up" : "circle"
        );

        // 1. Interactive Trend + Specifications Plot
        const trendTraces = [
            {
                type: "scatter", mode: "markers", name: "Observed Results", x: series.x, y: series.y,
                marker: { color: complianceColors, symbol: complianceSymbols, size: 7.5, opacity: .9, line: { color: "#061325", width: 1.5 } },
                customdata: series.reference || [],
                hovertemplate: "<b>%{y:.5g} " + (series.unit || "") + "</b><br>Observed: %{x}<br>Sample: %{customdata}<extra></extra>",
            },
            {
                type: "scatter", mode: "lines", name: "Rolling Mean", x: series.x, y: series.rolling,
                line: { color: colors.rolling, width: 2.2, shape: "spline" },
                fill: "tozeroy", fillcolor: "rgba(56, 189, 248, 0.04)",
                hovertemplate: "Rolling Mean: %{y:.5g}<br>%{x}<extra></extra>"
            },
        ];
        if (series.trend?.length) {
            trendTraces.push({
                type: "scatter", mode: "lines", name: "Process Trend (OLS)", x: series.x, y: series.trend,
                line: { color: colors.trend, width: 2, dash: "dash" },
                hovertemplate: "Process Trend: %{y:.5g}<br>%{x}<extra></extra>"
            });
        }
        if (series.forecast?.length) {
            const forecastX = series.forecast.map(item => item.period);
            trendTraces.push({
                type: "scatter", mode: "lines", name: "Upper Projection (95%)", x: forecastX, y: series.forecast.map(item => item.high),
                line: { width: 0 }, showlegend: false, hoverinfo: "skip"
            });
            trendTraces.push({
                type: "scatter", mode: "lines", name: "Forecast 95% Band", x: forecastX, y: series.forecast.map(item => item.low),
                line: { color: "rgba(168, 85, 247, 0.35)", width: 1 }, fill: "tonexty", fillcolor: "rgba(168, 85, 247, 0.14)",
                hovertemplate: "95% Interval: [%{y:.5g} - %{customdata:.5g}]<extra></extra>",
                customdata: series.forecast.map(item => item.high)
            });
            trendTraces.push({
                type: "scatter", mode: "lines+markers", name: "Forecast Trajectory", x: forecastX, y: series.forecast.map(item => item.mean),
                line: { color: colors.forecast, width: 2.2, dash: "dot" }, marker: { symbol: "diamond", size: 6, color: colors.forecast },
                hovertemplate: "Forecast: %{y:.5g} " + (series.unit || "") + "<br>%{x}<extra></extra>"
            });
        }

        const trendShapes = [];
        if (series.lower_limit !== null && series.lower_limit !== undefined) {
            trendShapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: series.lower_limit, y1: series.lower_limit, line: { color: colors.bad, dash: "dashdot", width: 1.5 } });
        }
        if (series.upper_limit !== null && series.upper_limit !== undefined) {
            trendShapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: series.upper_limit, y1: series.upper_limit, line: { color: colors.bad, dash: "dashdot", width: 1.5 } });
        }

        render("qcrTrendChart", trendTraces, {
            xaxis: { ...baseLayout.xaxis, type: "date", rangeslider: { visible: true, thickness: .07, bgcolor: "rgba(8, 28, 48, 0.55)", bordercolor: "rgba(56, 189, 248, 0.2)" } },
            yaxis: { ...baseLayout.yaxis, title: series.unit || "Measured Value" },
            shapes: trendShapes,
        });

        // 2. Compliance Composition Doughnut Chart
        const totalEvaluated = ((payload.distribution?.compliant || 0) + (payload.distribution?.out_of_range || 0));
        const compRate = totalEvaluated > 0 ? (((payload.distribution?.compliant || 0) / totalEvaluated) * 100).toFixed(1) : "—";
        render("qcrComplianceChart", [{
            type: "pie", hole: .70, sort: false, direction: "clockwise", rotation: 30,
            labels: ["Within Limits", "Out of Range", "Missing", "Pending Entry", "Historical Unverified", "No Limit Configured"],
            values: [payload.distribution?.compliant || 0, payload.distribution?.out_of_range || 0, payload.distribution?.missing || 0, payload.distribution?.pending || 0, payload.distribution?.legacy_unverified || 0, payload.distribution?.not_evaluated || 0],
            marker: { colors: [colors.good, colors.bad, colors.missing, colors.pending, "#c084fc", colors.unconfigured], line: { color: "#071220", width: 2.5 } },
            textinfo: "percent", textposition: "inside", insidetextfont: { color: "#fff", family: "'JetBrains Mono', monospace", size: 10 },
            hovertemplate: "<b>%{label}</b><br>Count: %{value:,}<br>Share: %{percent}<extra></extra>",
        }], {
            showlegend: true, legend: { ...baseLayout.legend, y: -.14 }, margin: { l: 12, r: 12, t: 8, b: 24 },
            annotations: [{ text: `<b style="font-size:1.35rem;color:#10b981;">${compRate}%</b><br><span style="font-size:9.5px;color:#94a3b8;letter-spacing:0.08em;">COMPLIANCE</span>`, showarrow: false, font: { family: "'JetBrains Mono', monospace", color: ink } }]
        });

        // 3. Period Comparison Compound Bar + Mean Line
        const periodTraces = [
            { type: "bar", name: "In Spec", x: series.period_labels || series.periods, y: series.period_within, marker: { color: "rgba(16, 185, 129, 0.85)", line: { color: "#10b981", width: 1 } }, hovertemplate: "%{x}<br>In Range: %{y:,}<extra></extra>" },
            { type: "bar", name: "Out of Spec", x: series.period_labels || series.periods, y: series.period_out, marker: { color: "rgba(244, 63, 94, 0.85)", line: { color: "#f43f5e", width: 1 } }, hovertemplate: "%{x}<br>Out of Range: %{y:,}<extra></extra>" },
            { type: "scatter", mode: "lines+markers", name: "Period Mean", x: series.period_labels || series.periods, y: series.period_mean, yaxis: "y2", line: { color: colors.actual, width: 2.2 }, marker: { size: 6, color: colors.actual, symbol: "circle" }, hovertemplate: "%{x}<br>Mean: %{y:.5g} " + (series.unit || "") + "<extra></extra>" },
        ];
        render("qcrPeriodChart", periodTraces, {
            barmode: "stack",
            yaxis: { ...baseLayout.yaxis, title: "Evaluated Count" },
            yaxis2: { title: `Mean (${series.unit || "Value"})`, overlaying: "y", side: "right", showgrid: false, tickfont: { color: muted, size: 9.5 } },
            xaxis: { ...baseLayout.xaxis, tickangle: -24 },
            legend: { ...baseLayout.legend, y: -.28 }
        });

        // 4. Distribution Density & Phase Violin Plots
        const distributionTraces = [{
            type: "histogram", x: payload.distribution?.values || [], name: "Probability Density", histnorm: "probability density",
            marker: { color: "rgba(0, 229, 255, 0.35)", line: { color: "#00e5ff", width: 1.2 } }, nbinsx: 34,
            hovertemplate: "Value: %{x:.5g}<br>Density: %{y:.4f}<extra></extra>"
        }];
        const boxes = series.phase_boxes || [];
        if (boxes.length) {
            const phasePalette = ["#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ec4899"];
            boxes.forEach((box, index) => {
                const color = phasePalette[index % phasePalette.length];
                distributionTraces.push({
                    type: "violin", name: box.label, x: Array(box.values.length).fill(box.label), y: box.values,
                    xaxis: "x2", yaxis: "y2", side: "both", box: { visible: true, width: 0.3 }, meanline: { visible: true }, points: false,
                    opacity: .7, line: { color: color, width: 1.5 }, fillcolor: color.replace(")", ", 0.16)").replace("rgb", "rgba"),
                    hovertemplate: `<b>${box.label}</b><br>Value: %{y:.5g}<extra></extra>`
                });
            });
        }
        render("qcrDistributionChart", distributionTraces, {
            grid: { rows: 1, columns: 2, pattern: "independent", xgap: .1 },
            xaxis: { ...baseLayout.xaxis, domain: boxes.length ? [0, .47] : [0, 1], title: `Distribution (${series.unit || ""})` },
            yaxis: { ...baseLayout.yaxis, title: "Density" },
            xaxis2: { ...baseLayout.xaxis, domain: [.55, 1], title: "Treatment Phase" },
            yaxis2: { ...baseLayout.yaxis, anchor: "x2", title: `Result (${series.unit || ""})`, showgrid: false },
            showlegend: boxes.length > 1,
            legend: { ...baseLayout.legend, y: -.22 }
        });

        // 5. Compliance Heatmap
        const heatX = series.heatmap_x?.length ? series.heatmap_x : (series.period_labels || series.periods || []);
        let heatY = series.heatmap_y || [];
        let heatZ = series.heatmap_z || [];
        if (!heatY.length && series.periods?.length) {
            heatY = [payload.focus_parameter || "Compliance"];
            heatZ = [series.period_compliance || []];
        }
        render("qcrHeatmapChart", [{
            type: "heatmap", x: heatX, y: heatY, z: heatZ, zmin: 0, zmax: 100,
            colorscale: [
                [0, "#be123c"],
                [0.4, "#f97316"],
                [0.7, "#eab308"],
                [0.85, "#10b981"],
                [1.0, "#00e5ff"]
            ],
            colorbar: { title: "Compliance %", ticksuffix: "%", tickfont: { color: muted, size: 9.5 }, thickness: 12 },
            hovertemplate: "<b>%{y}</b><br>%{x}<br>Compliance: <b>%{z:.1f}%</b><extra></extra>"
        }], {
            margin: { l: 85, r: 25, t: 14, b: 58 },
            xaxis: { ...baseLayout.xaxis, tickangle: -30 },
            yaxis: { ...baseLayout.yaxis, title: "" }
        });

        // 6. Forecast Fan Chart
        const forecast = series.forecast || [];
        const histX = series.periods || [];
        const histY = series.period_mean || [];
        const forecastTraces = [{
            type: "scatter", mode: "lines+markers", name: "Historical Interval Mean", x: histX, y: histY,
            line: { color: colors.actual, width: 2.2 }, marker: { color: colors.actual, size: 5.5 },
            hovertemplate: "Historical: %{y:.5g}<br>%{x}<extra></extra>"
        }];
        if (forecast.length) {
            const fx = forecast.map(item => item.period);
            forecastTraces.push({
                type: "scatter", mode: "lines", name: "Upper Band", x: fx, y: forecast.map(item => item.high),
                line: { width: 0 }, showlegend: false, hoverinfo: "skip"
            });
            forecastTraces.push({
                type: "scatter", mode: "lines", name: "Approx. 95% Uncertainty", x: fx, y: forecast.map(item => item.low),
                line: { color: "rgba(168, 85, 247, 0.3)", width: 1 }, fill: "tonexty", fillcolor: "rgba(168, 85, 247, 0.15)",
                hovertemplate: "95% Interval: [%{y:.5g} - %{customdata:.5g}]<extra></extra>",
                customdata: forecast.map(item => item.high)
            });
            forecastTraces.push({
                type: "scatter", mode: "lines+markers", name: "Damped Trend Projection", x: fx, y: forecast.map(item => item.mean),
                line: { color: colors.forecast, width: 2.2, dash: "dash" }, marker: { symbol: "diamond", size: 6.5, color: colors.forecast },
                hovertemplate: "Forecast: %{y:.5g}<br>%{x}<extra></extra>"
            });
        }
        render("qcrForecastChart", forecastTraces, {
            xaxis: { ...baseLayout.xaxis, type: "date", tickangle: -28 },
            yaxis: { ...baseLayout.yaxis, title: series.unit || "Measured Value" },
            legend: { ...baseLayout.legend, y: -.24 }
        });

        // 7. Stage Comparison Bar + Line
        const stageData = payload.stage_comparison || [];
        const stageColors = ["#00e5ff", "#a855f7", "#f59e0b", "#10b981", "#ec4899", "#3b82f6"];
        render("qcrStageChart", [
            {
                type: "bar", name: "Stage Mean", x: stageData.map(item => item.label), y: stageData.map(item => item.mean),
                marker: { color: stageData.map((_, i) => stageColors[i % stageColors.length]) },
                error_y: {
                    type: "data", symmetric: false,
                    array: stageData.map(item => item.ci_high != null ? Math.max(0, item.ci_high - item.mean) : 0),
                    arrayminus: stageData.map(item => item.ci_low != null ? Math.max(0, item.mean - item.ci_low) : 0),
                    color: "rgba(224, 242, 254, 0.45)", thickness: 1.5, width: 4
                },
                hovertemplate: "<b>%{x}</b><br>Mean: %{y:.5g} " + (series.unit || "") + "<extra></extra>"
            },
            {
                type: "scatter", mode: "lines+markers", name: "Compliance %", x: stageData.map(item => item.label), y: stageData.map(item => item.compliance_rate),
                yaxis: "y2", line: { color: "#10b981", width: 2.2 }, marker: { color: "#10b981", size: 7, symbol: "diamond" },
                hovertemplate: "<b>%{x}</b><br>Compliance: <b>%{y:.1f}%</b><extra></extra>"
            },
        ], {
            barmode: "group",
            yaxis: { ...baseLayout.yaxis, title: `Mean (${series.unit || "Value"})` },
            yaxis2: { title: "Compliance %", overlaying: "y", side: "right", range: [0, 100], showgrid: false, ticksuffix: "%", tickfont: { color: muted, size: 9.5 } },
            xaxis: { ...baseLayout.xaxis, tickangle: -18 },
            legend: { ...baseLayout.legend, y: -.22 }
        });

        // 8. Multivariate Correlation Matrix
        const multivariate = payload.multivariate || {};
        if ((multivariate.parameters || []).length > 1) {
            render("qcrCorrelationChart", [{
                type: "heatmap", x: multivariate.parameters, y: multivariate.parameters,
                z: multivariate.spearman_matrix || multivariate.pearson_matrix,
                customdata: multivariate.sample_size_matrix || [], zmin: -1, zmax: 1,
                colorscale: [
                    [0, "#be123c"],
                    [0.25, "#fb7185"],
                    [0.5, "#0b1d33"],
                    [0.75, "#2dd4bf"],
                    [1, "#00e5ff"]
                ],
                colorbar: { title: "Spearman ρ", tickfont: { color: muted, size: 9.5 }, thickness: 12 },
                hovertemplate: "<b>%{y} × %{x}</b><br>Spearman ρ: <b>%{z:.3f}</b><br>Paired Samples: %{customdata}<extra></extra>",
            }], {
                margin: { l: 95, r: 35, t: 15, b: 90 },
                xaxis: { ...baseLayout.xaxis, tickangle: -35 },
                yaxis: { ...baseLayout.yaxis, autorange: "reversed" }
            });
        }

        // 9. PCA Score Map
        const pca = multivariate.pca || {};
        if (pca.available && (pca.scores || []).length) {
            const variance = pca.explained_variance || [];
            const varianceText = `${((variance[0] || 0) * 100).toFixed(1)}% / ${((variance[1] || 0) * 100).toFixed(1)}%`;
            render("qcrPcaChart", [{
                type: "scattergl", mode: "markers", name: "Sample PC Scores",
                x: pca.scores.map(item => item.pc1), y: pca.scores.map(item => item.pc2),
                text: pca.scores.map(item => item.sample_id),
                marker: { size: 7.5, opacity: .82, color: pca.scores.map(item => item.pc1), colorscale: "Viridis", showscale: true, colorbar: { title: "PC1 Score", tickfont: { color: muted, size: 9.5 }, thickness: 12 } },
                hovertemplate: "<b>Sample %{text}</b><br>PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>",
            }], {
                xaxis: { ...baseLayout.xaxis, title: `PC1 (${((variance[0] || 0) * 100).toFixed(1)}% Variance)` },
                yaxis: { ...baseLayout.yaxis, title: `PC2 (${((variance[1] || 0) * 100).toFixed(1)}% Variance)` },
                annotations: [{ text: `PC1 / PC2 explain ${varianceText} variance`, showarrow: false, xref: "paper", yref: "paper", x: 1, y: 1.1, xanchor: "right", font: { color: muted, size: 9.5 } }]
            });
            render("qcrPcaLoadingsChart", [
                { type: "bar", name: "PC1 Loading", x: pca.loadings.map(item => item.parameter), y: pca.loadings.map(item => item.pc1), marker: { color: "#00e5ff" }, hovertemplate: "<b>%{x}</b><br>PC1 Loading: %{y:.3f}<extra></extra>" },
                { type: "bar", name: "PC2 Loading", x: pca.loadings.map(item => item.parameter), y: pca.loadings.map(item => item.pc2), marker: { color: "#a855f7" }, hovertemplate: "<b>%{x}</b><br>PC2 Loading: %{y:.3f}<extra></extra>" },
            ], { barmode: "group", xaxis: { ...baseLayout.xaxis, tickangle: -28 }, yaxis: { ...baseLayout.yaxis, title: "Standardized Loading" }, legend: { ...baseLayout.legend, y: -.26 } });
        }

        // Global Chart Action Buttons
        document.querySelector('[data-qcr-chart-action="reset"]')?.addEventListener("click", () => {
            document.querySelectorAll(".qcr-chart").forEach(chart => { if (chart.data) Plotly.relayout(chart, { "xaxis.autorange": true, "yaxis.autorange": true }); });
        });
        document.querySelector('[data-qcr-chart-action="download"]')?.addEventListener("click", () => {
            const chart = document.getElementById("qcrTrendChart");
            if (chart?.data) Plotly.downloadImage(chart, { format: "png", filename: `qca-${(payload.focus_parameter || "analytics").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-trend`, width: 1920, height: 960, scale: 2 });
        });

        document.querySelector('[data-qcr-chart-action="reset"]')?.addEventListener("click", () => {
            document.querySelectorAll(".qcr-chart").forEach(chart => { if (chart.data) Plotly.relayout(chart, { "xaxis.autorange": true, "yaxis.autorange": true }); });
        });
        document.querySelector('[data-qcr-chart-action="download"]')?.addEventListener("click", () => {
            const chart = document.getElementById("qcrTrendChart");
            if (chart?.data) Plotly.downloadImage(chart, { format: "png", filename: `qca-${(payload.focus_parameter || "analytics").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-trend`, width: 1800, height: 900, scale: 2 });
        });
    }
})();
