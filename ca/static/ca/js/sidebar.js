document.addEventListener("DOMContentLoaded", () => {
    // Support CA dashboard layout (#ca-sidebar) and core layout (.sidebar)
    const caSidebar = document.getElementById("ca-sidebar") || document.querySelector(".ca-sidebar");
    const coreSidebar = document.querySelector(".sidebar");
    const contentWrapper = document.querySelector(".content-wrapper");
    const submenuToggles = document.querySelectorAll(".toggle-children");
    const appShell = document.getElementById("app-shell");

    // ===================================
    // CA Dashboard Sidebar Hover Support
    // ===================================
    if (caSidebar && appShell) {
        let caHoverTimer = null;
        caSidebar.addEventListener("mouseenter", () => {
            if (window.matchMedia("(max-width: 1024px)").matches) return;
            if (!appShell.classList.contains("is-sidebar-collapsed")) return;
            clearTimeout(caHoverTimer);
            appShell.classList.add("is-sidebar-hover");
            caSidebar.classList.add("is-hover-expanded");
        });

        caSidebar.addEventListener("mouseleave", () => {
            if (window.matchMedia("(max-width: 1024px)").matches) return;
            caHoverTimer = setTimeout(() => {
                appShell.classList.remove("is-sidebar-hover");
                caSidebar.classList.remove("is-hover-expanded");
            }, 120);
        });
    }

    // ===================================
    // Core Layout Sidebar Hover Support
    // ===================================
    if (coreSidebar) {
        coreSidebar.addEventListener("mouseenter", () => {
            coreSidebar.classList.add("expanded");
            if (contentWrapper) {
                contentWrapper.style.marginLeft = getComputedStyle(coreSidebar).width;
            }
        });

        coreSidebar.addEventListener("mouseleave", () => {
            coreSidebar.classList.remove("expanded");
            if (contentWrapper) {
                contentWrapper.style.marginLeft = getComputedStyle(coreSidebar).width;
            }
        });
    }

    // =========================
    // Submenu toggling
    // =========================
    submenuToggles.forEach(toggle => {
        toggle.addEventListener("click", e => {
            e.preventDefault();
            const parent = toggle.parentElement;
            if (!parent) return;
            const submenu = parent.querySelector(".sidebar-submenu");

            parent.classList.toggle("open");

            if (submenu) {
                if (parent.classList.contains("open")) {
                    submenu.style.maxHeight = submenu.scrollHeight + "px";
                } else {
                    submenu.style.maxHeight = "0px";
                }
            }
        });
    });

    // =========================
    // Open submenus on page load
    // =========================
    document.querySelectorAll(".sidebar-item.open .sidebar-submenu").forEach(submenu => {
        submenu.style.maxHeight = submenu.scrollHeight + "px";
    });
});

