/**
 * Chemical Analysis (CA) Advanced Analytics & Chart Engine
 * Lightweight, progressive, responsive SVG chart renderers for CA Dashboards
 */
(function(window) {
    "use strict";

    // Tooltip singleton
    let tooltipEl = null;
    function getTooltip() {
        if (!tooltipEl) {
            tooltipEl = document.createElement("div");
            tooltipEl.className = "ca-chart-tooltip";
            tooltipEl.style.cssText = "position:fixed;z-index:9999;pointer-events:none;padding:8px 12px;background:rgba(15,23,42,0.92);backdrop-filter:blur(8px);border:1px solid rgba(148,163,184,0.2);border-radius:8px;color:#f8fafc;font-size:12px;box-shadow:0 10px 25px -5px rgba(0,0,0,0.5);display:none;transition:opacity 0.15s ease,transform 0.15s ease;font-family:system-ui,-apple-system,sans-serif;";
            document.body.appendChild(tooltipEl);
        }
        return tooltipEl;
    }

    function showTooltip(x, y, html) {
        const tip = getTooltip();
        tip.innerHTML = html;
        tip.style.display = "block";
        tip.style.opacity = "1";
        const rect = tip.getBoundingClientRect();
        const posX = Math.min(x + 12, window.innerWidth - rect.width - 16);
        const posY = Math.max(16, y - rect.height - 10);
        tip.style.left = `${posX}px`;
        tip.style.top = `${posY}px`;
    }

    function hideTooltip() {
        if (tooltipEl) {
            tooltipEl.style.opacity = "0";
            tooltipEl.style.display = "none";
        }
    }

    /**
     * Compute smooth cubic bezier path for points
     */
    function getSplinePath(points) {
        if (!points || points.length === 0) return "";
        if (points.length === 1) return `M ${points[0].x},${points[0].y}`;
        if (points.length === 2) return `M ${points[0].x},${points[0].y} L ${points[1].x},${points[1].y}`;

        let d = `M ${points[0].x},${points[0].y}`;
        for (let i = 0; i < points.length - 1; i++) {
            const p0 = i > 0 ? points[i - 1] : points[i];
            const p1 = points[i];
            const p2 = points[i + 1];
            const p3 = i < points.length - 2 ? points[i + 2] : p2;

            const cp1x = p1.x + (p2.x - p0.x) / 6;
            const cp1y = p1.y + (p2.y - p0.y) / 6;
            const cp2x = p2.x - (p3.x - p1.x) / 6;
            const cp2y = p2.y - (p3.y - p1.y) / 6;

            d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
        }
        return d;
    }

    const CACharts = {
        /**
         * Render Progressive Multi-Series Line Chart with Area Gradients & Hover Crosshair
         */
        renderProgressiveLine(container, options = {}) {
            if (!container) return;
            const dates = options.dates || [];
            const seriesList = options.series || [];
            const width = options.width || container.clientWidth || 600;
            const height = options.height || container.clientHeight || 260;
            const padding = { top: 30, right: 24, bottom: 40, left: 44 };

            if (!dates.length || !seriesList.length) {
                container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:${height}px;color:#94a3b8;font-size:13px;">No analytical timeline data available</div>`;
                return;
            }

            // Calculate max value across all series
            let maxVal = 1;
            seriesList.forEach(s => {
                const sMax = Math.max(...(s.data || [0]));
                if (sMax > maxVal) maxVal = sMax;
            });
            // Round maxVal up to pleasant interval
            maxVal = Math.ceil(maxVal * 1.15) || 5;

            const chartW = width - padding.left - padding.right;
            const chartH = height - padding.top - padding.bottom;
            const numPoints = dates.length;
            const stepX = chartW / Math.max(numPoints - 1, 1);

            const uid = "ca-line-" + Math.random().toString(36).substr(2, 6);

            // Gradients definitions
            let defs = `<defs>`;
            seriesList.forEach((s, idx) => {
                const col = s.color || "#3b82f6";
                defs += `
                    <linearGradient id="${uid}-grad-${idx}" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="${col}" stop-opacity="0.32" />
                        <stop offset="95%" stop-color="${col}" stop-opacity="0.01" />
                    </linearGradient>
                `;
            });
            defs += `</defs>`;

            // Background grid lines (Y-axis)
            let gridY = "";
            const yTicks = 4;
            for (let i = 0; i <= yTicks; i++) {
                const val = Math.round((maxVal / yTicks) * i);
                const y = padding.top + chartH - (i / yTicks) * chartH;
                gridY += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="rgba(148,163,184,0.12)" stroke-dasharray="3,3" />`;
                gridY += `<text x="${padding.left - 8}" y="${y + 4}" font-size="10" fill="#64748b" text-anchor="end" font-family="system-ui">${val}</text>`;
            }

            // X-axis date labels (show ~5 to 7 labels)
            let gridX = "";
            const xLabelInterval = Math.max(1, Math.floor(numPoints / 6));
            dates.forEach((d, i) => {
                if (i % xLabelInterval === 0 || i === numPoints - 1) {
                    const x = padding.left + i * stepX;
                    const dateStr = d.length > 5 ? d.slice(5) : d; // MM-DD
                    gridX += `<text x="${x}" y="${height - padding.bottom + 18}" font-size="10" fill="#64748b" text-anchor="middle" font-family="system-ui">${dateStr}</text>`;
                }
            });

            // Series Paths & Markers
            let pathsSvg = "";
            const seriesCoords = [];

            seriesList.forEach((s, idx) => {
                const col = s.color || "#3b82f6";
                const coords = (s.data || []).map((val, i) => {
                    const x = padding.left + i * stepX;
                    const y = padding.top + chartH - ((val || 0) / maxVal) * chartH;
                    return { x, y, val, date: dates[i] };
                });
                seriesCoords.push({ series: s, coords });

                const lineD = getSplinePath(coords);
                const firstX = coords[0].x;
                const lastX = coords[coords.length - 1].x;
                const baseY = padding.top + chartH;
                const areaD = `${lineD} L ${lastX},${baseY} L ${firstX},${baseY} Z`;

                // Fill path
                pathsSvg += `<path d="${areaD}" fill="url(#${uid}-grad-${idx})" />`;
                // Stroke path with smooth progressive animation
                pathsSvg += `<path class="ca-chart-line-stroke" d="${lineD}" fill="none" stroke="${col}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />`;

                // Key point markers
                coords.forEach((pt, i) => {
                    if (coords.length <= 15 || i % 2 === 0 || i === coords.length - 1) {
                        pathsSvg += `<circle cx="${pt.x}" cy="${pt.y}" r="3.5" fill="#0f172a" stroke="${col}" stroke-width="2" class="ca-chart-dot" data-val="${pt.val}" data-series="${s.name}" data-date="${pt.date}" />`;
                    }
                });
            });

            // Interactive crosshair element & overlay rect
            const crosshairSvg = `
                <line id="${uid}-crosshair" x1="0" y1="${padding.top}" x2="0" y2="${padding.top + chartH}" stroke="rgba(148,163,184,0.3)" stroke-width="1.5" stroke-dasharray="2,2" style="display:none;" />
                <rect class="ca-chart-overlay" x="${padding.left}" y="${padding.top}" width="${chartW}" height="${chartH}" fill="transparent" style="cursor:crosshair;" />
            `;

            const fullSvg = `
                <svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" style="overflow:visible;" id="${uid}-svg">
                    ${defs}
                    ${gridY}
                    ${gridX}
                    ${pathsSvg}
                    ${crosshairSvg}
                </svg>
            `;

            container.innerHTML = fullSvg;

            // Bind crosshair & tooltip
            const svgEl = document.getElementById(`${uid}-svg`);
            const crosshair = document.getElementById(`${uid}-crosshair`);
            const overlay = svgEl ? svgEl.querySelector(".ca-chart-overlay") : null;

            if (overlay && crosshair) {
                overlay.addEventListener("mousemove", (e) => {
                    const rect = svgEl.getBoundingClientRect();
                    const scaleX = width / rect.width;
                    const mouseSvgX = (e.clientX - rect.left) * scaleX;

                    // Find closest date index
                    const relX = mouseSvgX - padding.left;
                    let closestIdx = Math.round(relX / stepX);
                    closestIdx = Math.max(0, Math.min(numPoints - 1, closestIdx));

                    const snapX = padding.left + closestIdx * stepX;
                    crosshair.setAttribute("x1", snapX);
                    crosshair.setAttribute("x2", snapX);
                    crosshair.style.display = "block";

                    const dateVal = dates[closestIdx];
                    let tipHtml = `<div style="font-weight:700;margin-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:3px;color:#93c5fd;">${dateVal}</div>`;
                    seriesCoords.forEach(({ series, coords }) => {
                        const pt = coords[closestIdx];
                        const col = series.color || "#3b82f6";
                        tipHtml += `
                            <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin:3px 0;">
                                <span style="display:inline-flex;align-items:center;gap:6px;">
                                    <span style="width:8px;height:8px;border-radius:50%;background:${col};display:inline-block;"></span>
                                    <span>${series.name}</span>
                                </span>
                                <strong style="color:#fff;font-family:monospace;">${pt ? pt.val : 0}</strong>
                            </div>
                        `;
                    });

                    showTooltip(e.clientX, e.clientY, tipHtml);
                });

                overlay.addEventListener("mouseleave", () => {
                    crosshair.style.display = "none";
                    hideTooltip();
                });
            }
        },

        /**
         * Render Progressive Bar Chart (Horizontal or Vertical)
         */
        renderBar(container, data = [], options = {}) {
            if (!container) return;
            const width = options.width || container.clientWidth || 360;
            const height = options.height || container.clientHeight || 220;
            const isHorizontal = options.horizontal || false;
            const padding = isHorizontal
                ? { top: 16, right: 36, bottom: 20, left: 88 }
                : { top: 24, right: 16, bottom: 36, left: 36 };

            if (!data.length) {
                container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:${height}px;color:#94a3b8;font-size:13px;">No data available</div>`;
                return;
            }

            const values = data.map(d => Number(d.value ?? d) || 0);
            const labels = data.map((d, i) => d.label ?? `Item ${i + 1}`);
            const colors = options.colors || ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#06b6d4"];
            const maxVal = Math.max(...values, 1);

            let svgContent = "";
            const uid = "ca-bar-" + Math.random().toString(36).substr(2, 6);

            if (isHorizontal) {
                const chartW = width - padding.left - padding.right;
                const barHeight = Math.max(10, Math.min(22, (height - padding.top - padding.bottom) / values.length - 8));
                const stepY = (height - padding.top - padding.bottom) / values.length;

                values.forEach((val, i) => {
                    const barW = (val / maxVal) * chartW;
                    const y = padding.top + i * stepY + (stepY - barHeight) / 2;
                    const color = data[i].color || colors[i % colors.length];

                    svgContent += `
                        <text x="${padding.left - 10}" y="${y + barHeight / 2 + 4}" font-size="11" fill="#94a3b8" text-anchor="end" font-family="system-ui">${labels[i]}</text>
                        <rect x="${padding.left}" y="${y}" width="${Math.max(barW, 2)}" height="${barHeight}" rx="4" fill="${color}" opacity="0.88" class="ca-chart-bar" data-label="${labels[i]}" data-val="${val}">
                            <animate attributeName="width" from="0" to="${Math.max(barW, 2)}" dur="0.5s" fill="freeze" />
                        </rect>
                        <text x="${padding.left + barW + 6}" y="${y + barHeight / 2 + 4}" font-size="11" font-weight="700" fill="#f8fafc" font-family="monospace">${val}</text>
                    `;
                });
            } else {
                const chartH = height - padding.top - padding.bottom;
                const chartW = width - padding.left - padding.right;
                const barWidth = Math.max(12, Math.min(36, (chartW / values.length) - 10));
                const stepX = chartW / values.length;

                // Subtle horizontal gridlines
                for (let j = 0; j <= 3; j++) {
                    const gridY = padding.top + chartH - (j / 3) * chartH;
                    const val = Math.round((maxVal / 3) * j);
                    svgContent += `<line x1="${padding.left}" y1="${gridY}" x2="${width - padding.right}" y2="${gridY}" stroke="rgba(148,163,184,0.1)" stroke-dasharray="2,2" />`;
                    svgContent += `<text x="${padding.left - 6}" y="${gridY + 3}" font-size="9" fill="#64748b" text-anchor="end">${val}</text>`;
                }

                values.forEach((val, i) => {
                    const barH = (val / maxVal) * chartH;
                    const x = padding.left + i * stepX + (stepX - barWidth) / 2;
                    const y = padding.top + chartH - barH;
                    const color = data[i].color || colors[i % colors.length];

                    svgContent += `
                        <rect x="${x}" y="${y}" width="${barWidth}" height="${barH}" rx="4" fill="${color}" opacity="0.9" class="ca-chart-bar" data-label="${labels[i]}" data-val="${val}">
                            <animate attributeName="height" from="0" to="${barH}" dur="0.45s" fill="freeze" />
                            <animate attributeName="y" from="${padding.top + chartH}" to="${y}" dur="0.45s" fill="freeze" />
                        </rect>
                        <text x="${x + barWidth / 2}" y="${y - 4}" font-size="10" font-weight="700" fill="#e2e8f0" text-anchor="middle" font-family="monospace">${val}</text>
                        <text x="${x + barWidth / 2}" y="${height - padding.bottom + 16}" font-size="10" fill="#94a3b8" text-anchor="middle" font-family="system-ui">${labels[i]}</text>
                    `;
                });
            }

            container.innerHTML = `
                <svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" style="overflow:visible;" id="${uid}">
                    ${svgContent}
                </svg>
            `;

            // Hover tooltip on bars
            const bars = container.querySelectorAll(".ca-chart-bar");
            bars.forEach(b => {
                b.addEventListener("mouseenter", (e) => {
                    const l = b.getAttribute("data-label");
                    const v = b.getAttribute("data-val");
                    showTooltip(e.clientX, e.clientY, `<strong>${l}</strong>: <span style="font-family:monospace;color:#60a5fa">${v}</span>`);
                });
                b.addEventListener("mouseleave", hideTooltip);
            });
        },

        /**
         * Render Donut Chart with Center Metric & Segment Hover
         */
        renderDonut(container, data = [], options = {}) {
            if (!container) return;
            const size = options.size || Math.min(container.clientWidth || 220, container.clientHeight || 220);
            const strokeWidth = options.strokeWidth || 18;
            const radius = (size - strokeWidth) / 2 - 4;
            const circumference = 2 * Math.PI * radius;
            const centerTitle = options.centerTitle || "";
            const centerSubtitle = options.centerSubtitle || "";

            const total = data.reduce((acc, d) => acc + (Number(d.value ?? d) || 0), 0) || 1;
            const colors = options.colors || ["#10b981", "#ef4444", "#f59e0b", "#3b82f6", "#8b5cf6"];

            let offset = 0;
            let circles = "";

            data.forEach((d, i) => {
                const val = Number(d.value ?? d) || 0;
                const ratio = val / total;
                const dash = ratio * circumference;
                const color = d.color || colors[i % colors.length];
                const label = d.label || `Segment ${i + 1}`;
                const pct = ((ratio * 100) || 0).toFixed(1);

                circles += `
                    <circle cx="${size / 2}" cy="${size / 2}" r="${radius}"
                        fill="none" stroke="${color}" stroke-width="${strokeWidth}"
                        stroke-dasharray="${dash} ${circumference - dash}"
                        stroke-dashoffset="${-offset}"
                        stroke-linecap="round"
                        class="ca-donut-seg"
                        data-label="${label}" data-val="${val}" data-pct="${pct}"
                        style="transition:stroke-width 0.2s ease, opacity 0.2s ease; cursor:pointer;"
                    />
                `;
                offset += dash;
            });

            const centerSvg = `
                <g style="transform: rotate(90deg); transform-origin: center;">
                    <text x="${size / 2}" y="${size / 2 - 2}" text-anchor="middle" font-size="20" font-weight="800" fill="#f8fafc" font-family="monospace">${centerTitle}</text>
                    <text x="${size / 2}" y="${size / 2 + 16}" text-anchor="middle" font-size="10" font-weight="600" fill="#94a3b8" letter-spacing="0.05em" text-transform="uppercase">${centerSubtitle}</text>
                </g>
            `;

            container.innerHTML = `
                <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg" style="transform: rotate(-90deg); transform-origin: center; display:block; margin:0 auto;">
                    <circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="rgba(148,163,184,0.08)" stroke-width="${strokeWidth}" />
                    ${circles}
                    ${centerSvg}
                </svg>
            `;

            // Tooltips
            const segs = container.querySelectorAll(".ca-donut-seg");
            segs.forEach(s => {
                s.addEventListener("mouseenter", (e) => {
                    s.setAttribute("stroke-width", strokeWidth + 4);
                    const l = s.getAttribute("data-label");
                    const v = s.getAttribute("data-val");
                    const p = s.getAttribute("data-pct");
                    showTooltip(e.clientX, e.clientY, `<strong>${l}</strong>: <span style="font-family:monospace;color:#60a5fa">${v}</span> (${p}%)`);
                });
                s.addEventListener("mouseleave", () => {
                    s.setAttribute("stroke-width", strokeWidth);
                    hideTooltip();
                });
            });
        },

        /**
         * Render Workflow Aging Matrix Bar
         */
        renderAgingBar(container, buckets = {}, options = {}) {
            if (!container) return;
            const data = [
                { label: "< 3 Hours", value: buckets.under_3h || 0, color: "#10b981" },
                { label: "3 - 9h", value: buckets["3_to_9h"] || 0, color: "#3b82f6" },
                { label: "9 - 24h", value: buckets["9_to_24h"] || 0, color: "#f59e0b" },
                { label: "1 - 3 Days", value: buckets["1_to_3d"] || 0, color: "#f97316" },
                { label: "> 3 Days (Critical)", value: buckets.over_3d || 0, color: "#ef4444" }
            ];
            this.renderBar(container, data, {
                horizontal: true,
                height: options.height || 210,
                width: options.width || container.clientWidth
            });
        },

        /**
         * Sparkline renderer for Metric Cards
         */
        renderSparkline(container, values = [], options = {}) {
            if (!container || !values.length) return;
            const width = options.width || container.clientWidth || 110;
            const height = options.height || container.clientHeight || 34;
            const min = Math.min(...values);
            const max = Math.max(...values);
            const range = max - min || 1;

            const points = values.map((v, i) => {
                const x = (i / Math.max(values.length - 1, 1)) * (width - 4) + 2;
                const y = height - (((v - min) / range) * (height - 8) + 4);
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            }).join(" ");

            const color = options.color || "#3b82f6";
            container.innerHTML = `
                <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
                    <polyline fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="${points}" opacity="0.9" />
                </svg>
            `;
        }
    };

    window.CACharts = CACharts;
})(window);
