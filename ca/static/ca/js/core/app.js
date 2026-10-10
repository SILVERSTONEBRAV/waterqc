(() => {
    "use strict";

    const shell = document.getElementById("app-shell");

    if (!shell) {
        return;
    }

    window.CA = window.CA || {};
    window.CA.state = window.CA.state || {};

    const storageKey = "ca.sidebar.state";

    const isMobile = () =>
        window.matchMedia("(max-width: 1024px)").matches;

    const setDesktopState = (expanded) => {
        if (isMobile()) {
            return;
        }

        shell.classList.toggle("is-sidebar-expanded", expanded);
        shell.classList.toggle("is-sidebar-collapsed", !expanded);
        shell.classList.remove("is-sidebar-open");

        const state = expanded ? "expanded" : "collapsed";
        shell.dataset.sidebarState = state;
        window.CA.state.sidebarState = state;

        const sidebar = document.getElementById("ca-sidebar");
        if (sidebar) {
            sidebar.dataset.state = state;
        }

        const toggle = document.getElementById("sidebar-toggle");
        toggle?.setAttribute("aria-expanded", expanded ? "true" : "false");

        if (typeof window.CA.shell?.setSidebarState === "function") {
            window.CA.shell.setSidebarState(state);
        }
    };

    const setMobileState = (open) => {
        shell.classList.toggle("is-sidebar-open", open);
        shell.dataset.sidebarOpen = open ? "true" : "false";
        document.body.classList.toggle("ca-sidebar-open", open);

        const backdrop = document.getElementById("ca-sidebar-backdrop");
        if (backdrop) {
            backdrop.setAttribute("aria-hidden", open ? "false" : "true");
        }

        const toggle = document.getElementById("sidebar-toggle");
        toggle?.setAttribute("aria-expanded", open ? "true" : "false");
    };

    const closeMobileSidebar = () => setMobileState(false);
    const openMobileSidebar = () => setMobileState(true);

    const toggleSidebar = () => {
        if (isMobile()) {
            setMobileState(!shell.classList.contains("is-sidebar-open"));
            return;
        }

        const expanded = shell.classList.contains("is-sidebar-expanded");
        setDesktopState(!expanded);

        try {
            localStorage.setItem(
                storageKey,
                expanded ? "collapsed" : "expanded"
            );
        } catch (_) {}
    };

    const restoreSidebarState = () => {
        if (isMobile()) {
            setMobileState(false);
            return;
        }

        let state = shell.dataset.sidebarState || "expanded";

        try {
            state = localStorage.getItem(storageKey) || state;
        } catch (_) {}

        setDesktopState(state !== "collapsed");
    };

    const bindSidebar = () => {
        document.addEventListener("click", (event) => {
            const trigger = event.target.closest(
                "#sidebar-toggle, #sidebar-close, [data-action='toggle-sidebar'], [data-action='collapse-sidebar']"
            );

            if (trigger) {
                event.preventDefault();
                if (trigger.dataset.action === "collapse-sidebar" && !isMobile()) {
                    setDesktopState(false);
                    try {
                        localStorage.setItem(storageKey, "collapsed");
                    } catch (_) {}
                    return;
                }
                toggleSidebar();
                return;
            }

            if (event.target.closest("#ca-sidebar-backdrop, .ca-sidebar-overlay")) {
                closeMobileSidebar();
                return;
            }

            if (isMobile() && event.target.closest("[data-sidebar-close]")) {
                closeMobileSidebar();
            }
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && isMobile()) {
                closeMobileSidebar();
            }
        });

        const sidebar = document.getElementById("ca-sidebar");
        if (sidebar) {
            let hoverTimer = null;

            sidebar.addEventListener("mouseenter", () => {
                if (isMobile()) return;
                if (!shell.classList.contains("is-sidebar-collapsed")) return;
                clearTimeout(hoverTimer);
                shell.classList.add("is-sidebar-hover");
                sidebar.classList.add("is-hover-expanded");
            });

            sidebar.addEventListener("mouseleave", () => {
                if (isMobile()) return;
                hoverTimer = setTimeout(() => {
                    shell.classList.remove("is-sidebar-hover");
                    sidebar.classList.remove("is-hover-expanded");
                }, 120);
            });
        }

        window.addEventListener("resize", restoreSidebarState, { passive: true });
    };

    const init = () => {
        restoreSidebarState();
        bindSidebar();

        window.CA.state.sidebarToggle = toggleSidebar;
        window.CA.state.openSidebar = openMobileSidebar;
        window.CA.state.closeSidebar = closeMobileSidebar;
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
    } else {
        init();
    }
})();
