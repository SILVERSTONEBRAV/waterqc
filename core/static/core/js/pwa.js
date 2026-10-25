/* NCWSCwaterLAB — High Performance PWA & Secure Multi-Tab / Single-Device Session Manager */
(function () {
    "use strict";

    // 1. Inject PWA stylesheet if missing
    if (document.head && !document.querySelector('link[data-pwa-styles]')) {
        var pwaStyles = document.createElement("link");
        pwaStyles.rel = "stylesheet";
        pwaStyles.href = "/static/core/css/pwa.css";
        pwaStyles.dataset.pwaStyles = "true";
        document.head.appendChild(pwaStyles);
    }

    // 1b. Inject Offline Queue engine if missing
    if (document.head && !document.querySelector('script[data-offline-queue]') && typeof window.QADOfflineQueue === "undefined") {
        var queueScript = document.createElement("script");
        queueScript.src = "/static/core/js/offline-queue.js";
        queueScript.dataset.offlineQueue = "true";
        document.head.appendChild(queueScript);
    }

    // 2. Service Worker Registration
    if ("serviceWorker" in navigator && (window.isSecureContext || window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")) {
        window.addEventListener("load", function () {
            navigator.serviceWorker.register("/sw.js", {
                scope: "/",
                updateViaCache: "none"
            }).then(function (reg) {
                if (reg && typeof reg.update === "function") {
                    reg.update().catch(function () {});
                }
            }).catch(function (error) {
                console.warn("[QAD PWA] Service worker registration:", error);
            });
        }, { once: true });
    }

    // 3. Multi-Tab Synchronization Channel
    // Logout on one tab automatically logs out all other open tabs instantly.
    var authChannel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("qad_auth_sync") : null;

    function broadcastLogout(reason) {
        var payload = JSON.stringify({
            action: "logout",
            reason: reason || "logged_out",
            timestamp: Date.now()
        });
        try {
            localStorage.setItem("qad_auth_logout_event", payload);
        } catch (e) {}
        if (authChannel) {
            try {
                authChannel.postMessage({ action: "logout", reason: reason || "logged_out" });
            } catch (e) {}
        }
    }

    function handleRemoteLogout(reason) {
        sessionStorage.removeItem("qad_active_session");
        var isLoginPage = window.location.pathname.includes("/login/");
        if (!isLoginPage) {
            window.location.href = "/accounts/login/?reason=" + encodeURIComponent(reason || "logged_out");
        }
    }

    if (authChannel) {
        authChannel.onmessage = function (event) {
            if (event.data && event.data.action === "logout") {
                handleRemoteLogout(event.data.reason);
            }
        };
    }

    window.addEventListener("storage", function (event) {
        if (event.key === "qad_auth_logout_event" && event.newValue) {
            try {
                var data = JSON.parse(event.newValue);
                if (data && data.action === "logout") {
                    handleRemoteLogout(data.reason);
                }
            } catch (e) {}
        }
    });

    // 4. Window Close vs Internal Navigation Tracking
    // Closing the app window is considered a logout. Internal link clicks must NOT log out.
    var isInternalNav = false;

    // Track internal links
    document.addEventListener("click", function (event) {
        var target = event.target;
        while (target && target !== document.body) {
            if (target.tagName === "A" && target.href) {
                try {
                    var targetUrl = new URL(target.href, window.location.origin);
                    if (targetUrl.origin === window.location.origin && !target.target.includes("_blank")) {
                        isInternalNav = true;
                    }
                } catch (e) {}
                break;
            }
            target = target.parentElement;
        }
    }, true);

    // Track form submissions
    document.addEventListener("submit", function () {
        isInternalNav = true;
    }, true);

    // Track history navigation (back/forward)
    window.addEventListener("popstate", function () {
        isInternalNav = true;
    });

    // Reset internal navigation flag on page visibility restore
    window.addEventListener("pageshow", function () {
        isInternalNav = false;
    });

    // When the app window / tab is closed or user exits the app:
    window.addEventListener("pagehide", function (event) {
        if (!isInternalNav) {
            sessionStorage.removeItem("qad_active_session");
            localStorage.setItem("qad_window_closed_at", Date.now().toString());

            // Synchronize logout across any other open tabs
            broadcastLogout("window_closed");

            // Dispatch logout beacon to server immediately
            if (navigator.sendBeacon) {
                try {
                    var logoutUrl = "/accounts/logout/";
                    var blob = new Blob(["action=window_close"], { type: "application/x-www-form-urlencoded" });
                    navigator.sendBeacon(logoutUrl, blob);
                } catch (e) {}
            }
        }
    });

    // 5. Intercept Manual Logout Links to Broadcast to All Tabs
    document.addEventListener("click", function (event) {
        var target = event.target;
        while (target && target !== document.body) {
            if (target.tagName === "A" && target.href && (target.href.includes("/accounts/logout/") || target.href.endsWith("/logout/"))) {
                broadcastLogout("logged_out");
                break;
            }
            target = target.parentElement;
        }
    }, true);

    // 6. Real-Time Single-Device Session Heartbeat
    // If the account is opened on another computer, this session is terminated and redirects immediately.
    (function initSessionHeartbeat() {
        var isLoginPage = window.location.pathname.includes("/login/");
        if (isLoginPage) return;

        var isChecking = false;

        function checkActiveSession() {
            if (isChecking) return;
            isChecking = true;

            fetch("/accounts/session-check/", {
                method: "GET",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "Cache-Control": "no-cache"
                },
                cache: "no-store"
            }).then(function (res) {
                if (res.status === 401) {
                    return res.json().then(function (data) {
                        var reason = (data && data.reason) || "concurrent_login";
                        broadcastLogout(reason);
                        handleRemoteLogout(reason);
                    }).catch(function () {
                        broadcastLogout("concurrent_login");
                        handleRemoteLogout("concurrent_login");
                    });
                }
            }).catch(function () {
                // Ignore transient network errors
            }).finally(function () {
                isChecking = false;
            });
        }

        // Heartbeat interval: every 20 seconds when visible, immediately on window focus/tab change
        setInterval(function () {
            if (!document.hidden) {
                checkActiveSession();
            }
        }, 20000);

        window.addEventListener("focus", checkActiveSession);
        document.addEventListener("visibilitychange", function () {
            if (!document.hidden) {
                checkActiveSession();
            }
        });
    })();

    // 7. Offline / Online Network Indicator
    var networkNotice = null;

    function updateNetworkNotice() {
        if (!document.body) return;
        if (!networkNotice) {
            networkNotice = document.createElement("div");
            networkNotice.className = "pwa-network-notice";
            networkNotice.setAttribute("role", "status");
            networkNotice.setAttribute("aria-live", "polite");
            networkNotice.hidden = true;
            document.body.appendChild(networkNotice);
        }
        if (!navigator.onLine) {
            networkNotice.textContent = "⚡ You are offline. Changes are saved locally on this device and will sync automatically when reconnected.";
            networkNotice.hidden = false;
        } else if (!networkNotice.hidden) {
            networkNotice.textContent = "✓ Connection restored. Syncing offline data to server…";
            window.setTimeout(function () {
                if (navigator.onLine && networkNotice) networkNotice.hidden = true;
            }, 3500);
        }
    }

    window.addEventListener("offline", updateNetworkNotice);
    window.addEventListener("online", updateNetworkNotice);

    // 8. Modern PWA Install Affordance
    var installPrompt = null;
    var installButton = null;

    function isAppleMobile() {
        return /iPhone|iPad|iPod/.test(navigator.userAgent) ||
            (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    }

    function isAlreadyInstalled() {
        return window.matchMedia("(display-mode: fullscreen)").matches ||
            window.matchMedia("(display-mode: standalone)").matches ||
            window.matchMedia("(display-mode: window-controls-overlay)").matches ||
            window.navigator.standalone === true;
    }

    function removeInstallButton() {
        if (installButton) {
            installButton.remove();
            installButton = null;
        }
    }

    function renderInstallButton() {
        if (isAlreadyInstalled() || (!installPrompt && !isAppleMobile()) || installButton || !document.body) return;

        installButton = document.createElement("button");
        installButton.id = "pwa-install-button";
        installButton.type = "button";
        installButton.setAttribute("aria-label", "Install NCWSCwaterLAB Application");
        installButton.innerHTML = isAppleMobile()
            ? '<i class="fa-solid fa-arrow-up-from-bracket" aria-hidden="true"></i><span>Add to Home</span>'
            : '<i class="fa-solid fa-cloud-arrow-down" aria-hidden="true"></i><span>Install App</span>';

        installButton.addEventListener("click", async function () {
            if (!installPrompt && isAppleMobile()) {
                window.alert("To install NCWSCwaterLAB on iOS:\n1. Tap the Share button in Safari.\n2. Tap 'Add to Home Screen'.");
                return;
            }
            if (!installPrompt) return;
            installButton.disabled = true;
            try {
                await installPrompt.prompt();
                await installPrompt.userChoice;
            } catch (err) {
                console.warn("[QAD PWA] Install prompt failed:", err);
            } finally {
                installPrompt = null;
                removeInstallButton();
            }
        });

        document.body.appendChild(installButton);
    }

    window.addEventListener("beforeinstallprompt", function (event) {
        event.preventDefault();
        installPrompt = event;
        renderInstallButton();
    });

    window.addEventListener("appinstalled", function () {
        installPrompt = null;
        removeInstallButton();
    });

    // 9. Client-Side Hashed / Shortened URL Engine
    // Transforms browser address bars into clean, short, hashed URLs without displaying long raw paths.
    var ROUTE_SLUG_MAP = {
        "/": "#/portal",
        "/qc/scada/": "#/scada",
        "/qc/cards/": "#/qc-cards",
        "/qc/dashboard/": "#/qc-dashboard",
        "/ca/": "#/chemlab",
        "/accounts/login/": "#/auth",
        "/accounts/profile/": "#/profile",
        "/instruments/": "#/telemetry",
        "/weeklytasks/": "#/tasks",
        "/jartest/": "#/jartest",
        "/PHadjustment/": "#/ph-adjust",
        "/chlorinedemand/": "#/chlorine",
        "/xmicalconcentration/": "#/concentration",
        "/backwashing/": "#/backwashing",
        "/inventory/": "#/inventory",
        "/central_lab/": "#/central-lab",
        "/duty_house/": "#/housing",
        "/maintenance/": "#/maintenance",
        "/microbial/": "#/microbial",
        "/heavy_metal/": "#/heavy-metals",
        "/filtered_water/": "#/filtered-water",
        "/alerts/": "#/alerts"
    };

    var REVERSE_ROUTE_MAP = {};
    for (var routePath in ROUTE_SLUG_MAP) {
        REVERSE_ROUTE_MAP[ROUTE_SLUG_MAP[routePath]] = routePath;
    }

    function computeShortHash(str) {
        var hash = 5381;
        for (var i = 0; i < str.length; i++) {
            hash = ((hash << 5) + hash) + str.charCodeAt(i);
            hash = hash & hash;
        }
        return Math.abs(hash).toString(36).slice(0, 6);
    }

    function getShortenedUrl(pathname, search) {
        var cleanPath = pathname.endsWith("/") ? pathname : pathname + "/";
        if (ROUTE_SLUG_MAP[cleanPath]) {
            return ROUTE_SLUG_MAP[cleanPath];
        }
        var parts = cleanPath.split("/").filter(Boolean);
        var prefix = parts[0] || "portal";
        var token = computeShortHash(cleanPath + (search || ""));
        return "#/" + prefix + "~" + token;
    }

    function initUrlMasking() {
        var currentHash = window.location.hash;
        // On refresh or direct hash navigation at root (e.g. /#/scada):
        if (window.location.pathname === "/" && currentHash && currentHash.startsWith("#/")) {
            var cachedTarget = sessionStorage.getItem("qad_route_" + currentHash);
            var targetPath = cachedTarget || REVERSE_ROUTE_MAP[currentHash];
            if (targetPath && targetPath !== "/") {
                window.location.replace(targetPath);
                return;
            }
        }

        try {
            var shortHash = getShortenedUrl(window.location.pathname, window.location.search);
            sessionStorage.setItem("qad_route_" + shortHash, window.location.pathname + window.location.search);
            if (window.history && window.history.replaceState) {
                var targetDisplay = "/" + shortHash;
                window.history.replaceState({ qad_real_path: window.location.pathname }, document.title, targetDisplay);
            }
        } catch (e) {}
    }

    // 10. Global Window Exit & Omnipresent Top-Right Close Button (X)
    function executeAppExit() {
        broadcastLogout("window_closed");
        if (navigator.sendBeacon) {
            try {
                navigator.sendBeacon("/accounts/logout/", new Blob(["action=window_close"], { type: "application/x-www-form-urlencoded" }));
            } catch (e) {}
        }
        sessionStorage.removeItem("qad_active_session");
        window.close();
        setTimeout(function () {
            window.location.href = "/accounts/logout/?reason=window_closed";
        }, 200);
    }

    function ensureGlobalCloseControl() {
        if (!document.body) return;
        var existingClose = document.querySelector("[data-close-app-window], .app-window-close, .btn-launcher-close");
        if (existingClose) return;

        if (document.getElementById("pwa-global-close-control")) return;

        var closeBtn = document.createElement("button");
        closeBtn.id = "pwa-global-close-control";
        closeBtn.type = "button";
        closeBtn.title = "Close Application";
        closeBtn.setAttribute("aria-label", "Close Application Window");
        closeBtn.innerHTML = "&times;";
        closeBtn.setAttribute("data-close-app-window", "true");

        closeBtn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            executeAppExit();
        });

        document.body.appendChild(closeBtn);
    }

    document.addEventListener("click", function (event) {
        var closeControl = event.target.closest("[data-close-app-window]");
        if (closeControl) {
            event.preventDefault();
            event.stopPropagation();
            executeAppExit();
        }
    }, true);

    function initializePwaShell() {
        renderInstallButton();
        updateNetworkNotice();
        ensureGlobalCloseControl();
        initUrlMasking();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializePwaShell, { once: true });
    } else {
        initializePwaShell();
    }
})();
