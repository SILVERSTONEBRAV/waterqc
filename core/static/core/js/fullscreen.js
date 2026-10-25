/* Keep application content at the full viewport size. Regular browser tabs
 * enter fullscreen on the first trusted interaction; installed PWAs request it
 * through the web app manifest.
 */
(function () {
    "use strict";

    const root = document.documentElement;
    root.classList.add("app-fullscreen");

    function requestFullscreenAfterInteraction(event) {
        if (!event.isTrusted || document.fullscreenElement ||
            typeof root.requestFullscreen !== "function") {
            return;
        }

        const isFullscreenPwa = window.matchMedia &&
            window.matchMedia("(display-mode: fullscreen)").matches;
        if (isFullscreenPwa) return;

        root.requestFullscreen().catch((error) => {
            // Keep retrying on later trusted interactions if the browser rejects it.
            console.info("[QAD] Fullscreen was not available:", error);
        });
    }

    document.addEventListener("pointerdown", requestFullscreenAfterInteraction, true);
    document.addEventListener("keydown", requestFullscreenAfterInteraction, true);

    document.addEventListener("click", (event) => {
        const closeControl = event.target.closest("[data-close-app-window]");
        if (closeControl) {
            event.preventDefault();
            event.stopPropagation();
            if (navigator.sendBeacon) {
                try {
                    navigator.sendBeacon("/accounts/logout/", new Blob(["action=window_close"], { type: "application/x-www-form-urlencoded" }));
                } catch (e) {}
            }
            try {
                localStorage.setItem("qad_auth_logout_event", JSON.stringify({ action: "logout", reason: "window_closed", timestamp: Date.now() }));
            } catch (e) {}
            window.close();
            setTimeout(() => {
                window.location.href = "/accounts/logout/?reason=window_closed";
            }, 200);
        }
    });

    const toggleSelector = "#fullscreenToggle, [data-fullscreen-toggle], .fullscreen-toggle, .fullscreen-control";

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
