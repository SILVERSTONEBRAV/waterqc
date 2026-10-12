// static/core/js/fullscreen.js
// ──────────────────────────────────────────────────────────────
// Platform-wide PWA & Fullscreen Enforcement
// Ensures all apps open and stay in fullscreen mode across the platform
// ──────────────────────────────────────────────────────────────

(function () {
    "use strict";

    // 1. Service Worker Registration (Platform-wide root scope)
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/sw.js", { scope: "/" })
                .then((reg) => {
                    console.log("[PWA] Service Worker registered with root scope:", reg.scope);
                })
                .catch((err) => {
                    // Fallback to static path if root sw.js is not routed
                    navigator.serviceWorker.register("/static/core/js/sw.js", { scope: "/" })
                        .catch(() => {});
                });
        });
    }

    // 2. Fullscreen Helpers & Vendor Prefixes
    function isFullscreen() {
        return Boolean(
            document.fullscreenElement ||
            document.webkitFullscreenElement ||
            document.mozFullScreenElement ||
            document.msFullscreenElement
        );
    }

    function isStandalonePWA() {
        return (
            window.matchMedia("(display-mode: fullscreen)").matches ||
            window.matchMedia("(display-mode: standalone)").matches ||
            navigator.standalone === true
        );
    }

    function requestFullscreenSafe() {
        if (isFullscreen()) return Promise.resolve();

        const docEl = document.documentElement;
        let p = null;

        if (docEl.requestFullscreen) {
            p = docEl.requestFullscreen();
        } else if (docEl.webkitRequestFullscreen) {
            p = docEl.webkitRequestFullscreen();
        } else if (docEl.mozRequestFullScreen) {
            p = docEl.mozRequestFullScreen();
        } else if (docEl.msRequestFullscreen) {
            p = docEl.msRequestFullscreen();
        }

        if (p && typeof p.catch === "function") {
            return p.catch((err) => {
                // Browser requires user gesture; will re-trigger on next interaction
                return null;
            });
        }
        return Promise.resolve();
    }

    // 3. UI Indicator for Fullscreen Enforcement
    let hudElement = null;

    function createOrUpdateHud(show) {
        if (!show || isFullscreen()) {
            if (hudElement && hudElement.parentNode) {
                hudElement.parentNode.removeChild(hudElement);
                hudElement = null;
            }
            return;
        }

        if (hudElement) return;

        hudElement = document.createElement("div");
        hudElement.id = "pwa-fullscreen-hud";
        hudElement.setAttribute("role", "status");
        hudElement.setAttribute("aria-live", "polite");
        hudElement.style.cssText = `
            position: fixed;
            bottom: 16px;
            right: 16px;
            z-index: 999999;
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.95));
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.35);
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 0 15px rgba(56, 189, 248, 0.2);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            padding: 8px 16px;
            border-radius: 9999px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.025em;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            user-select: none;
            opacity: 0.95;
        `;

        hudElement.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
            </svg>
            <span>Tap to Return to Fullscreen</span>
        `;

        hudElement.addEventListener("mouseenter", () => {
            hudElement.style.transform = "scale(1.05)";
            hudElement.style.opacity = "1";
        });
        hudElement.addEventListener("mouseleave", () => {
            hudElement.style.transform = "scale(1)";
            hudElement.style.opacity = "0.95";
        });

        hudElement.addEventListener("click", (e) => {
            e.stopPropagation();
            requestFullscreenSafe();
        });

        document.body.appendChild(hudElement);
    }

    // 4. Fullscreen State Sync
    function onFullscreenChange() {
        if (isFullscreen()) {
            document.documentElement.classList.add("is-fullscreen-mode");
            document.body.classList.add("is-fullscreen-mode");
            createOrUpdateHud(false);
        } else {
            document.documentElement.classList.remove("is-fullscreen-mode");
            document.body.classList.remove("is-fullscreen-mode");
            // If exited, show persistent reminder and arm next interaction
            createOrUpdateHud(true);
        }
    }

    // 5. Automatic Fullscreen Triggering on Interaction
    let armInteraction = true;

    function handleFirstGesture(e) {
        if (!isFullscreen()) {
            requestFullscreenSafe().then(() => {
                if (isFullscreen()) {
                    createOrUpdateHud(false);
                }
            });
        }
    }

    // Attach interaction listeners to window & document
    ["click", "keydown", "touchstart", "pointerdown"].forEach((evt) => {
        document.addEventListener(evt, handleFirstGesture, { passive: true });
    });

    // Listen for fullscreen change events across vendor prefixes
    document.addEventListener("fullscreenchange", onFullscreenChange);
    document.addEventListener("webkitfullscreenchange", onFullscreenChange);
    document.addEventListener("mozfullscreenchange", onFullscreenChange);
    document.addEventListener("MSFullscreenChange", onFullscreenChange);

    // Re-assert fullscreen when page or tab regains focus
    window.addEventListener("focus", () => {
        if (!isFullscreen()) {
            requestFullscreenSafe();
        }
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && !isFullscreen()) {
            requestFullscreenSafe();
        }
    });

    // Try immediate fullscreen on page load
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            requestFullscreenSafe();
            if (!isFullscreen()) {
                createOrUpdateHud(true);
            }
        });
    } else {
        requestFullscreenSafe();
        if (!isFullscreen()) {
            createOrUpdateHud(true);
        }
    }

    // Global APIs for pages/buttons that want direct control
    window.NCWSC = window.NCWSC || {};
    window.NCWSC.requestFullscreen = requestFullscreenSafe;
    window.NCWSC.isFullscreen = isFullscreen;
})();
