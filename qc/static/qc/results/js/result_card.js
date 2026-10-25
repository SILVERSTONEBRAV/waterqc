// static/qc/results/js/result_card.js
// ──────────────────────────────────────────────────────────────
// QCA Analytics — Advanced Real-Time Progressive Dashboard
// Features:
//   1. Full-viewport PWA shell
//   2. Cycle Navigation Ribbon (All Cycles / Direct Cycle Jump)
//   3. Card Permanence Guarantee & Input State Preservation
//   4. Web Audio Synthesized Futuristic Sound FX (Save / Alert / Tap)
//   5. Excel-Style High-Speed Navigation
//   6. Durable WebSocket Real-Time Stream
//   7. Holographic Shortcuts HUD
// ──────────────────────────────────────────────────────────────

(() => {
    "use strict";

    if (window.__QCA_CONTROLLER_ACTIVE__) return;
    window.__QCA_CONTROLLER_ACTIVE__ = true;

    const RECONNECT_BASE_MS = 1000;
    const RECONNECT_MAX_MS = 30000;
    const REFRESH_DEBOUNCE_MS = 350;
    let socket = null;
    let reconnectAttempts = 0;
    let reconnectTimer = null;
    let refreshDebounceTimer = null;
    let clockTimer = null;
    const receivedRealtimeEvents = new Set();

    let persistenceWatchdogTimer = null;

    let isBusy = false;
    let isEditing = false;
    let hasQueuedRefresh = false;
    let queuedRefreshPreserveInput = true;
    let preserveInputForNextSwap = true;
    let isShuttingDown = false;
    let soundEnabled = localStorage.getItem("qca_sound") !== "muted";


    // Track active input state before HTMX swaps to eliminate typing interruption
    let lastActiveInputInfo = null;

    // ═══════════════════════════════════════════════════════════
    // 2. WEB AUDIO API SYNTHESIZER
    // ═══════════════════════════════════════════════════════════
    let audioCtx = null;
    function getAudioContext() {
        if (!audioCtx) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (AudioContextClass) audioCtx = new AudioContextClass();
        }
        if (audioCtx && audioCtx.state === "suspended") {
            audioCtx.resume().catch(() => {});
        }
        return audioCtx;
    }

    function playSound(type) {
        if (!soundEnabled) return;
        try {
            const ctx = getAudioContext();
            if (!ctx) return;
            const now = ctx.currentTime;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.connect(gain);
            gain.connect(ctx.destination);

            if (type === "save") {
                // High-tech positive chime: 587Hz (D5) -> 880Hz (A5)
                osc.type = "sine";
                osc.frequency.setValueAtTime(587.33, now);
                osc.frequency.exponentialRampToValueAtTime(880, now + 0.12);
                gain.gain.setValueAtTime(0.08, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
                osc.start(now);
                osc.stop(now + 0.2);
            } else if (type === "alert") {
                // Out of range warning pulse: 320Hz -> 240Hz
                osc.type = "sawtooth";
                osc.frequency.setValueAtTime(320, now);
                osc.frequency.linearRampToValueAtTime(240, now + 0.15);
                gain.gain.setValueAtTime(0.09, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
                osc.start(now);
                osc.stop(now + 0.2);
            } else if (type === "click") {
                // Subtle futuristic tap: 1200Hz
                osc.type = "sine";
                osc.frequency.setValueAtTime(1200, now);
                gain.gain.setValueAtTime(0.03, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
                osc.start(now);
                osc.stop(now + 0.06);
            }
        } catch (e) {
            // Audio policy ignored until interaction
        }
    }

    // ═══════════════════════════════════════════════════════════
    // 3. REFRESH & CARD PERSISTENCE SAFEGUARD
    // ═══════════════════════════════════════════════════════════
    function hasHTMX() { return typeof window.htmx !== "undefined"; }
    function getCardsContainer() { return document.getElementById("cards-container"); }

    function buildCardsRefreshUrl() {
        const url = new URL(window.location.href);
        url.searchParams.set("partial", "cards");
        return `${url.pathname}${url.search}`;
    }

    function captureActiveInputState() {
        const activeEl = document.activeElement;
        if (activeEl && activeEl.classList.contains("excel-input")) {
            lastActiveInputInfo = {
                name: activeEl.name,
                selectionStart: activeEl.selectionStart,
                selectionEnd: activeEl.selectionEnd,
                val: activeEl.value
            };
        } else {
            lastActiveInputInfo = null;
        }
    }

    function restoreActiveInputState() {
        if (!lastActiveInputInfo) return;
        const targetInput = document.querySelector(`input[name="${lastActiveInputInfo.name}"]`);
        if (targetInput) {
            targetInput.focus();
            if (lastActiveInputInfo.selectionStart !== null && lastActiveInputInfo.selectionEnd !== null) {
                targetInput.setSelectionRange(lastActiveInputInfo.selectionStart, lastActiveInputInfo.selectionEnd);
            }
        }
    }

    function scheduleRefresh(force = false, preserveInputState = true) {
        clearTimeout(refreshDebounceTimer);
        refreshDebounceTimer = setTimeout(() => refreshCardsAndTopbar(force, preserveInputState), REFRESH_DEBOUNCE_MS);
    }

    function hasPermanentCards(root) {
        const scope = root || document;
        return !!scope.querySelector(
            "#cards-container .result-card, #cards-container .permanent-card, .result-card.permanent-card, .visible-cycle-card"
        );
    }

    function isEmptyCardsPayload(fragment) {
        if (!fragment) return true;
        const hasCard = fragment.querySelector(
            ".result-card, .permanent-card, .visible-cycle-card"
        );
        const emptyState = fragment.querySelector(".empty-dashboard-card");
        return !hasCard || !!emptyState;
    }

    function dedupeTopbars() {
        const bars = document.querySelectorAll("#dashboard-topbars");
        if (bars.length <= 1) return;
        for (let i = 1; i < bars.length; i++) {
            bars[i].remove();
        }
    }

    function refreshCardsAndTopbar(force = false, preserveInputState = true) {
        if (!hasHTMX()) return;
        const container = getCardsContainer();
        if (!container) return;

        if (document.hidden) {
            hasQueuedRefresh = true;
            queuedRefreshPreserveInput = queuedRefreshPreserveInput && preserveInputState;
            return;
        }
        if (isBusy || isEditing) {
            hasQueuedRefresh = true;
            queuedRefreshPreserveInput = queuedRefreshPreserveInput && preserveInputState;
            return;
        }

        // Routine telemetry updates keep the worksheet stable. Database change
        // events use force=true to refresh cards immediately.
        if (!force) {
            refreshTopbar();
            return;
        }

        isBusy = true;
        hasQueuedRefresh = false;
        queuedRefreshPreserveInput = true;
        preserveInputForNextSwap = preserveInputState;
        if (preserveInputState) captureActiveInputState();
        else lastActiveInputInfo = null;

        htmx.ajax("GET", buildCardsRefreshUrl(), {
            target: "#cards-container",
            swap: "outerHTML"
        });

        refreshTopbar();
    }

    function refreshTopbar() {
        if (!hasHTMX()) return;
        dedupeTopbars();
        const topbars = document.getElementById("dashboard-topbars");
        if (!topbars) return;

        const url = new URL(window.location.href);
        url.searchParams.set("partial", "topbar");

        htmx.ajax("GET", `${url.pathname}${url.search}`, {
            target: "#dashboard-topbars",
            swap: "outerHTML"
        });
    }

    // ═══════════════════════════════════════════════════════════
    // 4. GUARANTEED CARD PERMANENCE WATCHDOG
    // ═══════════════════════════════════════════════════════════
    function enforceCardsVisibility() {
        const cards = document.querySelectorAll("#cards-container .result-card, #cards-container .excel-card, #cards-container .card");
        cards.forEach(card => {
            // Clear a stale dismissal class from cached/older scripts.
            card.classList.remove("dismissing");
            card.style.setProperty("display", "flex", "important");
            card.style.setProperty("opacity", "1", "important");
            card.style.setProperty("visibility", "visible", "important");
            card.style.setProperty("flex-direction", "column");
        });
        // Also guard the card bodies
        const bodies = document.querySelectorAll("#cards-container .card-cycle-body");
        bodies.forEach(body => {
            body.style.setProperty("display", "flex", "important");
            body.style.setProperty("opacity", "1", "important");
            body.style.setProperty("visibility", "visible", "important");
        });
    }

    // ═══════════════════════════════════════════════════════════
    // 5. CARD PERMANENCE (Result cards stay visible until next analysis)
    // ═══════════════════════════════════════════════════════════
    function initCompletionLifecycle() {
        // No auto-dismissal: result cards stay visible continuously until next analysis
    }

    window.dismissCompletedCardNow = function() {
        // No-op: cards remain visible until next scheduled cycle
    };

    window.toggleCompletedStage = function(waterType) {
        if (!waterType) return;
        const sec = document.getElementById(`stage-section-${waterType}`);
        if (!sec) return;
        sec.classList.toggle("stage-force-open");
        if (sec.classList.contains("stage-force-open")) {
            playSound("click");
            const firstInput = sec.querySelector(".excel-input");
            if (firstInput) firstInput.focus();
        }
    };

    function checkStageAutoDismiss(waterType) {
        if (!waterType) return;
        const sec = document.getElementById(`stage-section-${waterType}`);
        if (!sec) return;
        const inputs = Array.from(sec.querySelectorAll(`.excel-input`));
        if (inputs.length === 0) return;
        const allFilled = inputs.every(inp => inp.value && inp.value.trim() !== "");
        if (allFilled) {
            if (!sec.classList.contains("stage-completed-done")) {
                sec.classList.add("stage-completed-done");
                playSound("save");
                updateCompletedChips();
                // Advance focus to next incomplete stage if available
                const nextOpenInput = document.querySelector(".stage-section:not(.stage-completed-done) .excel-input");
                if (nextOpenInput) nextOpenInput.focus();
            }
        } else {
            if (sec.classList.contains("stage-completed-done")) {
                sec.classList.remove("stage-completed-done");
                updateCompletedChips();
            }
        }
    }

    function updateCompletedChips() {
        const strip = document.getElementById("completed-stages-strip");
        const list = document.getElementById("completedChipsList");
        if (!strip || !list) return;

        const sections = document.querySelectorAll(".stage-section");
        let hasAny = false;
        sections.forEach(sec => {
            const wt = sec.dataset.waterType;
            if (!wt) return;
            const isDone = sec.classList.contains("stage-completed-done");
            let chip = list.querySelector(`.stage-chip-${wt}`);
            if (isDone) {
                hasAny = true;
                if (!chip) {
                    const title = sec.querySelector(".stage-tag-pill")?.textContent.trim() || wt.toUpperCase();
                    const total = sec.dataset.total || sec.querySelectorAll(".excel-input").length;
                    chip = document.createElement("button");
                    chip.type = "button";
                    chip.className = `completed-stage-chip stage-chip-${wt}`;
                    chip.onclick = () => window.toggleCompletedStage(wt);
                    chip.title = `Click to view/edit ${title}`;
                    chip.innerHTML = `<span class="chip-dot"></span><span>${title} (${total}/${total})</span><i class="fa-solid fa-pen-to-square chip-edit-icon"></i>`;
                    list.appendChild(chip);
                }
            } else if (chip) {
                chip.remove();
            }
        });
        strip.style.display = hasAny ? "flex" : "none";
    }

    function startPersistenceWatchdog() {
        clearInterval(persistenceWatchdogTimer);
        // Run frequently to prevent any flickering or external CSS from hiding cards
        persistenceWatchdogTimer = setInterval(() => {
            enforceCardsVisibility();
        }, 800);

        // MutationObserver: catch ANY attribute/style change that hides cards
        const container = getCardsContainer();
        if (container && typeof MutationObserver !== "undefined") {
            const observer = new MutationObserver((mutations) => {
                for (const m of mutations) {
                    if (m.type === "attributes" && m.attributeName === "style") {
                        const el = m.target;
                        if (el.classList.contains("result-card") || el.classList.contains("excel-card") || el.classList.contains("card-cycle-body")) {
                            const cs = el.style;
                            if (cs.display === "none" || cs.opacity === "0" || cs.visibility === "hidden") {
                                enforceCardsVisibility();
                            }
                        }
                    }
                }
            });
            observer.observe(container, { attributes: true, subtree: true, attributeFilter: ["style", "class"] });
        }
    }

    // Cycle ribbon removed — single current analysis card only
    function initCycleRibbon() { /* no-op */ }

    // ═══════════════════════════════════════════════════════════
    // 6. LIVE CLOCK
    // ═══════════════════════════════════════════════════════════
    function startLiveClock() {
        function tick() {
            const el = document.getElementById("live-clock");
            if (el) {
                const now = new Date();
                const h = String(now.getHours()).padStart(2, "0");
                const m = String(now.getMinutes()).padStart(2, "0");
                const s = String(now.getSeconds()).padStart(2, "0");
                el.textContent = `${h}:${m}:${s}`;
            }
        }
        tick();
        clearInterval(clockTimer);
        clockTimer = setInterval(tick, 1000);
    }

    // ═══════════════════════════════════════════════════════════
    // 7. WEBSOCKET REAL-TIME STREAM
    // ═══════════════════════════════════════════════════════════
    function setConnectionStatus(status) {
        const indicator = document.getElementById("ws-status-indicator");
        if (!indicator) return;

        indicator.className = "ws-status " + status;
        const label = indicator.querySelector(".ws-label");
        if (label) {
            switch (status) {
                case "connected":
                    label.textContent = "Live Stream";
                    break;
                case "disconnected":
                    label.textContent = "Offline";
                    break;
                case "reconnecting":
                    label.textContent = "Syncing…";
                    break;
                default:
                    label.textContent = "Connecting…";
            }
        }
    }

    function connectWebSocket() {
        if (isShuttingDown) return;
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
        if (socket) {
            socket.onclose = null;
            socket.close();
            socket = null;
        }

        const plantId = document.body.dataset.plantId || new URLSearchParams(window.location.search).get("plant") || "";
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const wsQuery = plantId ? `?plant=${encodeURIComponent(plantId)}` : "";
        const wsUrl = `${protocol}://${window.location.host}/ws/qc/dashboard/${wsQuery}`;

        setConnectionStatus("reconnecting");

        try {
            socket = new WebSocket(wsUrl);
        } catch (e) {
            setConnectionStatus("disconnected");
            reconnectWebSocket();
            return;
        }

        socket.onopen = () => {
            reconnectAttempts = 0;
            setConnectionStatus("connected");
        };

        socket.onmessage = event => {
            let data;
            try { data = JSON.parse(event.data); }
            catch (err) { return; }

            switch (data.type) {
                case "connection.ready":
                    // Reconcile once on connect/reconnect; no periodic status poll.
                    scheduleRefresh(true, false);
                    break;
                case "results.changed": {
                    const eventId = data.event_id;
                    if (eventId && receivedRealtimeEvents.has(eventId)) break;
                    if (eventId) {
                        receivedRealtimeEvents.add(eventId);
                        if (receivedRealtimeEvents.size > 256) {
                            receivedRealtimeEvents.delete(receivedRealtimeEvents.values().next().value);
                        }
                    }
                    scheduleRefresh(true, false);
                    break;
                }
                case "analysis.created":
                case "analysis_created":
                case "results.updated":
                case "qc_results_updated":
                case "dashboard.refresh":
                case "dashboard_refresh":
                    playSound("click");
                    scheduleRefresh(true, !["analysis.created", "analysis_created", "results.updated", "qc_results_updated"].includes(data.type));
                    break;
            }
        };

        socket.onerror = () => {};

        socket.onclose = () => {
            socket = null;
            if (isShuttingDown) return;
            setConnectionStatus("disconnected");
            reconnectWebSocket();
        };
    }

    window.addEventListener("qad:data-changed", event => {
        // QC cards consume the durable qc.results.changed stream instead.
        if (event.detail?.app_label === "qc") return;
        const newAnalysis = event.detail && event.detail.model === "wateranalysis" && event.detail.action === "created";
        scheduleRefresh(true, !newAnalysis);
        event.preventDefault();
    });

    window.addEventListener("qad:resume", event => {
        scheduleRefresh(true);
        event.preventDefault();
    });

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) return;
        if (!socket || socket.readyState === WebSocket.CLOSED) {
            connectWebSocket();
        }
        if (hasQueuedRefresh) {
            const preserveInputState = queuedRefreshPreserveInput;
            hasQueuedRefresh = false;
            queuedRefreshPreserveInput = true;
            scheduleRefresh(true, preserveInputState);
        } else {
            scheduleRefresh(true, false);
        }
    });

    function reconnectWebSocket() {
        clearTimeout(reconnectTimer);
        reconnectAttempts++;
        const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempts), RECONNECT_MAX_MS);
        setConnectionStatus("reconnecting");
        reconnectTimer = setTimeout(connectWebSocket, delay);
    }

    // ═══════════════════════════════════════════════════════════
    // 8. EXCEL NAVIGATION & CELL INTERACTIONS
    // ═══════════════════════════════════════════════════════════
    function initCardInputs() {
        const inputs = Array.from(document.querySelectorAll("#cards-container .excel-input"));
        inputs.forEach((input, idx) => {
            input.removeEventListener("keydown", onInputKeyDown);
            input.removeEventListener("input", onInputChanged);
            input.removeEventListener("focus", onInputFocused);
            input.removeEventListener("blur", onInputBlurred);

            input._idx = idx;
            input.addEventListener("keydown", onInputKeyDown);
            input.addEventListener("input", onInputChanged);
            input.addEventListener("focus", onInputFocused);
            input.addEventListener("blur", onInputBlurred);

            // Spec evaluation without noise
            validateCell(input, false);
        });
        updateCompletedChips();
    }

    function onInputKeyDown(e) {
        const input = e.target;
        const inputs = Array.from(document.querySelectorAll("#cards-container .excel-input"));
        const idx = inputs.indexOf(input);
        if (idx === -1) return;

        if (e.key === "Enter") {
            e.preventDefault();
            playSound("click");
            const next = e.shiftKey ? inputs[idx - 1] : inputs[idx + 1];
            if (next) next.focus();
        } else if (e.key === "ArrowRight") {
            if (input.selectionStart === input.value.length) {
                e.preventDefault();
                const next = inputs[idx + 1];
                if (next) next.focus();
            }
        } else if (e.key === "ArrowLeft") {
            if (input.selectionStart === 0) {
                e.preventDefault();
                const prev = inputs[idx - 1];
                if (prev) prev.focus();
            }
        } else if (e.key === "ArrowDown") {
            e.preventDefault();
            const next = inputs[idx + 1];
            if (next) next.focus();
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            const prev = inputs[idx - 1];
            if (prev) prev.focus();
        }
    }

    function onInputChanged(e) {
        const input = e.target;
        validateCell(input, true);
        checkStageAutoDismiss(input.dataset.waterType);
    }

    function onInputFocused(e) {
        isEditing = true;
        const cell = e.target.closest("td");
        const row = e.target.closest("tr");
        if (row) row.classList.add("excel-row-active");
        if (cell) cell.classList.add("excel-cell-active");
    }

    function onInputBlurred(e) {
        isEditing = false;
        const cell = e.target.closest("td");
        const row = e.target.closest("tr");
        if (row) row.classList.remove("excel-row-active");
        if (cell) cell.classList.remove("excel-cell-active");

        if (hasQueuedRefresh && !isBusy) {
            const preserveInputState = queuedRefreshPreserveInput;
            hasQueuedRefresh = false;
            queuedRefreshPreserveInput = true;
            scheduleRefresh(true, preserveInputState);
        }
    }

    function validateCell(input, playAlertOnAbnormal = false) {
        // Read spec directly from data-spec attribute (limits are hidden by default)
        const specText = input.dataset.spec || "";

        const val = parseFloat(input.value);
        const limits = parseSpec(specText);

        // Find the out-of-range bubble sibling
        const wrapper = input.closest(".input-cell-wrapper");
        const oorBubble = wrapper ? wrapper.querySelector(".oor-spec-bubble") : null;
        const limitLabel = wrapper ? wrapper.querySelector(".cell-sub-spec") : null;

        if (isNaN(val) || !limits) {
            input.classList.remove("form-control-danger", "form-control-success");
            if (wrapper) wrapper.classList.remove("cell-danger-glow", "cell-success-glow");
            if (oorBubble) {
                oorBubble.hidden = true;
                oorBubble.style.display = "none";
                oorBubble.setAttribute("aria-hidden", "true");
            }
            if (limitLabel) limitLabel.hidden = true;
            return;
        }

        if (val < limits.min || val > limits.max) {
            input.classList.add("form-control-danger");
            input.classList.remove("form-control-success");
            if (wrapper) {
                wrapper.classList.add("cell-danger-glow");
                wrapper.classList.remove("cell-success-glow");
            }
            if (oorBubble) {
                oorBubble.hidden = false;
                oorBubble.style.display = "flex";
                oorBubble.setAttribute("aria-hidden", "false");
            }
            if (limitLabel) limitLabel.hidden = false;
            if (playAlertOnAbnormal) playSound("alert");
        } else {
            input.classList.remove("form-control-danger");
            input.classList.add("form-control-success");
            if (wrapper) {
                wrapper.classList.add("cell-success-glow");
                wrapper.classList.remove("cell-danger-glow");
            }
            if (oorBubble) {
                oorBubble.hidden = true;
                oorBubble.style.display = "none";
                oorBubble.setAttribute("aria-hidden", "true");
            }
            if (limitLabel) limitLabel.hidden = true;
        }
    }

    function parseSpec(text) {
        const number = "-?\\d+(?:\\.\\d+)?";
        const match = text.match(new RegExp(`(${number})\\s*[-–]\\s*(${number})`));
        if (match) return { min: parseFloat(match[1]), max: parseFloat(match[2]) };
        const maxMatch = text.match(new RegExp(`≤\\s*(${number})`));
        if (maxMatch) return { min: -Infinity, max: parseFloat(maxMatch[1]) };
        const minMatch = text.match(new RegExp(`≥\\s*(${number})`));
        if (minMatch) return { min: parseFloat(minMatch[1]), max: Infinity };
        return null;
    }

    // Autosave removed — manual form submission only

    // ═══════════════════════════════════════════════════════════
    // 9. HEADER CONTROLS (Scope, Theme, Audio, HUD)
    // ═══════════════════════════════════════════════════════════
    function initHeaderControls() {
        // Superuser Scope Dropdown
        const plantSelect = document.getElementById("plantScopeSelect");
        if (plantSelect) {
            plantSelect.addEventListener("change", (e) => {
                const newPlant = e.target.value;
                if (!newPlant) return;
                playSound("click");
                const url = new URL(window.location.href);
                url.searchParams.set("plant", newPlant);
                window.location.href = url.toString();
            });
        }

        // Audio Effects Toggle
        const soundBtn = document.getElementById("soundToggle");
        if (soundBtn) {
            updateSoundIcon();
            soundBtn.addEventListener("click", () => {
                soundEnabled = !soundEnabled;
                localStorage.setItem("qca_sound", soundEnabled ? "active" : "muted");
                updateSoundIcon();
                if (soundEnabled) playSound("save");
            });
        }

        // Global hotkey (M mute).
        document.addEventListener("keydown", (e) => {
            if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) {
                return;
            }

            if (e.key === "m" || e.key === "M") {
                e.preventDefault();
                soundEnabled = !soundEnabled;
                localStorage.setItem("qca_sound", soundEnabled ? "active" : "muted");
                updateSoundIcon();
                if (soundEnabled) playSound("save");
            }
        });
    }

    function updateSoundIcon() {
        const soundBtn = document.getElementById("soundToggle");
        if (!soundBtn) return;
        const icon = soundBtn.querySelector("i");
        if (icon) {
            icon.className = soundEnabled ? "fa-solid fa-volume-high" : "fa-solid fa-volume-xmark";
        }
    }

    // ═══════════════════════════════════════════════════════════
    // 10. HTMX LIFECYCLE & SWAP RESTORATION
    // ═══════════════════════════════════════════════════════════
    document.body.addEventListener("htmx:beforeRequest", e => {
        if (e.detail.target?.id === "cards-container") {
            isBusy = true;
            if (preserveInputForNextSwap) captureActiveInputState();
            else lastActiveInputInfo = null;
        }
    });

    document.body.addEventListener("htmx:beforeSwap", e => {
        const target = e.detail.target;
        if (!target) return;

        if (target.id === "cards-container") {
            const incoming = e.detail.serverResponse
                ? new DOMParser().parseFromString(e.detail.serverResponse, "text/html")
                : null;
            const incomingContainer = incoming?.querySelector("#cards-container");
            const incomingWatermark = incomingContainer?.dataset.analysisWatermark || "";
            const currentWatermark = target.dataset.analysisWatermark || "";
            const analysisAdvanced = incomingWatermark && incomingWatermark !== currentWatermark;
            // Never wipe an on-screen permanent card with an empty/awaiting payload.
            // A changed analysis watermark is authoritative, even if the new
            // analysis currently has no card rows, so an older card is removed.
            if (hasPermanentCards(document) && isEmptyCardsPayload(incoming) && !analysisAdvanced) {
                e.detail.shouldSwap = false;
                isBusy = false;
            }
        }

        if (target.id === "dashboard-topbars") {
            dedupeTopbars();
        }
    });

    document.body.addEventListener("htmx:afterSwap", e => {
        if (e.target.id === "cards-container" || e.target.id === "dashboard-topbars") {
            isBusy = false;
            preserveInputForNextSwap = true;
            dedupeTopbars();
            enforceCardsVisibility();
            initCardInputs();
            restoreActiveInputState();
            startLiveClock();
            initCompletionLifecycle();
            updateCompletedChips();
            setTimeout(enforceCardsVisibility, 100);
            setTimeout(enforceCardsVisibility, 500);
            if (hasQueuedRefresh && !isEditing && !document.hidden) {
                const preserveInputState = queuedRefreshPreserveInput;
                hasQueuedRefresh = false;
                queuedRefreshPreserveInput = true;
                scheduleRefresh(true, preserveInputState);
            }
        }
    });

    document.body.addEventListener("htmx:responseError", e => {
        if (e.detail.target?.id === "cards-container") {
            isBusy = false;
            if (hasQueuedRefresh && !isEditing && !document.hidden) {
                const preserveInputState = queuedRefreshPreserveInput;
                hasQueuedRefresh = false;
                queuedRefreshPreserveInput = true;
                scheduleRefresh(true, preserveInputState);
            }
        }
    });

    // ═══════════════════════════════════════════════════════════
    // 11. INITIALIZATION
    // ═══════════════════════════════════════════════════════════
    function init() {
        document.documentElement.classList.add("dashboard-locked");
        document.body.classList.add("dashboard-fullscreen");

        startLiveClock();
        initHeaderControls();
        initCycleRibbon();
        initCardInputs();
        enforceCardsVisibility();
        startPersistenceWatchdog();
        initCompletionLifecycle();
        updateCompletedChips();

        if (hasHTMX()) {
            connectWebSocket();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    window.addEventListener("beforeunload", () => {
        isShuttingDown = true;
        clearTimeout(reconnectTimer);
        clearTimeout(refreshDebounceTimer);

        clearInterval(clockTimer);
        clearInterval(persistenceWatchdogTimer);
        if (socket) {
            socket.onclose = null;
            socket.close();
            socket = null;
        }
    });

})();


