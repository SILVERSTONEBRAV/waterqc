/* Keep application content at the full viewport size. Regular browser tabs
 * enter fullscreen on the first trusted interaction; installed PWAs request it
 * through the web app manifest.
 */
(function () {
    "use strict";

    const root = document.documentElement;
    root.classList.add("app-fullscreen");

    const FS_KEY = "qad_fullscreen_active";
    const FS_EXIT_KEY = "qad_fullscreen_user_exited";

    function isPwa() {
        return window.matchMedia &&
            (window.matchMedia("(display-mode: fullscreen)").matches ||
             window.matchMedia("(display-mode: standalone)").matches);
    }

    function syncFullscreenState() {
        if (document.fullscreenElement) {
            sessionStorage.setItem(FS_KEY, "1");
            sessionStorage.removeItem(FS_EXIT_KEY);
        }
    }

    document.addEventListener("fullscreenchange", () => {
        if (document.fullscreenElement) {
            sessionStorage.setItem(FS_KEY, "1");
            sessionStorage.removeItem(FS_EXIT_KEY);
        } else {
            // If user explicitly pressed Esc or exited, remember so we don't annoy them
            sessionStorage.setItem(FS_EXIT_KEY, "1");
            sessionStorage.removeItem(FS_KEY);
        }
    });

    function requestFullscreenAfterInteraction(event) {
        if (!event.isTrusted || document.fullscreenElement ||
            typeof root.requestFullscreen !== "function") {
            return;
        }

        if (isPwa()) return;

        // If user explicitly exited during this session, don't re-force unless they clicked an internal navigation
        if (sessionStorage.getItem(FS_EXIT_KEY) === "1" && sessionStorage.getItem(FS_KEY) !== "1") {
            return;
        }

        root.requestFullscreen().then(() => {
            sessionStorage.setItem(FS_KEY, "1");
            sessionStorage.removeItem(FS_EXIT_KEY);
        }).catch((error) => {
            console.info("[QAD] Fullscreen request handled:", error);
        });
    }

    // Save intent before navigating internally
    document.addEventListener("click", (event) => {
        const link = event.target.closest("a");
        if (link && link.href && link.origin === window.location.origin) {
            if (document.fullscreenElement || sessionStorage.getItem(FS_KEY) === "1") {
                sessionStorage.setItem(FS_KEY, "1");
                sessionStorage.removeItem(FS_EXIT_KEY);
            }
        }
    }, true);

    document.addEventListener("pointerdown", requestFullscreenAfterInteraction, true);
    document.addEventListener("keydown", requestFullscreenAfterInteraction, true);
    document.addEventListener("touchstart", requestFullscreenAfterInteraction, true);

    // ESC key handles exiting fullscreen / closing overlays
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" || event.keyCode === 27) {
            if (document.fullscreenElement) {
                document.exitFullscreen().catch(() => {});
            }
        }
    });

    const toggleSelector = "#fullscreenToggle, [data-fullscreen-toggle], .fullscreen-toggle, .fullscreen-control, [data-close-app-window], #pwa-global-close-control, .btn-launcher-close";

    function applyAppViewport() {
        root.classList.add("app-fullscreen");
        if (document.body) {
            document.body.classList.add("app-fullscreen-shell");
        }

        document.querySelectorAll(toggleSelector).forEach((control) => control.remove());
    }

    applyAppViewport();
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", applyAppViewport, { once: true });
    }

    // Remove controls added by HTMX or other client-side renderers as well.
    if ("MutationObserver" in window && document.documentElement) {
        const observer = new MutationObserver((records) => {
            records.forEach((record) => record.addedNodes.forEach((node) => {
                if (!(node instanceof Element)) return;
                if (node.matches(toggleSelector)) node.remove();
                node.querySelectorAll(toggleSelector).forEach((control) => control.remove());
            }));
        });
        observer.observe(document.documentElement, { childList: true, subtree: true });
    }
})();
