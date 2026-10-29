/**
 * PH ADJUSTMENT & CHEMICAL NEUTRALIZATION ANALYTICAL DASHBOARD
 * Interactive SVG titration curve plotting, dynamic beaker color shifting,
 * reaction equilibration stopwatch, and plant feed rate scaler.
 */

document.addEventListener("DOMContentLoaded", () => {
    initPhChart();
    initPhPlantFeedCalc();
    initPhKeyboardShortcuts();
    initPhReportAnalytics();
});

// Helper for universal indicator color
function getUniversalIndicatorColor(ph) {
    if (ph < 5.5) return "#ef4444";       // Acidic red
    if (ph < 6.5) return "#f59e0b";       // Mild acid amber
    if (ph <= 7.5) return "#10b981";      // Neutral emerald
    if (ph <= 8.5) return "#06b6d4";      // Mild alkaline cyan
    return "#a855f7";                     // High alkaline purple
}

function getPhStatusText(ph) {
    if (ph < 5.5) return { label: "Acidic", cls: "status-acidic" };
    if (ph < 6.5) return { label: "Slightly Acidic", cls: "status-sub-neutral" };
    if (ph <= 7.5) return { label: "Optimal Neutral", cls: "status-optimal" };
    if (ph <= 8.5) return { label: "Mildly Alkaline", cls: "status-alkaline" };
    return { label: "High Alkaline", cls: "status-over-alkaline" };
}

// ==============================================================================
// 1. DYNAMIC SVG TITRATION CURVE PLOTTER
// ==============================================================================
function getPhJarPointsFromDOM() {
    const points = [];
    for (let i = 1; i <= 6; i++) {
        const doseEl = document.getElementById(`input-ph-dose-${i}`);
        const phEl = document.getElementById(`input-resulting-ph-${i}`);
        const cardEl = document.getElementById(`ph-jar-card-${i}`);
        if (doseEl && phEl) {
            const dose = parseFloat(doseEl.value) || 0;
            const ph = parseFloat(phEl.value) || 7.0;
            const isOpt = cardEl ? cardEl.classList.contains("is-optimal-card") : false;
            points.push({ jar: i, dosage: dose, ph: ph, is_optimal: isOpt });
        }
    }
    return points;
}

function initPhChart() {
    renderTitrationCurve();
}

function renderTitrationCurve() {
    const svg = document.getElementById("titrationCurveSvg");
    if (!svg) return;

    const points = getPhJarPointsFromDOM();
    if (points.length === 0) return;

    // ViewBox dimensions: 700 width, 280 height
    // Margin: Left 60, Right 670, Top 25, Bottom 240
    const xMin = 60;
    const xMax = 670;
    const yMin = 25;
    const yMax = 240;

    // Dose bounds
    let minDose = Math.min(...points.map(p => p.dosage), 0);
    let maxDose = Math.max(...points.map(p => p.dosage), 25.0);
    if (maxDose <= minDose) maxDose = minDose + 10.0;

    // pH bounds (range 5.0 to 9.0)
    const phMin = 5.0;
    const phMax = 9.0;

    // Scale mappings
    const scaleX = (d) => xMin + (((d - minDose) / (maxDose - minDose)) * (xMax - xMin));
    const scaleY = (ph) => {
        const clamped = Math.max(phMin, Math.min(phMax, ph));
        return yMax - (((clamped - phMin) / (phMax - phMin)) * (yMax - yMin));
    };

    const mapped = points.map(p => ({
        x: scaleX(p.dosage),
        y: scaleY(p.ph),
        color: getUniversalIndicatorColor(p.ph),
        raw: p
    }));

    // Build SVG Path string
    let pathD = "";
    let areaD = "";
    if (mapped.length > 0) {
        pathD = `M ${mapped[0].x} ${mapped[0].y}`;
        areaD = `M ${mapped[0].x} ${yMax} L ${mapped[0].x} ${mapped[0].y}`;

        for (let i = 0; i < mapped.length - 1; i++) {
            const curr = mapped[i];
            const next = mapped[i + 1];
            const cpX1 = curr.x + (next.x - curr.x) / 2;
            const cpY1 = curr.y;
            const cpX2 = curr.x + (next.x - curr.x) / 2;
            const cpY2 = next.y;
            pathD += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${next.x} ${next.y}`;
            areaD += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${next.x} ${next.y}`;
        }
        areaD += ` L ${mapped[mapped.length - 1].x} ${yMax} Z`;
    }

    const pathEl = document.getElementById("phCurvePath");
    const areaEl = document.getElementById("phAreaPath");
    if (pathEl) pathEl.setAttribute("d", pathD);
    if (areaEl) areaEl.setAttribute("d", areaD);

    // Render interactive circles
    const groupEl = document.getElementById("phPointsGroup");
    if (groupEl) {
        groupEl.innerHTML = "";
        mapped.forEach((pt) => {
            const g = document.createElementNS("http://www.w3.org/2000/svg", "g");

            if (pt.raw.is_optimal) {
                const halo = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                halo.setAttribute("cx", pt.x);
                halo.setAttribute("cy", pt.y);
                halo.setAttribute("r", "12");
                halo.setAttribute("fill", "rgba(16, 185, 129, 0.3)");
                halo.setAttribute("stroke", "#10b981");
                halo.setAttribute("stroke-width", "1.5");
                g.appendChild(halo);
            }

            const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            dot.setAttribute("cx", pt.x);
            dot.setAttribute("cy", pt.y);
            dot.setAttribute("r", pt.raw.is_optimal ? "6" : "4.5");
            dot.setAttribute("fill", pt.color);
            dot.setAttribute("stroke", "#0f172a");
            dot.setAttribute("stroke-width", "2");
            dot.style.cursor = "pointer";

            const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
            title.textContent = `Jar ${pt.raw.jar}: Dose ${pt.raw.dosage} mL -> Resulting pH ${pt.raw.ph}`;
            dot.appendChild(title);

            const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
            txt.setAttribute("x", pt.x);
            txt.setAttribute("y", pt.y - 10);
            txt.setAttribute("text-anchor", "middle");
            txt.setAttribute("fill", pt.color);
            txt.setAttribute("font-size", "10");
            txt.setAttribute("font-family", "JetBrains Mono");
            txt.setAttribute("font-weight", pt.raw.is_optimal ? "bold" : "normal");
            txt.textContent = `J${pt.raw.jar} (${pt.raw.ph})`;

            g.appendChild(dot);
            g.appendChild(txt);
            groupEl.appendChild(g);
        });
    }
}

// ==============================================================================
// 2. INTERACTIVE STEPPER & DYNAMIC RECALCULATION
// ==============================================================================
window.stepPhDose = function(jarNum, delta) {
    const input = document.getElementById(`input-ph-dose-${jarNum}`);
    if (input) {
        let val = parseFloat(input.value) || 0;
        val = Math.max(0, val + delta);
        input.value = val.toFixed(2);
        recalcPhJar(jarNum);
    }
};

window.stepResultingPh = function(jarNum, delta) {
    const input = document.getElementById(`input-resulting-ph-${jarNum}`);
    if (input) {
        let val = parseFloat(input.value) || 7.0;
        val = Math.max(0, Math.min(14, val + delta));
        input.value = val.toFixed(2);
        recalcPhJar(jarNum);
    }
};

window.recalcPhJar = function(jarNum) {
    const phInput = document.getElementById(`input-resulting-ph-${jarNum}`);
    const liquidEl = document.getElementById(`beaker-liquid-${jarNum}`);
    const statNumEl = document.getElementById(`ph-stat-num-${jarNum}`);
    const deltaNumEl = document.getElementById(`ph-delta-num-${jarNum}`);
    const badgeEl = document.getElementById(`ph-badge-${jarNum}`);
    const pointerEl = document.getElementById(`spectrum-pointer-${jarNum}`);
    const spectrumLbl = document.getElementById(`spectrum-lbl-${jarNum}`);

    if (phInput) {
        const ph = parseFloat(phInput.value) || 7.0;
        const delta = ph - 7.0;
        const color = getUniversalIndicatorColor(ph);
        const st = getPhStatusText(ph);

        if (liquidEl) liquidEl.style.backgroundColor = color;
        if (statNumEl) {
            statNumEl.textContent = `pH ${ph.toFixed(2)}`;
            statNumEl.style.color = color;
        }
        if (deltaNumEl) {
            deltaNumEl.textContent = `${delta > 0 ? '+' : ''}${delta.toFixed(2)}`;
        }
        if (badgeEl) {
            badgeEl.textContent = st.label;
            badgeEl.className = `ph-status-badge ${st.cls}`;
        }
        if (pointerEl) {
            const pct = (ph / 14.0) * 100;
            pointerEl.style.left = `${pct}%`;
        }
        if (spectrumLbl) {
            spectrumLbl.textContent = `pH ${ph.toFixed(2)}`;
        }
    }

    renderTitrationCurve();
};

// ==============================================================================
// 3. EQUILIBRATION REACTION TIMER
// ==============================================================================
let phTimerInterval = null;
let phTimerSeconds = 10 * 60; // 10 minutes default
let isPhTimerRunning = false;

window.togglePhTimer = function() {
    const btn = document.getElementById("phTimerStartBtn");
    const badge = document.getElementById("phTimerBadge");

    if (isPhTimerRunning) {
        clearInterval(phTimerInterval);
        isPhTimerRunning = false;
        if (btn) btn.innerHTML = '<i class="fa-solid fa-play"></i> Resume';
        if (badge) { badge.textContent = "PAUSED"; badge.className = "badge bg-warning text-dark font-mono"; }
    } else {
        isPhTimerRunning = true;
        if (btn) btn.innerHTML = '<i class="fa-solid fa-pause"></i> Pause';
        if (badge) { badge.textContent = "EQUILIBRATING"; badge.className = "badge bg-emerald-subtle text-emerald font-mono"; }

        phTimerInterval = setInterval(() => {
            if (phTimerSeconds > 0) {
                phTimerSeconds--;
                updatePhTimerDisplay();
            } else {
                clearInterval(phTimerInterval);
                isPhTimerRunning = false;
                if (btn) btn.innerHTML = '<i class="fa-solid fa-play"></i> Start';
                if (badge) { badge.textContent = "EQUILIBRATED"; badge.className = "badge bg-success text-white font-mono"; }
                playPhTimerChime();
            }
        }, 1000);
    }
};

window.resetPhTimer = function(mins = 10) {
    clearInterval(phTimerInterval);
    isPhTimerRunning = false;
    phTimerSeconds = mins * 60;
    updatePhTimerDisplay();

    const btn = document.getElementById("phTimerStartBtn");
    const badge = document.getElementById("phTimerBadge");
    if (btn) btn.innerHTML = '<i class="fa-solid fa-play"></i> Start';
    if (badge) { badge.textContent = "STANDBY"; badge.className = "badge bg-dark border border-secondary text-light font-mono"; }

    document.querySelectorAll(".preset-btn").forEach(b => {
        b.classList.remove("active");
        if (b.textContent.includes(`${mins}m`)) b.classList.add("active");
    });
};

function updatePhTimerDisplay() {
    const display = document.getElementById("phTimerDisplay");
    if (!display) return;
    const m = Math.floor(phTimerSeconds / 60);
    const s = phTimerSeconds % 60;
    display.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function playPhTimerChime() {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.frequency.setValueAtTime(784, audioCtx.currentTime); // G5
        gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 1.2);
        osc.start();
        osc.stop(audioCtx.currentTime + 1.2);
    } catch (e) {
        console.debug("Audio cue bypassed:", e);
    }
}

// ==============================================================================
// 4. PLANT CHEMICAL FEED RATE SCALER
// ==============================================================================
function initPhPlantFeedCalc() {
    calculatePhPlantFeed();
}

window.calculatePhPlantFeed = function() {
    const flowInput = document.getElementById("phPlantFlowInput");
    const doseInput = document.getElementById("phCalcDoseInput");
    const reagentSelect = document.getElementById("reagentTypeSelect");

    const flow = parseFloat(flowInput ? flowInput.value : 1000) || 1000; // m³/hr
    const dose = parseFloat(doseInput ? doseInput.value : 18.0) || 18.0;   // mL/L or g/m³ equivalent
    const selectedOption = reagentSelect ? reagentSelect.options[reagentSelect.selectedIndex] : null;
    const optPurity = selectedOption?.dataset?.purity ? parseFloat(selectedOption.dataset.purity) : null;
    const optVal = (reagentSelect ? reagentSelect.value : "lime").toLowerCase();
    const optText = (selectedOption ? selectedOption.textContent : "").toLowerCase();

    // Reagent purity / activity factors
    let purityFactor = optPurity || 1.0;
    let sackWeightKg = 25.0;

    if (!optPurity) {
        if (optVal.includes("lime") || optText.includes("lime")) purityFactor = 0.90;      // 90% hydrated lime Ca(OH)2
        else if (optVal.includes("soda") || optText.includes("soda")) purityFactor = 0.99; // 99% dense soda ash
        else if (optVal.includes("caustic") || optText.includes("naoh") || optText.includes("caustic")) purityFactor = 0.50; // 50% liquid caustic
        else if (optVal.includes("acid") || optText.includes("acid")) purityFactor = 0.98;
    }

    // Feed rate kg/hr = (flow m³/hr * dose g/m³) / (1000 * purity)
    const rateKgHr = (flow * dose) / (1000 * purityFactor);
    const rateKgDay = rateKgHr * 24;
    const bagsDay = rateKgDay / sackWeightKg;
    const pumpMlMin = (rateKgHr / 1.1) * (1000 / 60); // slurry dosing rate approx

    const rateHrEl = document.getElementById("feedRateKgHr");
    const rateDayEl = document.getElementById("feedRateKgDay");
    const bagsEl = document.getElementById("feedBagsDay");
    const pumpEl = document.getElementById("feedPumpMlMin");

    if (rateHrEl) rateHrEl.textContent = `${rateKgHr.toFixed(1)} kg/hr`;
    if (rateDayEl) rateDayEl.textContent = `${Math.round(rateKgDay)} kg/day`;
    if (bagsEl) bagsEl.textContent = `${bagsDay.toFixed(1)} bags/day`;
    if (pumpEl) pumpEl.textContent = `${Math.round(pumpMlMin)} mL/min`;
};

// ==============================================================================
// 5. KEYBOARD SHORTCUTS
// ==============================================================================
function initPhKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
            e.preventDefault();
            const saveBtn = document.getElementById("savePhBtn");
            if (saveBtn) saveBtn.click();
        }

        if (e.code === "Space" && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
            e.preventDefault();
            togglePhTimer();
        }
    });
}

// ============================================================================
// 6. FILTERED REPORT ANALYTICS
// ============================================================================
function initPhReportAnalytics() {
    const source = document.getElementById("ph-report-data");
    if (!source || !window.Plotly) return;
    let data;
    try { data = JSON.parse(source.textContent || "{}"); } catch (_) { return; }
    const layout = {
        autosize: true, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "Inter, Segoe UI, sans-serif", size: 9, color: "#98abc5" },
        margin: { l: 44, r: 12, t: 9, b: 32 }, showlegend: true,
        legend: { orientation: "h", y: 1.16, font: { size: 8 } },
        xaxis: { gridcolor: "rgba(148,163,184,.10)", tickfont: { color: "#8295b1" } },
        yaxis: { gridcolor: "rgba(148,163,184,.10)", tickfont: { color: "#8295b1" } },
        hoverlabel: { bgcolor: "#101b34", bordercolor: "#52658a", font: { color: "#e9f5ff", size: 10 } },
    };
    const config = { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] };
    const median = (items) => {
        const sorted = items.filter(Number.isFinite).sort((a, b) => a - b);
        if (!sorted.length) return null;
        const middle = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
    };
    const drawControl = () => {
        const node = document.getElementById("ph-report-dose-timeline");
        if (!node) return;
        const points = data.dose_timeline || [];
        const values = points.map((row) => row.value).filter(Number.isFinite);
        const center = median(values);
        const mad = median(values.map((value) => Math.abs(value - center)));
        const dates = points.map((row) => row.date);
        const traces = [{ x: dates, y: points.map((row) => row.value), type: "scatter", mode: "lines+markers", name: "Adjustment dose", line: { color: "#a78bfa", width: 2 }, marker: { color: "#c4b5fd", size: 6 }, hovertemplate: "%{x}<br>%{y:.2f} mL<extra></extra>" }];
        if (dates.length && center !== null) [["Median", center, "#22d3ee", "solid"], ["Upper 3 MAD", center + 3 * 1.4826 * mad, "#f59e0b", "dash"], ["Lower 3 MAD", Math.max(0, center - 3 * 1.4826 * mad), "#f59e0b", "dash"]].forEach(([name, value, color, dash]) => traces.push({ x: dates, y: dates.map(() => value), type: "scatter", mode: "lines", name, line: { color, width: 1, dash }, hovertemplate: `${name}: %{y:.2f} mL<extra></extra>` }));
        if (data.dose_fit?.length) traces.push({ x: data.dose_fit.map((row) => row.date), y: data.dose_fit.map((row) => row.value), type: "scatter", mode: "lines", name: "Theil–Sen trend", line: { color: "#34d399", width: 2, dash: "dot" } });
        const chartLayout = { ...layout, xaxis: { ...layout.xaxis, type: "date", title: "Test date" }, yaxis: { ...layout.yaxis, title: "Established dose (mL)", rangemode: "tozero" } };
        if (!dates.length) chartLayout.annotations = [{ text: "No established doses match these filters", x: .5, y: .5, xref: "paper", yref: "paper", showarrow: false, font: { color: "#8193ae", size: 10 } }];
        window.Plotly.react(node, traces, chartLayout, config);
    };
    const drawDosePh = () => {
        const node = document.getElementById("ph-report-dose-response");
        if (!node) return;
        const response = data.dose_ph || {};
        const traces = [{ x: (response.points || []).map((point) => point.x), y: (response.points || []).map((point) => point.y), customdata: (response.points || []).map((point) => point.date), type: "scatter", mode: "markers", name: "Bench outcome", marker: { size: 8, color: (response.points || []).map((point) => point.y), colorscale: [[0, "#f59e0b"], [.5, "#34d399"], [1, "#a78bfa"]], cmin: 5, cmax: 9, showscale: true, colorbar: { title: "pH", thickness: 8, len: .7, tickfont: { size: 8, color: "#98abc5" } }, line: { color: "#dbeafe", width: .6 }, opacity: .85 }, hovertemplate: "Dose %{x:.2f} mL<br>Result pH %{y:.2f}<br>%{customdata}<extra></extra>" }];
        if (response.fit?.length) traces.push({ x: response.fit.map((point) => point.x), y: response.fit.map((point) => point.y), type: "scatter", mode: "lines", name: "Theil–Sen fit", line: { color: "#22d3ee", width: 2, dash: "dot" } });
        if (response.points?.length) {
            const extent = response.points.reduce((range, point) => [Math.min(range[0], point.x), Math.max(range[1], point.x)], [Infinity, -Infinity]);
            traces.push({ x: extent, y: [7, 7], type: "scatter", mode: "lines", name: "Neutral target pH 7", line: { color: "#34d399", width: 1, dash: "dash" } });
        }
        const chartLayout = { ...layout, xaxis: { ...layout.xaxis, title: "Adjustment dose (mL)" }, yaxis: { ...layout.yaxis, title: "Resulting pH", range: [5, 9] } };
        if (response.correlation) chartLayout.annotations = [{ text: `Spearman ρ ${response.correlation.rho} · p ${response.correlation.p ?? "—"}`, x: .99, y: .98, xref: "paper", yref: "paper", xanchor: "right", yanchor: "top", showarrow: false, font: { color: "#c4b5fd", size: 9 } }];
        if (!response.points?.length) chartLayout.annotations = [{ text: "No dose / pH pairs match these filters", x: .5, y: .5, xref: "paper", yref: "paper", showarrow: false, font: { color: "#8193ae", size: 10 } }];
        window.Plotly.react(node, traces, chartLayout, config);
    };
    const drawRawAssociation = (parameterId) => {
        const node = document.getElementById("ph-report-raw-response");
        if (!node) return;
        const association = (data.raw_associations || []).find((item) => String(item.id) === String(parameterId)) || data.raw_dose || {};
        const traces = [{ x: (association.points || []).map((point) => point.x), y: (association.points || []).map((point) => point.y), customdata: (association.points || []).map((point) => point.date), type: "scatter", mode: "markers", name: association.name || "Linked water value", marker: { size: 8, color: "#22d3ee", opacity: .82, line: { color: "#cffafe", width: .8 } }, hovertemplate: "%{x:.3f}<br>Adjustment dose %{y:.2f} mL<br>%{customdata}<extra></extra>" }];
        if (association.fit?.length) traces.push({ x: association.fit.map((point) => point.x), y: association.fit.map((point) => point.y), type: "scatter", mode: "lines", name: "Theil–Sen fit", line: { color: "#a78bfa", width: 2, dash: "dot" } });
        const chartLayout = { ...layout, xaxis: { ...layout.xaxis, title: `${association.name || "Raw-water value"}${association.unit ? ` (${association.unit})` : ""}` }, yaxis: { ...layout.yaxis, title: "Adjustment dose (mL)", rangemode: "tozero" } };
        if (association.correlation) chartLayout.annotations = [{ text: `Spearman ρ ${association.correlation.rho} · p ${association.correlation.p ?? "—"}`, x: .99, y: .98, xref: "paper", yref: "paper", xanchor: "right", yanchor: "top", showarrow: false, font: { color: "#c4b5fd", size: 9 } }];
        if (!association.points?.length) chartLayout.annotations = [{ text: "Not enough linked source-water values", x: .5, y: .5, xref: "paper", yref: "paper", showarrow: false, font: { color: "#8193ae", size: 10 } }];
        window.Plotly.react(node, traces, chartLayout, config);
    };
    const drawHistogram = () => {
        const node = document.getElementById("ph-report-dose-hist");
        if (!node) return;
        const distribution = data.dose_histogram || {};
        const chartLayout = { ...layout, showlegend: false, xaxis: { ...layout.xaxis, title: "Established dose (mL)" }, yaxis: { ...layout.yaxis, title: "Tests", dtick: 1, rangemode: "tozero" } };
        const traces = [{ x: distribution.centers || [], y: distribution.counts || [], type: "bar", marker: { color: "#8b5cf6", line: { color: "rgba(255,255,255,.2)", width: 1 } }, hovertemplate: "%{x:.2f} mL<br>%{y} tests<extra></extra>" }];
        if (!distribution.counts?.length) chartLayout.annotations = [{ text: "No established doses match these filters", x: .5, y: .5, xref: "paper", yref: "paper", showarrow: false, font: { color: "#8193ae", size: 10 } }];
        window.Plotly.react(node, traces, chartLayout, config);
    };
    const drawCoagulantGroups = () => {
        const node = document.getElementById("ph-report-source-groups");
        if (!node) return;
        const groups = data.groups || [];
        const traces = groups.map((group, index) => ({ y: group.doses, type: "box", name: group.name, boxpoints: "all", jitter: .35, pointpos: 0, marker: { color: ["#22d3ee", "#a78bfa", "#34d399", "#f59e0b"][index % 4], size: 5, opacity: .75 }, line: { color: ["#22d3ee", "#a78bfa", "#34d399", "#f59e0b"][index % 4] }, hovertemplate: `${group.name}<br>%{y:.2f} mL<extra></extra>` }));
        const chartLayout = { ...layout, showlegend: false, xaxis: { ...layout.xaxis, title: "Source coagulant" }, yaxis: { ...layout.yaxis, title: "pH adjustment dose (mL)", rangemode: "tozero" } };
        if (!traces.length) chartLayout.annotations = [{ text: "No linked coagulant groups match these filters", x: .5, y: .5, xref: "paper", yref: "paper", showarrow: false, font: { color: "#8193ae", size: 10 } }];
        window.Plotly.react(node, traces, chartLayout, config);
    };
    requestAnimationFrame(() => {
        drawControl();
        drawDosePh();
        drawRawAssociation(document.getElementById("ph-report-raw-select")?.value || data.selected_parameter);
        drawHistogram();
        drawCoagulantGroups();
    });
    document.getElementById("ph-report-raw-select")?.addEventListener("change", (event) => drawRawAssociation(event.target.value));
}
