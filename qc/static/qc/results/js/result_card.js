// static/qc/results/js/result_card.js
// ──────────────────────────────────────────────────────────────
// QCA Analytics — Advanced Real-Time Progressive Dashboard
// Features:
//   1. PWA Fullscreen Mode Enforcement & Service Worker
//   2. Cycle Navigation Ribbon (All Cycles / Direct Cycle Jump)
//   3. Card Permanence Guarantee & Input State Preservation
//   4. Web Audio Synthesized Futuristic Sound FX (Save / Alert / Tap)
//   5. Excel-Style High-Speed Navigation
//   6. WebSocket Real-Time Stream & Fallback Heartbeat
//   7. Holographic Shortcuts HUD & Native Fullscreen Toggle
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
    let fallbackPollTimer = null;

    let persistenceWatchdogTimer = null;

    let isBusy = false;
    let isEditing = false;
    let hasQueuedRefresh = false;
    let isShuttingDown = false;
    let soundEnabled = localStorage.getItem("qca_sound") !== "muted";


    // Track active input state before HTMX swaps to eliminate typing interruption
    let lastActiveInputInfo = null;

    // ═══════════════════════════════════════════════════════════
    // 1. PWA REGISTRATION & FULLSCREEN MODE ENFORCEMENT
    // ═══════════════════════════════════════════════════════════
    function isPWAMode() {
        return window.matchMedia("(display-mode: fullscreen)").matches ||
               window.matchMedia("(display-mode: standalone)").matches ||
               window.navigator.standalone === true;
    }

    function enforcePWAFullscreen() {
        if (!document.fullscreenElement) {
            const docEl = document.documentElement;
            const rfs = docEl.requestFullscreen || docEl.webkitRequestFullscreen || docEl.msRequestFullscreen;
            if (rfs) {
                rfs.call(docEl).catch(() => {});
            }
        }
    }

    function registerPWA() {
        if ("serviceWorker" in navigator) {
            window.addEventListener("load", () => {
                navigator.serviceWorker.register("/static/qc/results/js/sw.js")
                    .then(reg => console.log("[QCA PWA] Service Worker active in scope:", reg.scope))
                    .catch(err => console.warn("[QCA PWA] Service Worker registration failed:", err));
            });
        }

        // When launched as PWA or clicked anywhere in standalone mode, trigger fullscreen
        window.addEventListener("click", enforcePWAFullscreen, { passive: true });
        window.addEventListener("touchstart", enforcePWAFullscreen, { passive: true });
        if (isPWAMode()) {
            setTimeout(enforcePWAFullscreen, 400);
        }
    }

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

    function scheduleRefresh() {
        clearTimeout(refreshDebounceTimer);
        refreshDebounceTimer = setTimeout(() => refreshCardsAndTopbar(), REFRESH_DEBOUNCE_MS);
    }

    function refreshCardsAndTopbar(force = false) {
        if (!hasHTMX()) return;
        const container = getCardsContainer();
        if (!container) return;

        if (document.hidden && !force) {
            hasQueuedRefresh = true;
            return;
        }
        if ((isBusy || isEditing) && !force) {
            hasQueuedRefresh = true;
            return;
        }

        isBusy = true;
        hasQueuedRefresh = false;

        captureActiveInputState();

        // Perform atomic HTMX swap on cards container
        htmx.ajax("GET", buildCardsRefreshUrl(), {
            target: "#cards-container",
            swap: "outerHTML"
        });

        // Concurrently refresh telemetry topbars
        refreshTopbar();
    }

    function refreshTopbar() {
        if (!hasHTMX()) return;
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
            if (card.classList.contains("dismissing")) return;
            card.style.setProperty("display", "flex", "important");
            card.style.setProperty("opacity", "1", "important");
            card.style.setProperty("visibility", "visible", "important");
            card.style.setProperty("flex-direction", "column");
        });
        // Also guard the card bodies
        const bodies = document.querySelectorAll("#cards-container .card-cycle-body");
        bodies.forEach(body => {
            if (body.closest(".dismissing")) return;
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
                    label.textContent = "Offline (Polling)";
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
                    break;
                case "analysis.created":
                case "analysis_created":
                case "results.updated":
                case "qc_results_updated":
                case "dashboard.refresh":
                case "dashboard_refresh":
                    playSound("click");
                    scheduleRefresh();
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

    function reconnectWebSocket() {
        clearTimeout(reconnectTimer);
        reconnectAttempts++;
        const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempts), RECONNECT_MAX_MS);
        setConnectionStatus("reconnecting");
        reconnectTimer = setTimeout(connectWebSocket, delay);
    }

    function startFallbackPolling() {
        clearInterval(fallbackPollTimer);
        fallbackPollTimer = setInterval(() => {
            if (!isEditing && !isBusy && document.visibilityState === "visible") {
                refreshCardsAndTopbar();
            }
        }, 60000); // 1-minute fallback heartbeat
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
            hasQueuedRefresh = false;
            scheduleRefresh();
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

        if (isNaN(val) || !limits) {
            input.classList.remove("form-control-danger", "form-control-success");
            if (oorBubble) oorBubble.style.display = "none";
            return;
        }

        if (val < limits.min || val > limits.max) {
            input.classList.add("form-control-danger");
            input.classList.remove("form-control-success");
            // Show the out-of-range spec bubble
            if (oorBubble) {
                oorBubble.style.display = "flex";
                oorBubble.setAttribute("aria-hidden", "false");
            }
            if (playAlertOnAbnormal) playSound("alert");
        } else {
            input.classList.remove("form-control-danger");
            input.classList.add("form-control-success");
            // Hide the out-of-range spec bubble
            if (oorBubble) {
                oorBubble.style.display = "none";
                oorBubble.setAttribute("aria-hidden", "true");
            }
        }
    }

    function parseSpec(text) {
        const match = text.match(/(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)/);
        if (match) return { min: parseFloat(match[1]), max: parseFloat(match[2]) };
        const maxMatch = text.match(/≤\s*(\d+\.?\d*)/);
        if (maxMatch) return { min: -Infinity, max: parseFloat(maxMatch[1]) };
        const minMatch = text.match(/≥\s*(\d+\.?\d*)/);
        if (minMatch) return { min: parseFloat(minMatch[1]), max: Infinity };
        return null;
    }

    // Autosave removed — manual form submission only

    // ═══════════════════════════════════════════════════════════
    // 9. HEADER CONTROLS (Scope, Theme, Audio, Fullscreen, HUD)
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

        // Fullscreen Toggle
        const fsBtn = document.getElementById("fullscreenToggle");
        if (fsBtn) {
            fsBtn.addEventListener("click", () => {
                playSound("click");
                toggleFullscreen();
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

        // Shortcuts HUD Dialog Toggle
        const shortcutsBtn = document.getElementById("shortcutsToggle");
        const shortcutsModal = document.getElementById("shortcutsModal");
        if (shortcutsBtn && shortcutsModal) {
            shortcutsBtn.addEventListener("click", () => {
                playSound("click");
                shortcutsModal.showModal();
            });
        }

        // Global hotkeys (F for fullscreen, M for mute, ? for shortcuts, 0-9 for cycles)
        document.addEventListener("keydown", (e) => {
            if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) {
                return;
            }

            if (e.key === "f" || e.key === "F") {
                e.preventDefault();
                toggleFullscreen();
            } else if (e.key === "m" || e.key === "M") {
                e.preventDefault();
                soundEnabled = !soundEnabled;
                localStorage.setItem("qca_sound", soundEnabled ? "active" : "muted");
                updateSoundIcon();
                if (soundEnabled) playSound("save");
            } else if (e.key === "?") {
                e.preventDefault();
                const modal = document.getElementById("shortcutsModal");
                if (modal) {
                    modal.open ? modal.close() : modal.showModal();
                }

        });
    }

    function toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(() => {});
        } else {
            if (document.exitFullscreen) document.exitFullscreen().catch(() => {});
        }
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
            captureActiveInputState();
        }
    });

    document.body.addEventListener("htmx:afterSwap", e => {
        if (e.target.id === "cards-container" || e.target.id === "dashboard-topbars") {
            isBusy = false;
            enforceCardsVisibility();
            initCardInputs();
            restoreActiveInputState();
            startLiveClock();
            initCompletionLifecycle();
            updateCompletedChips();
            // Re-enforce after a brief delay in case of CSS reflows
            setTimeout(enforceCardsVisibility, 100);
            setTimeout(enforceCardsVisibility, 500);
        }
    });

    document.body.addEventListener("htmx:responseError", e => {
        if (e.detail.target?.id === "cards-container") isBusy = false;
    });

    // ═══════════════════════════════════════════════════════════
    // 11. INITIALIZATION
    // ═══════════════════════════════════════════════════════════
    function init() {
        document.documentElement.classList.add("dashboard-locked");
        document.body.classList.add("dashboard-fullscreen");

        registerPWA();
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
        startFallbackPolling();
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
        clearInterval(fallbackPollTimer);
        clearInterval(persistenceWatchdogTimer);
        if (socket) {
            socket.onclose = null;
            socket.close();
            socket = null;
        }
    });

})();


